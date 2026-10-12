"""
기념굿즈 SKU별 일일 매출 대시보드
- products.json + custom_codes.json 기반 SKU 리스트 (카테고리는 categories.json 순서 고정)
- bar_shop1 DB에서 SKU × 일자 × (매출/수량/주문수) 집계
- 주 시작 = 일요일
- 상단 툴바: [매출 | 수량 | 주문수] 지표 전환 버튼
- 주차별 접기/펼치기, SKU 0건 숨기기, 카테고리 접기
실행: python build_sku_daily.py [DAYS]  또는  [YYYY-MM-DD] [YYYY-MM-DD]
서버: sku_server.py가 generate_sku_html()을 import해서 사용
"""
import os, sys, io, json
from datetime import datetime, timedelta, date
from collections import defaultdict
# stdout 재할당은 __main__일 때만 (모듈로 import 시 부모 프로세스가 처리)
if __name__ == "__main__":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
import pymssql
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(r"C:\src\barunson-database-reference", ".env"))

CATEGORIES_FILE = os.path.join(HERE, "categories.json")
PRODUCTS_FILE = os.path.join(HERE, "products.json")
CUSTOM_CODES_FILE = os.path.join(HERE, "custom_codes.json")
SYNC_STATUS_FILE = os.path.join(HERE, "data", "sync_status.json")
OUT_FILE = os.path.join(HERE, "sku_dashboard.html")

# SKU별 세트 보정: DB는 개별 스티커 수/단가로 저장되어 있지만
# 실제 판매 단위는 1 set이므로 qty/amount를 set 기준으로 환산한다.
# qty_per_set: 1 set에 포함된 개별 개수, price_per_set: set 판매가(원)
SET_OVERRIDES = {
    "pearl_jj_3": {"qty_per_set": 200, "price_per_set": 3900},  # 진주스티커 3mm
    "pearl_jj_4": {"qty_per_set": 200, "price_per_set": 3900},  # 진주스티커 4mm
    "pearl_jj_5": {"qty_per_set": 100, "price_per_set": 3900},  # 진주스티커 5mm
    "2026_sticker_11": {"qty_per_set": 25, "price_per_set": 2500},  # 소프트터치 1set=25개
    "2026_sticker_12": {"qty_per_set": 25, "price_per_set": 2500},  # 오브제 씰 1set=25개
}

# 주 시작 = 일요일. weekday(): 월=0, 화=1, ..., 토=5, 일=6
# 일요일 기준 offset: 일=0, 월=1, 화=2, 수=3, 목=4, 금=5, 토=6
def sunday_offset(d):
    return (d.weekday() + 1) % 7

# 요일 라벨 (일요일부터 시작이지만, 표시는 실제 weekday에 따라)
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def build_sku_list():
    """products.json + custom_codes.json을 파일 순서대로 합쳐 반환"""
    products = load_json(PRODUCTS_FILE, [])
    customs = load_json(CUSTOM_CODES_FILE, [])
    seen, sku_list = set(), []
    for p in products:
        code = (p.get("card_code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        sku_list.append({
            "card_code": code,
            "name": p.get("name", ""),
            "category": p.get("category", ""),
            "discontinued": bool(p.get("discontinued", False)),
        })
    for cc in customs:
        code = (cc.get("card_code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        sku_list.append({
            "card_code": code,
            "name": cc.get("name", ""),
            "category": cc.get("category", ""),
            "discontinued": bool(cc.get("discontinued", False)),
        })
    return sku_list


def _new_db_conn():
    return pymssql.connect(
        server=os.getenv("DB_SERVER"),
        port=int(os.getenv("DB_PORT", "1433")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="bar_shop1",
        login_timeout=15, timeout=120,
    )


def _run_query_with_retry(sql, retries=2):
    """Azure SQL이 간헐적으로 연결을 끊는 10054 오류에 대비한 재시도 래퍼.
    매번 새 연결을 열어 stale 상태를 피한다."""
    import time as _time
    last_exc = None
    for attempt in range(retries + 1):
        conn = None
        try:
            conn = _new_db_conn()
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            conn.close()
            return rows
        except pymssql.OperationalError as e:
            last_exc = e
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            if attempt < retries:
                _time.sleep(1.5 * (attempt + 1))
            else:
                raise
    raise last_exc


def fetch_sku_daily(card_codes, date_from, date_to, batch_size=5):
    """(card_code, 'YYYY-MM-DD') -> {qty, amount, cnt}

    두 주문 테이블을 모두 조회해서 합산한다:
      1) custom_order / custom_order_item  — 청첩장 주문에 같이 나간 부가상품
         (item_count=개별 수량, item_price=개별 단가 → SET_OVERRIDES로 set 환산)
      2) CUSTOM_ETC_ORDER / CUSTOM_ETC_ORDER_ITEM — 부가상품 개별 주문
         (order_count=set 수량, card_sale_price=라인 총액[set수×단가] — order_count로 다시 곱하면 안 됨)

    매출 인식 조건: settle_date IS NOT NULL AND settle_(C|c)ancel_date IS NULL
    (status_seq는 신뢰할 수 없음 — 취소 주문도 status_seq=5로 남는 사례 확인됨)

    Azure SQL이 큰 IN 절이나 장시간 연결을 간헐적으로 끊는(10054) 문제가 있어
    batch_size개씩 나눠 쿼리하고, 쿼리마다 새 연결 + 재시도한다.
    """
    if not card_codes:
        return {}

    # (code, date) -> {qty, amount, cnt, wi:{...}, st:{...}}
    # wi = 청첩장 동반 (custom_order), st = 단독 (CUSTOM_ETC_ORDER)
    # top-level은 wi+st 합 (backward-compat)
    result = defaultdict(lambda: {
        "qty": 0, "amount": 0, "cnt": 0,
        "wi": {"qty": 0, "amount": 0, "cnt": 0},
        "st": {"qty": 0, "amount": 0, "cnt": 0},
    })

    def _merge(code, date_key, qty_v, amt_v, cnt_v, source):
        bucket = result[(code, date_key)]
        bucket["qty"] += qty_v
        bucket["amount"] += amt_v
        bucket["cnt"] += cnt_v
        bucket[source]["qty"] += qty_v
        bucket[source]["amount"] += amt_v
        bucket[source]["cnt"] += cnt_v

    for i in range(0, len(card_codes), batch_size):
        batch = card_codes[i:i + batch_size]
        safe = [c.replace("'", "''") for c in batch]
        in_list = ",".join(f"'{c}'" for c in safe)

        # 1) 청첩장 동반 부가상품 — 개별 개수/단가 저장, set 환산 필요
        sql1 = f"""
        SELECT
            CONVERT(varchar, o.order_date, 23),
            c.Card_Code,
            SUM(oi.item_count),
            SUM(oi.item_count * oi.item_price),
            COUNT(DISTINCT o.order_seq)
        FROM custom_order o WITH (NOLOCK)
        INNER JOIN custom_order_item oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
        INNER JOIN S2_Card c           WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
        WHERE o.settle_date IS NOT NULL
          AND o.settle_cancel_date IS NULL
          AND o.order_date >= '{date_from}'
          AND o.order_date <  DATEADD(day, 1, '{date_to}')
          AND c.Card_Code IN ({in_list})
        GROUP BY CONVERT(varchar, o.order_date, 23), c.Card_Code
        """
        for row in _run_query_with_retry(sql1):
            d, code, qty, amount, cnt = row
            code_s = str(code)
            qty_v = int(qty or 0)
            amt_v = int(amount or 0)
            cnt_v = int(cnt or 0)
            ov = SET_OVERRIDES.get(code_s)
            if ov:
                sets = round(qty_v / ov["qty_per_set"]) if ov["qty_per_set"] else 0
                qty_v = sets
                amt_v = sets * ov["price_per_set"]
            _merge(code_s, str(d)[:10], qty_v, amt_v, cnt_v, "wi")

        # 2) 부가상품 개별 주문 — 실 결제금액(settle_price) 기준 비례 배분
        # 쿠폰/할인이 적용된 경우 라인 총액(card_sale_price)이 아닌 실제 결제금액 반영
        # 예: 포스터 + 쿠폰으로 0원 결제 → 0으로 표시
        sql2 = f"""
        SELECT
            CONVERT(varchar, o.order_date, 23),
            c.Card_Code,
            SUM(oi.order_count),
            SUM(CASE WHEN ot.gross > 0
                     THEN oi.card_sale_price * 1.0 * COALESCE(o.settle_price, 0) / ot.gross
                     ELSE 0 END),
            COUNT(DISTINCT o.order_seq)
        FROM CUSTOM_ETC_ORDER o WITH (NOLOCK)
        INNER JOIN CUSTOM_ETC_ORDER_ITEM oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
        INNER JOIN (
            SELECT order_seq, SUM(card_sale_price) AS gross
            FROM CUSTOM_ETC_ORDER_ITEM WITH (NOLOCK)
            GROUP BY order_seq
        ) ot ON ot.order_seq = o.order_seq
        INNER JOIN S2_Card c WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
        WHERE o.settle_date IS NOT NULL
          AND o.settle_Cancel_Date IS NULL
          AND o.order_date >= '{date_from}'
          AND o.order_date <  DATEADD(day, 1, '{date_to}')
          AND c.Card_Code IN ({in_list})
        GROUP BY CONVERT(varchar, o.order_date, 23), c.Card_Code
        """
        for row in _run_query_with_retry(sql2):
            d, code, qty, amount, cnt = row
            code_s = str(code)
            qty_v = int(qty or 0)
            amt_v = int(amount or 0)  # 이미 실 결제금액 비례 배분된 값
            cnt_v = int(cnt or 0)
            # CUSTOM_ETC_ORDER에서는 qty가 이미 set 단위, amount도 실 결제 반영이므로
            # SET_OVERRIDES 보정 불필요 (custom_order_item만 보정 필요)
            _merge(code_s, str(d)[:10], qty_v, amt_v, cnt_v, "st")

    return dict(result)


def fmt_n(v):
    return "" if not v else f"{v:,}"


def _val(e, source, metric):
    """sales_map 엔트리에서 source(None=전체 / 'wi'=청첩장동반 / 'st'=단독)별 지표값 추출."""
    if not e:
        return 0
    if source:
        return e.get(source, {}).get(metric, 0)
    return e.get(metric, 0)


def generate_sku_html(date_from, date_to):
    """지정 기간의 SKU × 일자 대시보드 HTML을 반환. 서버에서 호출."""
    if isinstance(date_from, str):
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    if isinstance(date_to, str):
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()

    sku_list = build_sku_list()
    categories = load_json(CATEGORIES_FILE, [])

    days = (date_to - date_from).days + 1
    dates = [date_from + timedelta(days=i) for i in range(days)]

    card_codes = [s["card_code"] for s in sku_list]
    sales_map = fetch_sku_daily(
        card_codes,
        date_from.strftime("%Y-%m-%d"),
        date_to.strftime("%Y-%m-%d"),
    )

    # 주차 그룹 (일요일 시작)
    weeks = defaultdict(list)
    for d in dates:
        wk_start = d - timedelta(days=sunday_offset(d))
        weeks[wk_start].append(d)
    week_list = sorted(weeks.keys())
    # 주차 번호: 1부터 순차 (달력 주차 대신 대시보드 내 순서)
    wk_num_map = {ws: i + 1 for i, ws in enumerate(week_list)}

    # 카테고리 순서: categories.json 순서를 그대로 (매출순 아님, 사용자 지정)
    cat_order = [c["name"] for c in categories]
    for s in sku_list:
        if s["category"] and s["category"] not in cat_order:
            cat_order.append(s["category"])
    by_cat = defaultdict(list)
    for s in sku_list:
        by_cat[s["category"]].append(s)

    return _render_html(categories, cat_order, by_cat, dates, weeks, week_list, wk_num_map, sales_map)


def _build_copy_table_html(cat_order, by_cat, dates, sales_map, source=None, table_id="copyTable"):
    """구글시트 복사용 표.
    - source: None=전체 / 'wi'=청첩장 동반 / 'st'=단독 주문
    - 컬럼: 카테고리(rowspan=카테고리행수) | 상품명(rowspan=3) | 상품코드+지표 | 주차별(합계+일별)
    - SKU당 3행 (매출/수량/주문수)
    - 하단 그랜드 합계 6행 (매출합계/WoW/수량합계/WoW/주문수합계/WoW)
    - 빈 셀에도 0 표기
    """
    # 주차 그룹 (일요일 시작)
    wk_map = defaultdict(list)
    for d in dates:
        ws = d - timedelta(days=sunday_offset(d))
        wk_map[ws].append(d)
    week_list = sorted(wk_map.keys())

    # 헤더 — 2행
    h1 = [
        '<th rowspan="2">카테고리</th>',
        '<th rowspan="2">상품명</th>',
        '<th rowspan="2">상품코드 + 지표</th>',
    ]
    h2 = []
    for i, ws in enumerate(week_list):
        days_in_wk = wk_map[ws]
        we = ws + timedelta(days=6)
        h1.append(
            f'<th colspan="{len(days_in_wk) + 1}" class="wk-grp">'
            f'W.{i+1} <small>({ws.strftime("%m/%d")}~{we.strftime("%m/%d")})</small></th>'
        )
        h2.append(f'<th class="wk-sum-hdr">W.{i+1} 합계</th>')
        for d in days_in_wk:
            wd = WEEKDAY_KR[d.weekday()]
            d_str = d.strftime("%Y-%m-%d")
            h2.append(f'<th data-date="{d_str}">{d.strftime("%m/%d")}({wd})</th>')

    # 본문 — 카테고리별로 묶고, SKU마다 3행
    rows = []
    metrics = [("amount", "매출"), ("qty", "수량"), ("cnt", "주문수")]

    for cat_name in cat_order:
        skus = by_cat.get(cat_name, [])
        if not skus:
            continue
        cat_rowspan = len(skus) * 3  # 카테고리 셀의 rowspan = SKU수 × 3지표
        first_in_cat = True
        for s in skus:
            code = s["card_code"]
            name = s["name"]
            disc = " (단종)" if s.get("discontinued") else ""

            # SKU의 주차별 합계 미리 계산
            wk_sums = defaultdict(lambda: {"amount": 0, "qty": 0, "cnt": 0})
            for ws in week_list:
                for d in wk_map[ws]:
                    e = sales_map.get((code, d.strftime("%Y-%m-%d")))
                    for k in ("amount", "qty", "cnt"):
                        wk_sums[ws][k] += _val(e, source, k)

            for i, (mk, label) in enumerate(metrics):
                cells = []
                if first_in_cat and i == 0:
                    cells.append(f'<td class="t cat-cell" rowspan="{cat_rowspan}">{cat_name}</td>')
                if i == 0:
                    cells.append(f'<td class="t" rowspan="3">{name}{disc}</td>')
                cells.append(f'<td class="t metric-{mk}">{code} {label}</td>')
                for ws in week_list:
                    cells.append(f'<td class="wk-sum">{wk_sums[ws][mk]}</td>')
                    for d in wk_map[ws]:
                        d_str = d.strftime("%Y-%m-%d")
                        e = sales_map.get((code, d_str))
                        v = _val(e, source, mk)
                        cells.append(f'<td data-date="{d_str}">{v}</td>')
                rows.append(f'<tr data-metric="{mk}">' + ''.join(cells) + '</tr>')
            first_in_cat = False

    # --- 그랜드 합계 + WoW 행 (하단) ---
    # 모든 SKU 합산: 날짜별 + 주차별 총합
    grand_per_day = defaultdict(lambda: {"amount": 0, "qty": 0, "cnt": 0})
    for cat_name in cat_order:
        for s in by_cat.get(cat_name, []):
            for d in dates:
                e = sales_map.get((s["card_code"], d.strftime("%Y-%m-%d")))
                for k in ("amount", "qty", "cnt"):
                    grand_per_day[d.strftime("%Y-%m-%d")][k] += _val(e, source, k)

    def _fmt_wow(curr, prev):
        if prev is None or prev == 0:
            return ""
        pct = (curr - prev) / prev * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    for mk, label in metrics:
        # 합계 행
        total_cells = [f'<td colspan="3" class="grand-label">{label}합계</td>']
        for ws in week_list:
            wk_total = sum(grand_per_day[d.strftime("%Y-%m-%d")][mk] for d in wk_map[ws])
            total_cells.append(f'<td class="wk-sum grand-row">{wk_total}</td>')
            for d in wk_map[ws]:
                v = grand_per_day[d.strftime("%Y-%m-%d")][mk]
                total_cells.append(f'<td class="grand-row" data-date="{d.strftime("%Y-%m-%d")}">{v}</td>')
        rows.append(f'<tr class="grand-total" data-metric="{mk}">' + ''.join(total_cells) + '</tr>')

        # WoW 행 — 주차합계는 전주 대비, 일자는 7일전 대비
        wow_cells = [f'<td colspan="3" class="grand-label wow-label">WoW</td>']
        prev_wk_total = None
        for ws in week_list:
            wk_total = sum(grand_per_day[d.strftime("%Y-%m-%d")][mk] for d in wk_map[ws])
            wow_cells.append(f'<td class="wk-sum wow-cell">{_fmt_wow(wk_total, prev_wk_total)}</td>')
            for d in wk_map[ws]:
                d_str = d.strftime("%Y-%m-%d")
                prev_d_str = (d - timedelta(days=7)).strftime("%Y-%m-%d")
                curr_v = grand_per_day[d_str][mk]
                prev_v = grand_per_day[prev_d_str][mk] if prev_d_str in grand_per_day else None
                wow_cells.append(f'<td class="wow-cell" data-date="{d_str}">{_fmt_wow(curr_v, prev_v)}</td>')
            prev_wk_total = wk_total
        rows.append(f'<tr class="grand-wow" data-metric="{mk}">' + ''.join(wow_cells) + '</tr>')

    return (
        f'<table class="copy-table" id="{table_id}">'
        '<thead>'
        '<tr>' + ''.join(h1) + '</tr>'
        '<tr>' + ''.join(h2) + '</tr>'
        '</thead>'
        '<tbody>' + ''.join(rows) + '</tbody>'
        '</table>'
    )


def _build_report_table_html(cat_order, by_cat, dates, sales_map, source=None, table_id="reportTable"):
    """주간 보고용 표 — 직전 3주 완성된 주차 (이번주는 표시하지 않음).
    예: 이번주가 W.22면 W.19/W.20/W.21 보고. 매주 자동 rolling.
    - 컬럼: W-3합계(W.19) | W-2합계(W.20) | W-2 일별 7일 | W-1합계(W.21)
    - 일별 = 중간 주차(W-2 = W.20)의 일별 breakdown
    - 스티커 카테고리 제외, 3주간 매출>0 상품만
    - 카테고리별 소계+WoW + 전체 합계+WoW
    - 일별 WoW = 같은 요일 7일 전(W-3 = W.19) 대비
    """
    today = date.today()
    this_ws = today - timedelta(days=sunday_offset(today))     # W (이번주, 표시 안함)
    w_late  = this_ws - timedelta(days=7)                       # W-1 (보고 중 가장 최근, 예 W.21) — 일별 표시 대상
    w_mid   = this_ws - timedelta(days=14)                      # W-2 (중간, 예 W.20)
    w_early = this_ws - timedelta(days=21)                      # W-3 (가장 오래, 예 W.19) — 첫 열
    w_pre   = this_ws - timedelta(days=28)                      # W-4 (W-3의 WoW 계산용, 예 W.18)
    daily_dates = [w_late + timedelta(days=i) for i in range(7)]  # W-1 일별 (예 W.21: 5/17~5/23)

    # 주차 번호 (date_from = 2026-01-01 기준)
    if dates:
        d0 = dates[0]
        first_ws = d0 - timedelta(days=sunday_offset(d0))
    else:
        first_ws = this_ws
    def wk_num(ws):
        return ((ws - first_ws).days // 7) + 1
    n_early, n_mid, n_late = wk_num(w_early), wk_num(w_mid), wk_num(w_late)

    def wsum(code, ws, metric):
        t = 0
        for i in range(7):
            d_str = (ws + timedelta(days=i)).strftime("%Y-%m-%d")
            e = sales_map.get((code, d_str))
            t += _val(e, source, metric)
        return t

    def dval(code, d, metric):
        e = sales_map.get((code, d.strftime("%Y-%m-%d")))
        return _val(e, source, metric)

    def fmt_wow(curr, prev):
        if prev is None or prev == 0:
            return ""
        pct = (curr - prev) / prev * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.2f}%"

    # 스티커 제외
    cats_filtered = [c for c in cat_order if "스티커" not in c]

    metrics = [("amount", "매출"), ("qty", "수량"), ("cnt", "주문수")]

    # 헤더 — 컬럼 순서: W-3 합계 | W-2 합계 | W-1 합계 | W-1 일별 (7일)
    h1 = [
        '<th rowspan="2">카테고리</th>',
        '<th rowspan="2">상품명</th>',
        '<th rowspan="2">상품코드 + 지표</th>',
        f'<th rowspan="2" class="wk-grp">W.{n_early} 합계<br><small>{w_early.strftime("%m/%d")}~{(w_early+timedelta(days=6)).strftime("%m/%d")}</small></th>',
        f'<th rowspan="2" class="wk-grp">W.{n_mid} 합계<br><small>{w_mid.strftime("%m/%d")}~{(w_mid+timedelta(days=6)).strftime("%m/%d")}</small></th>',
        f'<th rowspan="2" class="wk-grp">W.{n_late} 합계<br><small>{w_late.strftime("%m/%d")}~{(w_late+timedelta(days=6)).strftime("%m/%d")}</small></th>',
        f'<th colspan="7" class="wk-grp">W.{n_late} 일별</th>',
    ]
    h2 = []
    for d in daily_dates:
        wd = WEEKDAY_KR[d.weekday()]
        h2.append(f'<th data-date="{d.strftime("%Y-%m-%d")}">{d.strftime("%m/%d")}({wd})</th>')

    rows = []

    # 그랜드 누적
    g_early = {"amount": 0, "qty": 0, "cnt": 0}        # W-3 (예 W.19) 합계
    g_pre   = {"amount": 0, "qty": 0, "cnt": 0}        # W-4 (예 W.18, W.19의 WoW용)
    g_mid   = {"amount": 0, "qty": 0, "cnt": 0}        # W-2 (예 W.20) 합계
    g_late  = {"amount": 0, "qty": 0, "cnt": 0}        # W-1 (예 W.21) 합계
    g_daily = {d: {"amount": 0, "qty": 0, "cnt": 0} for d in daily_dates}      # W-2 일별
    g_pre_daily = {d: {"amount": 0, "qty": 0, "cnt": 0} for d in daily_dates}  # W-3 같은 요일 (일별 WoW용)

    for cat_name in cats_filtered:
        skus = by_cat.get(cat_name, [])
        if not skus:
            continue

        # 매출>0 필터 (3주 = W-3 + W-2 + W-1 합산)
        active = []
        for s in skus:
            tot = wsum(s["card_code"], w_early, "amount") + wsum(s["card_code"], w_mid, "amount") + wsum(s["card_code"], w_late, "amount")
            if tot > 0:
                active.append(s)
        if not active:
            continue

        # 카테고리 누적
        c_early = {"amount": 0, "qty": 0, "cnt": 0}
        c_pre   = {"amount": 0, "qty": 0, "cnt": 0}    # W-4 (W-3의 WoW용)
        c_mid   = {"amount": 0, "qty": 0, "cnt": 0}
        c_late  = {"amount": 0, "qty": 0, "cnt": 0}
        c_daily = {d: {"amount": 0, "qty": 0, "cnt": 0} for d in daily_dates}
        c_pre_daily = {d: {"amount": 0, "qty": 0, "cnt": 0} for d in daily_dates}  # W-3 same weekday

        cat_rowspan = len(active) * 3
        first = True
        for s in active:
            code = s["card_code"]
            name = s["name"]
            disc = " (단종)" if s.get("discontinued") else ""

            # W-4 (W-3의 WoW용)
            for mk in ("amount", "qty", "cnt"):
                c_pre[mk] += wsum(code, w_pre, mk)

            for i, (mk, label) in enumerate(metrics):
                cells = []
                if first and i == 0:
                    cells.append(f'<td class="t cat-cell" rowspan="{cat_rowspan}">{cat_name}</td>')
                if i == 0:
                    cells.append(f'<td class="t" rowspan="3">{name}{disc}</td>')
                cells.append(f'<td class="t metric-{mk}">{code} {label}</td>')

                v_early = wsum(code, w_early, mk)
                v_mid   = wsum(code, w_mid, mk)
                v_late  = wsum(code, w_late, mk)
                cells.append(f'<td class="wk-sum">{v_early}</td>')
                cells.append(f'<td class="wk-sum">{v_mid}</td>')
                cells.append(f'<td class="wk-sum">{v_late}</td>')
                for d in daily_dates:
                    v = dval(code, d, mk)
                    cells.append(f'<td data-date="{d.strftime("%Y-%m-%d")}">{v}</td>')
                    c_daily[d][mk] += v
                    # 같은 요일의 W-2 값 (= d - 7days, 즉 W.20 같은 요일)
                    pv = dval(code, d - timedelta(days=7), mk)
                    c_pre_daily[d][mk] += pv

                c_early[mk] += v_early
                c_mid[mk] += v_mid
                c_late[mk] += v_late

                rows.append(f'<tr data-metric="{mk}">' + ''.join(cells) + '</tr>')
            first = False

        # 카테고리 소계 (3 지표 × [합계+WoW])
        for mk, m_label in metrics:
            # 소계 행 — W.19 | W.20 | W.21 | W.21 일별 7일
            sub = [
                '<td class="t cat-sub-empty"></td>',
                '<td class="t cat-sub-empty"></td>',
                f'<td class="t cat-sub-label">{m_label}</td>',
                f'<td class="wk-sum cat-sub">{c_early[mk]}</td>',
                f'<td class="wk-sum cat-sub">{c_mid[mk]}</td>',
                f'<td class="wk-sum cat-sub">{c_late[mk]}</td>',
            ]
            for d in daily_dates:
                sub.append(f'<td class="cat-sub" data-date="{d.strftime("%Y-%m-%d")}">{c_daily[d][mk]}</td>')
            rows.append(f'<tr class="cat-subtotal" data-metric="{mk}">' + ''.join(sub) + '</tr>')
            # WoW 행
            wow = [
                '<td class="t cat-sub-empty"></td>',
                '<td class="t cat-sub-empty"></td>',
                '<td class="t cat-sub-label wow-label">WoW</td>',
                f'<td class="wk-sum wow-cell">{fmt_wow(c_early[mk], c_pre[mk])}</td>',
                f'<td class="wk-sum wow-cell">{fmt_wow(c_mid[mk], c_early[mk])}</td>',
                f'<td class="wk-sum wow-cell">{fmt_wow(c_late[mk], c_mid[mk])}</td>',
            ]
            for d in daily_dates:
                wow.append(f'<td class="wow-cell" data-date="{d.strftime("%Y-%m-%d")}">{fmt_wow(c_daily[d][mk], c_pre_daily[d][mk])}</td>')
            rows.append(f'<tr class="cat-wow" data-metric="{mk}">' + ''.join(wow) + '</tr>')

        # 그랜드에 누적
        for mk in ("amount", "qty", "cnt"):
            g_early[mk] += c_early[mk]
            g_pre[mk] += c_pre[mk]
            g_mid[mk] += c_mid[mk]
            g_late[mk] += c_late[mk]
        for d in daily_dates:
            for mk in ("amount", "qty", "cnt"):
                g_daily[d][mk] += c_daily[d][mk]
                g_pre_daily[d][mk] += c_pre_daily[d][mk]

    # 그랜드 합계 (전체 카테고리, 스티커 제외)
    for mk, m_label in metrics:
        sub = [
            '<td class="t grand-empty"></td>',
            '<td class="t grand-empty"></td>',
            f'<td class="t grand-label">전체 {m_label}합계</td>',
            f'<td class="wk-sum grand-sub">{g_early[mk]}</td>',
            f'<td class="wk-sum grand-sub">{g_mid[mk]}</td>',
            f'<td class="wk-sum grand-sub">{g_late[mk]}</td>',
        ]
        for d in daily_dates:
            sub.append(f'<td class="grand-sub" data-date="{d.strftime("%Y-%m-%d")}">{g_daily[d][mk]}</td>')
        rows.append(f'<tr class="grand-subtotal" data-metric="{mk}">' + ''.join(sub) + '</tr>')
        wow = [
            '<td class="t grand-empty"></td>',
            '<td class="t grand-empty"></td>',
            '<td class="t grand-label wow-label">WoW</td>',
            f'<td class="wk-sum wow-cell">{fmt_wow(g_early[mk], g_pre[mk])}</td>',
            f'<td class="wk-sum wow-cell">{fmt_wow(g_mid[mk], g_early[mk])}</td>',
            f'<td class="wk-sum wow-cell">{fmt_wow(g_late[mk], g_mid[mk])}</td>',
        ]
        for d in daily_dates:
            wow.append(f'<td class="wow-cell" data-date="{d.strftime("%Y-%m-%d")}">{fmt_wow(g_daily[d][mk], g_pre_daily[d][mk])}</td>')
        rows.append(f'<tr class="grand-wow" data-metric="{mk}">' + ''.join(wow) + '</tr>')

    return (
        f'<table class="copy-table report-table" id="{table_id}">'
        '<thead>'
        '<tr>' + ''.join(h1) + '</tr>'
        '<tr>' + ''.join(h2) + '</tr>'
        '</thead>'
        '<tbody>' + ''.join(rows) + '</tbody>'
        '</table>'
    )


def _build_best10_table_html(cat_order, by_cat, dates, sales_map, days_back=30, source=None, table_id="best10Table"):
    """최근 N일 매출 기준 Best 10 SKU. 스티커 제외."""
    today = date.today()
    start = today - timedelta(days=days_back - 1)
    if dates:
        if start < dates[0]: start = dates[0]
        if today > dates[-1]: today = dates[-1]

    sku_totals = []
    for cat_name in cat_order:
        if "스티커" in cat_name:
            continue
        for s in by_cat.get(cat_name, []):
            code = s["card_code"]
            amt = qty = cnt = 0
            d = start
            while d <= today:
                e = sales_map.get((code, d.strftime("%Y-%m-%d")))
                amt += _val(e, source, "amount")
                qty += _val(e, source, "qty")
                cnt += _val(e, source, "cnt")
                d += timedelta(days=1)
            if amt > 0:
                sku_totals.append({"code": code, "name": s["name"], "category": cat_name,
                                   "amount": amt, "qty": qty, "cnt": cnt})
    sku_totals.sort(key=lambda x: -x["amount"])
    top10 = sku_totals[:10]
    total_period_amt = sum(s["amount"] for s in sku_totals)

    rows = []
    for i, s in enumerate(top10, 1):
        share = (s["amount"] / total_period_amt * 100) if total_period_amt > 0 else 0
        rows.append(
            f'<tr><td>{i}</td>'
            f'<td class="t">{s["category"]}</td>'
            f'<td class="t">{s["name"]}</td>'
            f'<td class="t">{s["code"]}</td>'
            f'<td>{s["amount"]:,}</td>'
            f'<td>{s["qty"]:,}</td>'
            f'<td>{s["cnt"]:,}</td>'
            f'<td>{share:.1f}%</td></tr>'
        )
    period_label = f"{start.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')} ({days_back}일)"
    return (
        f'<table class="copy-table" id="{table_id}">'
        f'<thead><tr><th>순위</th><th>카테고리</th><th>상품명</th><th>코드</th>'
        f'<th>매출</th><th>수량</th><th>주문수</th><th>점유율</th></tr></thead>'
        f'<tbody>' + ''.join(rows) + '</tbody>'
        f'<tfoot><tr><td colspan="8" style="text-align:left;color:#666;font-size:11px;padding:6px;">'
        f'기간 {period_label} · 스티커 제외 · 매출 발생 SKU 총 {len(sku_totals)}개 중 상위 10개 · 전체 매출 {total_period_amt:,}원</td></tr></tfoot>'
        f'</table>'
    )


def _build_category_trend_html(cat_order, by_cat, dates, sales_map, source=None, table_id="catTrendTable"):
    """카테고리 × 월 매출 매트릭스 + MoM."""
    months_set = set((d.year, d.month) for d in dates)
    months = sorted(months_set)

    cat_month_amt = defaultdict(lambda: defaultdict(int))
    cat_month_cnt = defaultdict(lambda: defaultdict(int))
    for cat_name in cat_order:
        for s in by_cat.get(cat_name, []):
            code = s["card_code"]
            for d in dates:
                ym = (d.year, d.month)
                e = sales_map.get((code, d.strftime("%Y-%m-%d")))
                cat_month_amt[cat_name][ym] += _val(e, source, "amount")
                cat_month_cnt[cat_name][ym] += _val(e, source, "cnt")

    grand_amt = {ym: 0 for ym in months}
    grand_cnt = {ym: 0 for ym in months}

    headers = ['<th>카테고리</th>', '<th>지표</th>']
    for y, m in months:
        headers.append(f'<th>{y}-{m:02d}</th>')
    headers.append('<th>합계</th>')

    rows = []
    for cat_name in cat_order:
        if not by_cat.get(cat_name):
            continue
        cat_total = sum(cat_month_amt[cat_name][ym] for ym in months)
        if cat_total == 0:
            continue
        # 매출 행
        amt_cells = [f'<td class="t cat-cell" rowspan="3">{cat_name}</td>',
                     '<td class="t metric-amount">매출</td>']
        for ym in months:
            v = cat_month_amt[cat_name][ym]
            grand_amt[ym] += v
            amt_cells.append(f'<td>{v:,}</td>')
        amt_cells.append(f'<td class="wk-sum"><b>{cat_total:,}</b></td>')
        rows.append('<tr>' + ''.join(amt_cells) + '</tr>')
        # MoM 행
        mom_cells = ['<td class="t wow-label">매출 MoM</td>']
        prev = None
        for ym in months:
            v = cat_month_amt[cat_name][ym]
            if prev is None or prev == 0:
                mom_cells.append('<td class="wow-cell"></td>')
            else:
                pct = (v - prev) / prev * 100
                sign = "+" if pct >= 0 else ""
                mom_cells.append(f'<td class="wow-cell">{sign}{pct:.1f}%</td>')
            prev = v
        mom_cells.append('<td class="wow-cell"></td>')
        rows.append('<tr>' + ''.join(mom_cells) + '</tr>')
        # 주문수 행
        cnt_total = sum(cat_month_cnt[cat_name][ym] for ym in months)
        cnt_cells = ['<td class="t metric-cnt">주문수</td>']
        for ym in months:
            v = cat_month_cnt[cat_name][ym]
            grand_cnt[ym] += v
            cnt_cells.append(f'<td>{v:,}</td>')
        cnt_cells.append(f'<td class="wk-sum"><b>{cnt_total:,}</b></td>')
        rows.append('<tr>' + ''.join(cnt_cells) + '</tr>')

    # 그랜드 행
    grand_total_amt = sum(grand_amt[ym] for ym in months)
    grand_total_cnt = sum(grand_cnt[ym] for ym in months)
    g_cells = ['<td class="t grand-label" rowspan="2">전체</td>', '<td class="t grand-label">매출 합계</td>']
    for ym in months:
        g_cells.append(f'<td class="grand-row">{grand_amt[ym]:,}</td>')
    g_cells.append(f'<td class="wk-sum grand-row"><b>{grand_total_amt:,}</b></td>')
    rows.append(f'<tr class="grand-total">' + ''.join(g_cells) + '</tr>')
    g_cnt_cells = ['<td class="t grand-label">주문수 합계</td>']
    for ym in months:
        g_cnt_cells.append(f'<td class="grand-row">{grand_cnt[ym]:,}</td>')
    g_cnt_cells.append(f'<td class="wk-sum grand-row"><b>{grand_total_cnt:,}</b></td>')
    rows.append(f'<tr class="grand-total">' + ''.join(g_cnt_cells) + '</tr>')

    return (
        f'<table class="copy-table" id="{table_id}">'
        f'<thead><tr>' + ''.join(headers) + f'</tr></thead>'
        f'<tbody>' + ''.join(rows) + f'</tbody>'
        f'</table>'
    )


def _build_invitation_link_html(cat_order, by_cat, dates, sales_map, table_id="invLinkTable"):
    """월별 청첩장 동반 vs 단독 부가상품 매출 + 동반 비율 (계절성 분석).
    스티커 제외. 결혼 성수기 vs 비수기 인사이트.
    """
    months_set = set((d.year, d.month) for d in dates)
    months = sorted(months_set)

    monthly = {ym: {"wi_amt": 0, "st_amt": 0, "wi_cnt": 0, "st_cnt": 0, "wi_qty": 0, "st_qty": 0}
               for ym in months}

    for cat_name in cat_order:
        if "스티커" in cat_name:
            continue
        for s in by_cat.get(cat_name, []):
            code = s["card_code"]
            for d in dates:
                ym = (d.year, d.month)
                e = sales_map.get((code, d.strftime("%Y-%m-%d")))
                if e:
                    monthly[ym]["wi_amt"] += e.get("wi", {}).get("amount", 0)
                    monthly[ym]["st_amt"] += e.get("st", {}).get("amount", 0)
                    monthly[ym]["wi_qty"] += e.get("wi", {}).get("qty", 0)
                    monthly[ym]["st_qty"] += e.get("st", {}).get("qty", 0)
                    monthly[ym]["wi_cnt"] += e.get("wi", {}).get("cnt", 0)
                    monthly[ym]["st_cnt"] += e.get("st", {}).get("cnt", 0)

    SEASON_MAP = {  # 결혼 성수기/비수기 추정 (월 기준)
        1: "비수기", 2: "비수기", 3: "보통", 4: "성수기", 5: "성수기", 6: "보통",
        7: "비수기", 8: "비수기", 9: "성수기", 10: "성수기", 11: "성수기", 12: "보통",
    }

    headers = ['<th>지표</th>']
    for y, m in months:
        season = SEASON_MAP.get(m, "")
        headers.append(f'<th>{y}-{m:02d}<br><small style="font-weight:normal;">{season}</small></th>')

    metrics = [
        ("청첩장 동반 매출", "wi_amt", "{:,}"),
        ("단독 매출", "st_amt", "{:,}"),
        ("합계 매출", "_total_amt", "{:,}"),
        ("동반 비율 (매출)", "_ratio_amt", "{:.1f}%"),
        ("청첩장 동반 주문수", "wi_cnt", "{:,}"),
        ("단독 주문수", "st_cnt", "{:,}"),
        ("합계 주문수", "_total_cnt", "{:,}"),
        ("동반 비율 (주문수)", "_ratio_cnt", "{:.1f}%"),
    ]

    def get_metric(mm, key):
        if key == "_total_amt": return mm["wi_amt"] + mm["st_amt"]
        if key == "_total_cnt": return mm["wi_cnt"] + mm["st_cnt"]
        if key == "_ratio_amt":
            t = mm["wi_amt"] + mm["st_amt"]
            return (mm["wi_amt"] / t * 100) if t > 0 else 0
        if key == "_ratio_cnt":
            t = mm["wi_cnt"] + mm["st_cnt"]
            return (mm["wi_cnt"] / t * 100) if t > 0 else 0
        return mm.get(key, 0)

    rows = []
    for label, key, fmt in metrics:
        cls = "grand-total" if "합계" in label else ("cat-subtotal" if "비율" in label else "")
        cells = [f'<td class="t" style="text-align:left;font-weight:600;">{label}</td>']
        for ym in months:
            v = get_metric(monthly[ym], key)
            try:
                s = fmt.format(v)
            except Exception:
                s = str(v)
            cells.append(f'<td>{s}</td>')
        rows.append(f'<tr class="{cls}">' + ''.join(cells) + '</tr>')

    return (
        f'<table class="copy-table" id="{table_id}">'
        f'<thead><tr>' + ''.join(headers) + f'</tr></thead>'
        f'<tbody>' + ''.join(rows) + f'</tbody>'
        f'<tfoot><tr><td colspan="{len(months)+1}" style="text-align:left;color:#666;font-size:11px;padding:8px;">'
        f'<b>해석 가이드:</b> 동반 비율 = 청첩장과 함께 산 매출 / 전체 부가상품 매출 × 100. '
        f'성수기(4·5·9·10·11월)에 동반 비율이 높을수록 청첩장 cross-sell이 잘 되고 있음. '
        f'비수기에 단독 매출이 차지하는 비중이 높다면 채널 분리(바른손몰 등)의 기여가 큼.'
        f'</td></tr></tfoot>'
        f'</table>'
    )


def _render_html(categories, cat_order, by_cat, dates, weeks, week_list, wk_num_map, sales_map):
    cat_styles = {c["name"]: c for c in categories}
    period = f"{dates[0].strftime('%Y/%m/%d')} ~ {dates[-1].strftime('%Y/%m/%d')}"
    today = date.today()

    # 월별 마지막 주차 매핑 (date_range 안의 마지막 일자가 속한 주차)
    month_last_week = {}  # (year, month) -> week_start (sunday)
    for d in dates:
        key = (d.year, d.month)
        ws_d = d - timedelta(days=sunday_offset(d))
        if key not in month_last_week or ws_d > month_last_week[key]:
            month_last_week[key] = ws_d
    # 주차별로 끝나는 월들 매핑 (한 주에 여러 월이 끝날 수도 있음 — 일반적으론 0~1)
    months_ending_at_ws = defaultdict(list)
    for (y, m), ws_end in month_last_week.items():
        months_ending_at_ws[ws_end].append((y, m))

    # --- colgroup (열 너비 확정) ---
    col_tags = ['<col class="col-num">', '<col class="col-name">', '<col class="col-code">']
    for ws in week_list:
        wn = wk_num_map[ws]
        for _ in weeks[ws]:
            col_tags.append(f'<col class="col-day" data-wk="{wn}">')
        col_tags.append(f'<col class="col-wksum" data-wk="{wn}">')
        col_tags.append(f'<col class="col-wow" data-wk="{wn}">')
        for (y, m) in months_ending_at_ws.get(ws, []):
            col_tags.append(f'<col class="col-monthsum" data-month="{y:04d}-{m:02d}">')

    # --- 헤더 ---
    week_hdr, day_hdr = [], []
    for ws in week_list:
        ds = weeks[ws]
        we = ws + timedelta(days=6)
        wn = wk_num_map[ws]
        # week-hdr colspan = 일자 + 소계 + WoW
        week_hdr.append(
            f'<th colspan="{len(ds) + 2}" class="wk-hdr" data-wk="{wn}">'
            f'<button class="wk-fold" onclick="toggleWeek({wn})" title="접기/펼치기">▼</button> '
            f'W.{wn}<div class="small">{ws.strftime("%m/%d")}~{we.strftime("%m/%d")}</div>'
            f'</th>'
        )
        for d in ds:
            cls = "day"
            if d.weekday() >= 5:
                cls += " weekend"
            if d == today:
                cls += " today"
            day_hdr.append(
                f'<th class="{cls}" data-wk="{wn}">'
                f'<div class="wd">{WEEKDAY_KR[d.weekday()]}</div>'
                f'<div class="dt">{d.strftime("%m/%d")}</div>'
                f'</th>'
            )
        day_hdr.append(f'<th class="wk-sum-hdr" data-wk="{wn}">소계</th>')
        day_hdr.append(f'<th class="wk-wow-hdr" data-wk="{wn}">WoW</th>')
        # 월 마감 헤더
        for (y, m) in months_ending_at_ws.get(ws, []):
            week_hdr.append(
                f'<th rowspan="2" class="month-sum-hdr" data-month="{y:04d}-{m:02d}">'
                f'{m}월<br>마감</th>'
            )

    # --- 본문 ---
    body_rows = []
    sku_num = 0
    grand = defaultdict(lambda: {"amount": 0, "qty": 0, "cnt": 0})

    def _row_cells(per_day_lookup, css_day, css_wksum, css_monthsum, day_extra_attr=""):
        """한 행의 모든 셀(일자/소계/WoW/월마감) HTML 생성.
        per_day_lookup(d) -> {amount,qty,cnt} 닥셔너리 반환하는 함수.
        반환: (cells_html_list, row_total_amount)
        """
        # 월별 누적 (정확한 행 단위 합계)
        monthly = defaultdict(lambda: {"amount": 0, "qty": 0, "cnt": 0})
        for d in dates:
            data = per_day_lookup(d) or {"amount": 0, "qty": 0, "cnt": 0}
            mk = (d.year, d.month)
            for k in ("amount", "qty", "cnt"):
                monthly[mk][k] += data.get(k, 0)

        cells = []
        prev_wk_amt = None
        row_total = 0
        for ws in week_list:
            wn = wk_num_map[ws]
            wk_sum = {"amount": 0, "qty": 0, "cnt": 0}
            for d in weeks[ws]:
                data = per_day_lookup(d) or {"amount": 0, "qty": 0, "cnt": 0}
                for k in ("amount", "qty", "cnt"):
                    wk_sum[k] += data.get(k, 0)
                cls = css_day
                if data.get("amount", 0) > 0:
                    cls += " has"
                if d.weekday() >= 5:
                    cls += " weekend"
                if d == today:
                    cls += " today"
                cells.append(
                    f'<td class="{cls}" data-wk="{wn}"{day_extra_attr}>'
                    f'{_metric_spans(data["amount"], data["qty"], data["cnt"])}'
                    f'</td>'
                )
            row_total += wk_sum["amount"]
            cells.append(
                f'<td class="{css_wksum}" data-wk="{wn}"{day_extra_attr}>'
                f'{_metric_spans(wk_sum["amount"], wk_sum["qty"], wk_sum["cnt"])}'
                f'</td>'
            )
            # WoW 셀
            cells.append(_wow_cell(wk_sum["amount"], prev_wk_amt, wn))
            prev_wk_amt = wk_sum["amount"]

            # 월 마감 셀 (이 주차에서 끝나는 월들)
            for (y, m) in months_ending_at_ws.get(ws, []):
                ms = monthly.get((y, m), {"amount": 0, "qty": 0, "cnt": 0})
                cells.append(
                    f'<td class="{css_monthsum}" data-month="{y:04d}-{m:02d}"{day_extra_attr}>'
                    f'{_metric_spans(ms["amount"], ms["qty"], ms["cnt"])}'
                    f'</td>'
                )

        return cells, row_total

    for cat_name in cat_order:
        skus = by_cat.get(cat_name, [])
        if not skus:
            continue
        style = cat_styles.get(cat_name, {})
        bg = style.get("bg", "#EEEEEE")
        color = style.get("color", "#333333")
        icon = style.get("icon", "📦")

        # 카테고리 일자별 합계
        cat_daily = defaultdict(lambda: {"amount": 0, "qty": 0, "cnt": 0})
        for s in skus:
            for d in dates:
                e = sales_map.get((s["card_code"], d.strftime("%Y-%m-%d")))
                if e:
                    for k in ("amount", "qty", "cnt"):
                        cat_daily[d][k] += e[k]
                        grand[d][k] += e[k]

        cat_cells, _ = _row_cells(
            lambda d: cat_daily.get(d),
            css_day="cat-cell", css_wksum="cat-wksum", css_monthsum="cat-monthsum",
            day_extra_attr=f' style="background:{bg}"',
        )

        body_rows.append(
            f'<tr class="cat-hdr" data-cat="{cat_name}">'
            f'<td colspan="3" class="cat-label" style="background:{bg};color:{color}">'
            f'<span class="ico">{icon}</span> <b>{cat_name}</b> '
            f'<span class="cnt">({len(skus)} SKU)</span> '
            f'<button class="fold" onclick="toggleCat(this,\'{cat_name}\')">▼</button>'
            f'</td>'
            + "".join(cat_cells)
            + "</tr>"
        )

        for s in skus:
            sku_num += 1
            code = s["card_code"]
            name = s["name"]
            disc = s.get("discontinued", False)

            sku_cells, sku_total = _row_cells(
                lambda d, _code=code: sales_map.get((_code, d.strftime("%Y-%m-%d"))),
                css_day="cell", css_wksum="wk-sum", css_monthsum="month-sum",
            )

            row_cls = "sku-row" if sku_total > 0 else "sku-row zero"
            if disc:
                row_cls += " discontinued"
            disc_badge = '<span class="disc-badge">단종</span> ' if disc else ''
            body_rows.append(
                f'<tr class="{row_cls}" data-cat="{cat_name}" data-code="{code}">'
                f'<td class="num">{sku_num}</td>'
                f'<td class="name" title="{name}">{disc_badge}{name}</td>'
                f'<td class="code">{code}</td>'
                + "".join(sku_cells)
                + "</tr>"
            )

    # --- 전체 합계 행 ---
    grand_cells, grand_total_amt = _row_cells(
        lambda d: grand.get(d),
        css_day="grand-cell", css_wksum="grand-wksum", css_monthsum="grand-monthsum",
    )
    grand_row = (
        '<tr class="grand">'
        '<td colspan="3" class="grand-label">💰 전체 합계</td>'
        + "".join(grand_cells) + "</tr>"
    )

    copy_full_html = _build_copy_table_html(cat_order, by_cat, dates, sales_map, source=None, table_id="copyTable-full")
    copy_wi_html   = _build_copy_table_html(cat_order, by_cat, dates, sales_map, source="wi", table_id="copyTable-wi")
    copy_st_html   = _build_copy_table_html(cat_order, by_cat, dates, sales_map, source="st", table_id="copyTable-st")
    report_full_html = _build_report_table_html(cat_order, by_cat, dates, sales_map, source=None, table_id="reportTable-full")
    report_wi_html   = _build_report_table_html(cat_order, by_cat, dates, sales_map, source="wi", table_id="reportTable-wi")
    report_st_html   = _build_report_table_html(cat_order, by_cat, dates, sales_map, source="st", table_id="reportTable-st")
    best10_html    = _build_best10_table_html(cat_order, by_cat, dates, sales_map, days_back=30, source=None, table_id="best10Table")
    cat_trend_html = _build_category_trend_html(cat_order, by_cat, dates, sales_map, source=None, table_id="catTrendTable")
    inv_link_html  = _build_invitation_link_html(cat_order, by_cat, dates, sales_map, table_id="invLinkTable")

    sync_info = _read_sync_status()
    html = _build_page(
        col_tags, week_hdr, day_hdr, body_rows, grand_row,
        period, sku_num, len(sales_map), grand_total_amt, sync_info,
        copy_full_html, copy_wi_html, copy_st_html, dates,
        report_full_html, report_wi_html, report_st_html,
        best10_html, cat_trend_html, inv_link_html,
    )
    return html


def _read_sync_status():
    """홈페이지 동기화 상태 헤더용. 파일 없으면 None."""
    if not os.path.exists(SYNC_STATUS_FILE):
        return None
    try:
        with open(SYNC_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _metric_spans(amount, qty, cnt):
    if not (amount or qty or cnt):
        return ""
    return (
        f'<span class="m amt">{fmt_n(amount)}</span>'
        f'<span class="m qty">{fmt_n(qty)}</span>'
        f'<span class="m cnt">{fmt_n(cnt)}</span>'
    )


def _wow_cell(curr_amt, prev_amt, wn):
    """WoW(전주 대비) 셀 HTML 반환. prev=None(첫 주차)은 빈 셀, prev=0 & curr>0은 '신규'."""
    if prev_amt is None:
        return f'<td class="wk-wow" data-wk="{wn}"></td>'
    if not prev_amt and not curr_amt:
        return f'<td class="wk-wow flat" data-wk="{wn}">—</td>'
    if not prev_amt and curr_amt:
        return f'<td class="wk-wow new" data-wk="{wn}">신규</td>'
    if not curr_amt and prev_amt:
        return f'<td class="wk-wow down" data-wk="{wn}">▼ -100%</td>'
    pct = (curr_amt - prev_amt) / prev_amt * 100
    if pct > 0.5:
        return f'<td class="wk-wow up" data-wk="{wn}">▲ +{pct:.0f}%</td>'
    elif pct < -0.5:
        return f'<td class="wk-wow down" data-wk="{wn}">▼ {pct:.0f}%</td>'
    else:
        return f'<td class="wk-wow flat" data-wk="{wn}">≈ {pct:+.0f}%</td>'


def _build_page(col_tags, week_hdr, day_hdr, body_rows, grand_row,
                period, sku_num, rec_count, grand_total_amt, sync_info=None,
                copy_full_html="", copy_wi_html="", copy_st_html="", dates=None,
                report_full_html="", report_wi_html="", report_st_html="",
                best10_html="", cat_trend_html="", inv_link_html=""):
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    col_html = "".join(col_tags)
    wk_html = "".join(week_hdr)
    day_html = "".join(day_hdr)
    body_html = "".join(body_rows)

    # 데일리 복사용 날짜 옵션 (역순 — 최근 날짜가 위로)
    date_opts_html = ""
    if dates:
        for d in reversed(dates):
            d_str = d.strftime("%Y-%m-%d")
            wd = WEEKDAY_KR[d.weekday()]
            label = f'{d.strftime("%m/%d")}({wd})'
            date_opts_html += f'<option value="{d_str}">{label}</option>'

    # 동기화 상태 배지
    if sync_info and sync_info.get("last_sync"):
        ls = sync_info["last_sync"][:16].replace("T", " ")
        ok = sync_info.get("ok", True)
        new_p = sync_info.get("new_products_count", 0)
        new_c = sync_info.get("new_categories_count", 0)
        disc = sync_info.get("discontinued_count", 0)
        chg_parts = []
        if new_p: chg_parts.append(f"신규 {new_p}")
        if new_c: chg_parts.append(f"신규카테고리 {new_c}")
        if disc:  chg_parts.append(f"단종 {disc}")
        chg_text = " · ".join(chg_parts) if chg_parts else "변경 없음"
        cls = "sync-ok" if ok else "sync-err"
        sync_badge = (f'<span class="sync-badge {cls}" title="홈페이지 자동 동기화">'
                      f'🔄 {ls} · {chg_text}</span>')
    else:
        sync_badge = '<span class="sync-badge sync-warn" title="아직 동기화 미실행">🔄 동기화 대기</span>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>기념굿즈 SKU별 일일 매출 · {period}</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI','Malgun Gothic',sans-serif; background:#f5f6f8; margin:0; padding:16px; color:#222; font-size:12px; }}
  h1 {{ margin:0 0 4px; font-size:20px; }}
  .sub {{ color:#666; margin-bottom:10px; font-size:12px; }}
  .toolbar {{ margin-bottom:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  .toolbar button {{ padding:5px 12px; border:1px solid #bbb; background:white; border-radius:4px; cursor:pointer; font-size:12px; }}
  .toolbar button:hover {{ background:#eef; }}
  .toolbar button.active {{ background:#233243; color:white; border-color:#233243; }}
  .metric-group {{ display:inline-flex; border:1px solid #aaa; border-radius:4px; overflow:hidden; }}
  .metric-group button {{ border:none; border-radius:0; border-right:1px solid #ddd; }}
  .metric-group button:last-child {{ border-right:none; }}
  .wrap {{ overflow:auto; border:1px solid #ddd; background:white; max-height:calc(100vh - 120px); }}
  table {{ border-collapse:separate; border-spacing:0; table-layout:fixed; width:max-content; white-space:nowrap; background:white; }}
  th, td {{ border-right:1px solid #e3e3e3; border-bottom:1px solid #e3e3e3; padding:3px 6px; text-align:center; vertical-align:middle; }}

  /* ===== colgroup width ===== */
  col.col-num    {{ width:40px; }}
  col.col-name   {{ width:200px; }}
  col.col-code   {{ width:150px; }}
  col.col-day    {{ width:78px; }}
  col.col-wksum  {{ width:84px; }}

  /* ===== 상단 헤더 2행 (JS가 top 동적 주입) ===== */
  thead th {{ color:white; font-weight:600; background:#233243; }}
  thead tr.h-week th {{ position:sticky; top:0; z-index:5; }}
  thead tr.h-week th.wk-hdr {{ background:#3c74a8; }}
  thead tr.h-day th {{ position:sticky; z-index:5; }}
  th.wk-sum-hdr {{ background:#555; }}
  th.wk-hdr .small {{ font-size:10px; color:#d0e0f0; font-weight:normal; display:block; }}
  th.wk-hdr .wk-fold {{ background:rgba(255,255,255,0.15); color:white; border:1px solid rgba(255,255,255,0.3); border-radius:3px; font-size:10px; padding:1px 5px; cursor:pointer; }}
  th.wk-hdr .wk-fold:hover {{ background:rgba(255,255,255,0.3); }}

  /* ===== 컬럼 스타일 ===== */
  .num   {{ color:#999; }}
  .name  {{ text-align:left; font-weight:600; overflow:hidden; text-overflow:ellipsis; }}
  .code  {{ color:#666; font-family:Consolas,monospace; font-size:11px; text-align:left; overflow:hidden; text-overflow:ellipsis; }}
  .wk-sum, .wk-sum-hdr, .cat-wksum, .grand-wksum {{ background:#fafae0; font-weight:600; }}

  /* ===== 주말/오늘 강조 ===== */
  tbody td.weekend {{ background:#f7f7f7; }}
  tbody td.weekend.has {{ background:#e0efe0; }}
  tbody .today {{ background:#fff8e1 !important; }}
  thead th.weekend .wd {{ color:#ffd180; }}
  thead th.weekend .dt {{ color:#ffecb3; }}
  thead th.today {{ background:#ff9800 !important; }}
  thead th.today .wd, thead th.today .dt {{ color:white !important; font-weight:700; }}
  .wd {{ font-size:10px; color:#cfd8dc; }}
  .dt {{ font-size:12px; }}

  /* ===== 데이터 셀 ===== */
  td.cell {{ color:#bbb; }}
  td.cell.has {{ background:#e8f0fe; color:#222; }}

  /* 3지표 동시 표시 (세로 적층) — view-amount/qty/cnt는 필터 모드 */
  .m {{ display:block; line-height:1.3; }}
  .m.amt {{ font-weight:700; font-size:12px; color:#1a53ff; }}
  .m.qty {{ font-weight:600; font-size:11px; color:#2e7d32; }}
  .m.cnt {{ font-weight:600; font-size:11px; color:#6a1b9a; }}
  /* 빈 값(""만 있는 span)은 자리 안 차지 */
  .m:empty {{ display:none; }}

  /* ===== 숫자 컬럼 정렬 통일 ===== */
  td.cell, td.wk-sum, td.cat-cell, td.cat-wksum, td.grand-cell, td.grand-wksum,
  td.month-sum, td.cat-monthsum, td.grand-monthsum {{
    text-align:right; padding-right:8px; vertical-align:top;
  }}

  /* ===== WoW 컬럼 ===== */
  col.col-wow {{ width:60px; }}
  th.wk-wow-hdr {{ background:#444; }}
  td.wk-wow {{ background:#f0f4ff; font-size:11px; font-weight:700; text-align:center;
                vertical-align:middle; padding:3px 4px; }}
  td.wk-wow.up   {{ color:#0a8a3e; }}
  td.wk-wow.down {{ color:#c92a2a; }}
  td.wk-wow.flat {{ color:#999; }}
  td.wk-wow.new  {{ color:#e67e22; font-size:10px; }}

  /* ===== 월 마감 컬럼 ===== */
  col.col-monthsum {{ width:90px; }}
  th.month-sum-hdr {{ background:#1a4480; color:#fff; font-size:11px; }}
  td.month-sum, td.cat-monthsum, td.grand-monthsum {{
    background:#fff3d6; font-weight:700;
    border-left:2px solid #b88500; border-right:2px solid #b88500;
  }}
  td.cat-monthsum {{ background:#fde8a4; }}
  td.grand-monthsum {{ background:#f8c447; color:#5a3c00; }}

  /* ===== 3지표 표시 토글 (필터 모드: 한 가지만 보기) ===== */
  body.view-amount td .m.qty, body.view-amount td .m.cnt {{ display:none; }}
  body.view-qty    td .m.amt, body.view-qty    td .m.cnt {{ display:none; }}
  body.view-cnt    td .m.amt, body.view-cnt    td .m.qty {{ display:none; }}

  /* ===== 주차 접기 (col-hidden 클래스) ===== */
  col.col-hidden {{ visibility:collapse; }}
  td.col-hidden, th.col-hidden {{ display:none; }}

  /* ===== 카테고리 헤더 행 ===== */
  tr.cat-hdr {{ border-top:2px solid #888; }}
  tr.cat-hdr td {{ padding:6px 8px; font-size:12px; }}
  tr.cat-hdr .cat-label {{ text-align:left; font-size:13px; }}
  tr.cat-hdr .ico {{ font-size:14px; margin-right:4px; }}
  tr.cat-hdr .cnt {{ color:#555; font-weight:normal; margin-left:6px; font-size:11px; }}
  tr.cat-hdr .fold {{ margin-left:8px; border:none; background:transparent; cursor:pointer; font-size:11px; color:#555; }}
  tr.cat-hdr td.cat-cell {{ text-align:right; font-weight:600; font-size:11px; }}
  tr.cat-hdr td.cat-wksum {{ font-weight:700; color:#5a3c00; text-align:right; font-size:11px; }}

  /* ===== SKU 행 ===== */
  tr.sku-row td {{ transition:background 0.1s; }}
  tr.sku-row.zero td {{ color:#ccc; }}
  tr.sku-row.zero td.name {{ color:#aaa; }}
  tr.sku-row:hover td:not(.num):not(.name):not(.code) {{ background:#fff3cd; }}
  tr.hidden {{ display:none; }}

  /* ===== 단종 상품 ===== */
  tr.sku-row.discontinued td.num,
  tr.sku-row.discontinued td.name,
  tr.sku-row.discontinued td.code {{ background:#f0e6e6 !important; }}
  tr.sku-row.discontinued td.name {{ text-decoration:line-through; color:#999 !important; }}
  tr.sku-row.discontinued td.code {{ color:#b8a0a0 !important; }}
  .disc-badge {{ display:inline-block; background:#999; color:white; font-size:9px; font-weight:700;
                  padding:1px 5px; border-radius:3px; margin-right:4px; vertical-align:middle;
                  text-decoration:none !important; }}

  /* ===== 동기화 상태 배지 ===== */
  .sync-badge {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px;
                  font-weight:600; margin-left:8px; }}
  .sync-badge.sync-ok   {{ background:#e8f5e9; color:#2e7d32; border:1px solid #a5d6a7; }}
  .sync-badge.sync-warn {{ background:#fff3e0; color:#e65100; border:1px solid #ffcc80; }}
  .sync-badge.sync-err  {{ background:#ffebee; color:#c62828; border:1px solid #ef9a9a; }}

  /* ===== 전체 합계 (하단 sticky) ===== */
  tr.grand {{ border-top:2px solid #333; }}
  tr.grand td {{ position:sticky; bottom:0; z-index:4; background:#fff8d6; font-size:12px; font-weight:700; }}
  tr.grand td.grand-label {{ text-align:left; color:#c77700; font-size:13px; }}
  tr.grand td.grand-wksum {{ background:#f0d070; color:#5a3c00; }}

  /* ===== 좌측 3열 고정 (white bg, z-index) ===== */
  td.num, td.name, td.code {{
    position:sticky;
    background:white;
    z-index:2;
  }}
  td.num  {{ left:0; }}
  td.name {{ left:40px; }}
  td.code {{ left:240px; }}
  tr.sku-row.zero td.num,
  tr.sku-row.zero td.name,
  tr.sku-row.zero td.code {{ background:#fafafa; }}
  tr.sku-row:hover td.num,
  tr.sku-row:hover td.name,
  tr.sku-row:hover td.code {{ background:#fff8e1; }}

  /* 헤더 좌측 3열 코너 */
  thead th.num,
  thead th.name,
  thead th.code {{
    position:sticky;
    top:0;
    z-index:7 !important;
    background:#233243 !important;
  }}
  thead th.num  {{ left:0; }}
  thead th.name {{ left:40px; }}
  thead th.code {{ left:240px; }}

  /* 카테고리 라벨 (colspan=3) 좌측 고정 */
  tr.cat-hdr td.cat-label {{
    position:sticky;
    left:0;
    z-index:3;
    border-right:2px solid rgba(0,0,0,0.2);
  }}

  /* 전체합계 좌측 라벨 */
  tr.grand td.grand-label {{
    position:sticky;
    left:0;
    bottom:0;
    z-index:6;
    background:#fff8d6;
    border-right:2px solid rgba(0,0,0,0.2);
  }}

  /* 좌측 3열과 데이터 경계 강조 */
  td.code {{ border-right:2px solid #b0b0b0; }}
  thead th.code {{ border-right:2px solid #000 !important; }}

  /* ===== 구글시트 복사용 표 ===== */
  .copy-section {{ margin-top:24px; padding-top:16px; border-top:2px dashed #aaa; }}
  .copy-section h2 {{ font-size:15px; margin:0 0 6px; color:#233243; }}
  .copy-section .hint {{ color:#666; font-size:11px; margin-bottom:8px; }}
  .copy-section .copy-toolbar {{ margin-bottom:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  .copy-section .copy-toolbar button {{ padding:6px 14px; border:1px solid #233243; background:#233243; color:white; border-radius:4px; cursor:pointer; font-size:12px; font-weight:600; }}
  .copy-section .copy-toolbar button:hover {{ background:#3c74a8; border-color:#3c74a8; }}
  .copy-section .copy-toolbar button.secondary {{ background:white; color:#233243; }}
  .copy-section .copy-toolbar button.secondary:hover {{ background:#eef; }}
  .copy-section .copy-toolbar .ok-msg {{ color:#0a8a3e; font-size:11px; font-weight:600; }}
  .copy-wrap {{ overflow:auto; border:1px solid #bbb; background:white; max-height:520px; }}
  .copy-wrap.collapsed {{ display:none; }}
  table.copy-table {{ border-collapse:collapse; font-size:11px; font-family:'Segoe UI','Malgun Gothic',sans-serif; }}
  table.copy-table th, table.copy-table td {{ border:1px solid #ccc; padding:3px 6px; text-align:right; white-space:nowrap; }}
  table.copy-table th {{ background:#f0f0f0; color:#222; font-weight:600; }}
  table.copy-table thead tr:first-child th {{ position:sticky; top:0; z-index:3; background:#dde6ef; }}
  table.copy-table thead tr:nth-child(2) th {{ position:sticky; top:28px; z-index:2; }}
  table.copy-table th.wk-grp {{ background:#3c74a8; color:white; }}
  table.copy-table th.wk-sum-hdr, table.copy-table td.wk-sum {{ background:#fafae0; font-weight:600; }}
  table.copy-table td.t {{ text-align:left; }}
  table.copy-table td.cat-cell {{ background:#e8eef5; font-weight:700; vertical-align:middle; text-align:center; }}
  table.copy-table td.metric-amount {{ color:#1a53ff; font-weight:600; }}
  table.copy-table td.metric-qty    {{ color:#2e7d32; font-weight:600; }}
  table.copy-table td.metric-cnt    {{ color:#6a1b9a; font-weight:600; }}
  table.copy-table tbody tr:hover td {{ background:#fff8e1; }}
  /* 그랜드 합계 + WoW 행 */
  table.copy-table tr.grand-total td {{ background:#fff3d6; font-weight:700; border-top:2px solid #b88500; }}
  table.copy-table tr.grand-total td.wk-sum {{ background:#ffe9a8; }}
  table.copy-table tr.grand-total td.grand-label {{ text-align:left; color:#5a3c00; }}
  table.copy-table tr.grand-wow td {{ background:#f5f5f5; font-size:10px; color:#555; }}
  table.copy-table tr.grand-wow td.wow-label {{ text-align:left; color:#888; font-style:italic; }}

  /* ===== 주간 보고용 표 (report-table) — 카테고리 소계 / 그랜드 / WoW ===== */
  table.copy-table tr.cat-subtotal td {{ background:#dde6ef; font-weight:700; border-top:1px solid #7d96b3; }}
  table.copy-table tr.cat-subtotal td.wk-sum {{ background:#b6c8de; }}
  table.copy-table tr.cat-subtotal td.cat-sub-label {{ text-align:left; color:#1a3b66; font-size:12px; }}
  table.copy-table tr.cat-wow td {{ background:#eef2f7; font-size:10px; color:#555; }}
  table.copy-table tr.cat-wow td.cat-sub-label {{ text-align:left; color:#5a7faf; font-style:italic; }}
  table.copy-table tr.grand-subtotal td {{ background:#fff3d6; font-weight:800; border-top:2px solid #b88500; font-size:12px; }}
  table.copy-table tr.grand-subtotal td.wk-sum {{ background:#ffe9a8; }}
  table.copy-table tr.grand-subtotal td.grand-label {{ text-align:left; color:#5a3c00; }}
  table.copy-table td.cat-sub-empty, table.copy-table td.grand-empty {{ background:white; border-right:none; border-bottom:none; }}
  /* WoW 색상 (양수/음수) */
  table.copy-table td.wow-cell:not(:empty) {{ font-weight:600; }}
  .report-section h2 {{ color:#1a3b66; }}

  /* ===== 탭 ===== */
  .copy-section .tabs {{ display:flex; gap:0; margin-bottom:0; border-bottom:2px solid #233243; }}
  .copy-section .tab-btn {{ padding:8px 18px; border:1px solid #aaa; border-bottom:none; background:#f0f0f0; color:#333; cursor:pointer; font-size:12px; font-weight:600; border-radius:4px 4px 0 0; margin-right:2px; }}
  .copy-section .tab-btn:hover {{ background:#e3e9f0; }}
  .copy-section .tab-btn.active {{ background:#233243; color:white; border-color:#233243; }}
  .copy-section .tab-panel {{ display:none; padding-top:10px; }}
  .copy-section .tab-panel.active {{ display:block; }}
  .insights-section h2 {{ color:#2e7d32; }}
</style>
</head>
<body class="view-all">
<h1>기념굿즈 SKU별 일일 매출</h1>
<div class="sub">기간 {period} · 생성 {gen_time} · SKU {sku_num}개 · 매출 레코드 {rec_count}행 · 전체 매출 {grand_total_amt:,}원 &nbsp; {sync_badge}</div>
<div class="toolbar">
  <div class="metric-group">
    <button id="m-all"    class="active" onclick="setMetric('all')">📊 전체</button>
    <button id="m-amount" onclick="setMetric('amount')">💰 매출만</button>
    <button id="m-qty"    onclick="setMetric('qty')">📦 수량만</button>
    <button id="m-cnt"    onclick="setMetric('cnt')">🧾 주문수만</button>
  </div>
  <button id="btnZero" onclick="toggleZero()">매출 0 SKU 숨기기</button>
  <button onclick="expandAll()">전체 표시</button>
  <span style="color:#777;font-size:11px;margin-left:6px;">※ 주차 헤더 <b>▼</b>로 주 단위 접기, 카테고리 <b>▼</b>로 그룹 접기</span>
</div>
<div class="wrap">
<table>
  <colgroup>{col_html}</colgroup>
  <thead>
    <tr class="h-week">
      <th class="num">#</th>
      <th class="name">상품명</th>
      <th class="code">상품코드</th>
      {wk_html}
    </tr>
    <tr class="h-day">
      <th class="num"></th>
      <th class="name"></th>
      <th class="code"></th>
      {day_html}
    </tr>
  </thead>
  <tbody>
    {body_html}
    {grand_row}
  </tbody>
</table>
</div>

<div class="copy-section report-section">
  <h2>📊 주간 보고용 표 (최근 3주차)</h2>
  <div class="hint">스티커 제외, 3주간 매출 발생 상품만. 매주 자동 rolling. 탭으로 전체/동반/단독 전환.</div>
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab(this,'report-full')">전체</button>
    <button class="tab-btn" onclick="showTab(this,'report-wi')">청첩장 동반</button>
    <button class="tab-btn" onclick="showTab(this,'report-st')">단독 주문</button>
  </div>
  <div class="tab-panel active" id="report-full">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('reportTable-full','reportMsgFull')">📋 TSV 복사</button>
      <button class="secondary" onclick="selectTable('reportTable-full','reportMsgFull')">표 전체 선택</button>
      <span class="ok-msg" id="reportMsgFull"></span>
    </div>
    <div class="copy-wrap">{report_full_html}</div>
  </div>
  <div class="tab-panel" id="report-wi">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('reportTable-wi','reportMsgWI')">📋 TSV 복사</button>
      <button class="secondary" onclick="selectTable('reportTable-wi','reportMsgWI')">표 전체 선택</button>
      <span class="ok-msg" id="reportMsgWI"></span>
    </div>
    <div class="copy-wrap">{report_wi_html}</div>
  </div>
  <div class="tab-panel" id="report-st">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('reportTable-st','reportMsgST')">📋 TSV 복사</button>
      <button class="secondary" onclick="selectTable('reportTable-st','reportMsgST')">표 전체 선택</button>
      <span class="ok-msg" id="reportMsgST"></span>
    </div>
    <div class="copy-wrap">{report_st_html}</div>
  </div>
</div>

<div class="copy-section">
  <h2>📋 구글시트 복사용 표 (전체 기간)</h2>
  <div class="hint">매일 업데이트용 날짜별 1열 복사 지원. 탭으로 전체/동반/단독 전환.</div>
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab(this,'copy-full')">전체</button>
    <button class="tab-btn" onclick="showTab(this,'copy-wi')">청첩장 동반</button>
    <button class="tab-btn" onclick="showTab(this,'copy-st')">단독 주문</button>
  </div>
  <div class="tab-panel active" id="copy-full">
    <div class="copy-toolbar">
      <span style="font-size:11px;color:#555;margin-right:4px;"><b>초기 1회용:</b></span>
      <button onclick="copyTableTSV('copyTable-full','copyMsgFull')">📋 전체 표 TSV 복사</button>
      <button class="secondary" onclick="selectTable('copyTable-full','copyMsgFull')">표 전체 선택</button>
    </div>
    <div class="copy-toolbar" style="margin-top:6px;">
      <span style="font-size:11px;color:#555;margin-right:4px;"><b>매일 업데이트용:</b></span>
      <label style="font-size:11px;">날짜 <select id="selDate-full">{date_opts_html}</select></label>
      <label style="font-size:11px;">지표
        <select id="selMetric-full">
          <option value="all">매출+수량+주문수</option>
          <option value="amount">매출만</option>
          <option value="qty">수량만</option>
          <option value="cnt">주문수만</option>
        </select>
      </label>
      <button onclick="copyDateColumn('copyTable-full','selDate-full','selMetric-full','copyMsgFull')">📅 이 날짜만 복사</button>
      <span class="ok-msg" id="copyMsgFull"></span>
    </div>
    <div class="copy-wrap">{copy_full_html}</div>
  </div>
  <div class="tab-panel" id="copy-wi">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('copyTable-wi','copyMsgWI')">📋 전체 표 TSV 복사</button>
      <button class="secondary" onclick="selectTable('copyTable-wi','copyMsgWI')">표 전체 선택</button>
    </div>
    <div class="copy-toolbar" style="margin-top:6px;">
      <label style="font-size:11px;">날짜 <select id="selDate-wi">{date_opts_html}</select></label>
      <label style="font-size:11px;">지표
        <select id="selMetric-wi">
          <option value="all">매출+수량+주문수</option>
          <option value="amount">매출만</option>
          <option value="qty">수량만</option>
          <option value="cnt">주문수만</option>
        </select>
      </label>
      <button onclick="copyDateColumn('copyTable-wi','selDate-wi','selMetric-wi','copyMsgWI')">📅 이 날짜만 복사</button>
      <span class="ok-msg" id="copyMsgWI"></span>
    </div>
    <div class="copy-wrap">{copy_wi_html}</div>
  </div>
  <div class="tab-panel" id="copy-st">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('copyTable-st','copyMsgST')">📋 전체 표 TSV 복사</button>
      <button class="secondary" onclick="selectTable('copyTable-st','copyMsgST')">표 전체 선택</button>
    </div>
    <div class="copy-toolbar" style="margin-top:6px;">
      <label style="font-size:11px;">날짜 <select id="selDate-st">{date_opts_html}</select></label>
      <label style="font-size:11px;">지표
        <select id="selMetric-st">
          <option value="all">매출+수량+주문수</option>
          <option value="amount">매출만</option>
          <option value="qty">수량만</option>
          <option value="cnt">주문수만</option>
        </select>
      </label>
      <button onclick="copyDateColumn('copyTable-st','selDate-st','selMetric-st','copyMsgST')">📅 이 날짜만 복사</button>
      <span class="ok-msg" id="copyMsgST"></span>
    </div>
    <div class="copy-wrap">{copy_st_html}</div>
  </div>
</div>

<div class="copy-section insights-section">
  <h2>📈 인사이트 분석</h2>
  <div class="hint">Best 10 / 카테고리 월간 추세 / 청첩장과의 연결성 (계절성). 탭으로 전환.</div>
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab(this,'insight-best10')">🏆 Best 10 (최근 30일)</button>
    <button class="tab-btn" onclick="showTab(this,'insight-catTrend')">📊 카테고리 월간 추세</button>
    <button class="tab-btn" onclick="showTab(this,'insight-invLink')">💌 청첩장 연결성 (계절성)</button>
  </div>
  <div class="tab-panel active" id="insight-best10">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('best10Table','best10Msg')">📋 TSV 복사</button>
      <button class="secondary" onclick="selectTable('best10Table','best10Msg')">표 전체 선택</button>
      <span class="ok-msg" id="best10Msg"></span>
    </div>
    <div class="copy-wrap">{best10_html}</div>
  </div>
  <div class="tab-panel" id="insight-catTrend">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('catTrendTable','catTrendMsg')">📋 TSV 복사</button>
      <button class="secondary" onclick="selectTable('catTrendTable','catTrendMsg')">표 전체 선택</button>
      <span class="ok-msg" id="catTrendMsg"></span>
    </div>
    <div class="copy-wrap">{cat_trend_html}</div>
  </div>
  <div class="tab-panel" id="insight-invLink">
    <div class="copy-toolbar">
      <button onclick="copyTableTSV('invLinkTable','invLinkMsg')">📋 TSV 복사</button>
      <button class="secondary" onclick="selectTable('invLinkTable','invLinkMsg')">표 전체 선택</button>
      <span class="ok-msg" id="invLinkMsg"></span>
    </div>
    <div class="copy-wrap">{inv_link_html}</div>
  </div>
</div>

<script>
/* 헤더 2행 sticky top 동적 설정 (rowspan=2 + sticky 정렬 문제 해결) */
function alignHeaderTops() {{
  const week = document.querySelector('thead tr.h-week');
  if (!week) return;
  const h = week.offsetHeight;
  document.querySelectorAll('thead tr.h-day th').forEach(th => {{ th.style.top = h + 'px'; }});
}}
window.addEventListener('load', alignHeaderTops);
window.addEventListener('resize', alignHeaderTops);

/* 지표 전환 (전체/매출만/수량만/주문수만) */
function setMetric(m) {{
  document.body.className = 'view-' + m;
  ['all','amount','qty','cnt'].forEach(k => {{
    const b = document.getElementById('m-' + k);
    if (b) b.classList.toggle('active', k === m);
  }});
}}

/* 매출 0건 SKU 숨김 */
let hideZero = false;
function toggleZero() {{
  hideZero = !hideZero;
  document.querySelectorAll('tr.sku-row.zero').forEach(r => r.classList.toggle('hidden', hideZero));
  const btn = document.getElementById('btnZero');
  btn.classList.toggle('active', hideZero);
  btn.textContent = hideZero ? '매출 0 SKU 표시' : '매출 0 SKU 숨기기';
}}

function expandAll() {{
  hideZero = false;
  document.querySelectorAll('tr.sku-row, tr.cat-hdr').forEach(r => r.classList.remove('hidden'));
  document.getElementById('btnZero').classList.remove('active');
  document.getElementById('btnZero').textContent = '매출 0 SKU 숨기기';
  document.querySelectorAll('.fold').forEach(b => b.textContent = '▼');
  /* 모든 주차 펼침 */
  document.querySelectorAll('[data-wk]').forEach(e => e.classList.remove('col-hidden'));
  document.querySelectorAll('.wk-fold').forEach(b => b.textContent = '▼');
}}

/* 카테고리 접기 */
function toggleCat(btn, cat) {{
  const rows = document.querySelectorAll('tr.sku-row[data-cat="' + cat + '"]');
  const folded = btn.textContent === '▶';
  rows.forEach(r => r.classList.toggle('hidden', !folded));
  btn.textContent = folded ? '▼' : '▶';
}}

/* 주차 접기 — 일자 셀만 토글, 소계는 항상 보이게 유지 */
function toggleWeek(wn) {{
  const items = document.querySelectorAll('[data-wk="' + wn + '"]');
  // 소계/WoW 관련 요소는 토글 대상에서 제외 (주차 접어도 항상 보이게)
  const isSubtotal = e => (
    e.classList.contains('col-wksum') ||
    e.classList.contains('wk-sum-hdr') ||
    e.classList.contains('wk-sum') ||
    e.classList.contains('cat-wksum') ||
    e.classList.contains('grand-wksum') ||
    e.classList.contains('col-wow') ||
    e.classList.contains('wk-wow-hdr') ||
    e.classList.contains('wk-wow')
  );
  // wk-hdr(주차 헤더)도 colspan으로 소계까지 묶고 있어서 숨기면 안 됨 — 그대로 둠
  const isWeekHdr = e => e.classList.contains('wk-hdr');

  let folded = false;
  items.forEach(e => {{
    if (e.tagName === 'BUTTON') return;
    if (isSubtotal(e) || isWeekHdr(e)) return;
    if (e.classList.contains('col-hidden')) folded = true;
  }});
  items.forEach(e => {{
    if (e.tagName === 'BUTTON') return;
    if (isSubtotal(e) || isWeekHdr(e)) return;
    e.classList.toggle('col-hidden', !folded);
  }});
  const btn = document.querySelector('.wk-hdr[data-wk="' + wn + '"] .wk-fold');
  if (btn) btn.textContent = folded ? '▼' : '▶';
}}

/* ===== 구글시트 복사용 표 — rowspan/colspan 펼쳐서 격자로 변환 ===== */
function _tableToTSV(table) {{
  const grid = [];
  let maxCols = 0;
  for (let r = 0; r < table.rows.length; r++) {{
    if (!grid[r]) grid[r] = [];
    let col = 0;
    for (const cell of table.rows[r].cells) {{
      while (grid[r][col] !== undefined) col++;
      const text = cell.innerText.replace(/\\r?\\n/g, ' ').replace(/\\t/g, ' ').trim();
      const rs = cell.rowSpan || 1;
      const cs = cell.colSpan || 1;
      for (let dr = 0; dr < rs; dr++) {{
        if (!grid[r + dr]) grid[r + dr] = [];
        for (let dc = 0; dc < cs; dc++) {{
          grid[r + dr][col + dc] = text;
        }}
      }}
      col += cs;
    }}
    if (col > maxCols) maxCols = col;
  }}
  const lines = [];
  for (const row of grid) {{
    const out = [];
    for (let c = 0; c < maxCols; c++) out.push(row[c] !== undefined ? row[c] : '');
    lines.push(out.join('\\t'));
  }}
  return lines.join('\\n');
}}

function copyTSV() {{
  const table = document.getElementById('copyTable');
  if (!table) return;
  const tsv = _tableToTSV(table);
  const msg = document.getElementById('copyMsg');
  navigator.clipboard.writeText(tsv).then(() => {{
    if (msg) {{ msg.textContent = '✓ 복사 완료 — 구글시트에 Ctrl+V'; setTimeout(() => msg.textContent = '', 4000); }}
  }}).catch(err => {{
    if (msg) {{ msg.textContent = '✗ 복사 실패 — "표 전체 선택" 후 Ctrl+C 사용'; setTimeout(() => msg.textContent = '', 5000); }}
  }});
}}

function selectCopyTable() {{
  const table = document.getElementById('copyTable');
  if (!table) return;
  const range = document.createRange();
  range.selectNodeContents(table);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  const msg = document.getElementById('copyMsg');
  if (msg) {{ msg.textContent = '✓ 선택됨 — Ctrl+C로 복사'; setTimeout(() => msg.textContent = '', 4000); }}
}}

function toggleCopySection() {{
  const wrap = document.getElementById('copyWrap');
  const btn = document.getElementById('btnCopyToggle');
  const collapsed = wrap.classList.toggle('collapsed');
  if (btn) btn.textContent = collapsed ? '표 펼치기' : '표 접기';
}}

/* 탭 전환 */
function showTab(btn, panelId) {{
  const section = btn.closest('.copy-section');
  if (!section) return;
  section.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const panel = section.querySelector('#' + panelId);
  if (panel) panel.classList.add('active');
  section.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}

/* 공용 — 표 TSV 복사 */
function copyTableTSV(tableId, msgId) {{
  const t = document.getElementById(tableId);
  const msg = msgId ? document.getElementById(msgId) : null;
  if (!t) return;
  const tsv = _tableToTSV(t);
  navigator.clipboard.writeText(tsv).then(() => {{
    if (msg) {{ msg.textContent = '✓ 복사 완료 — 시트에 Ctrl+V'; setTimeout(() => msg.textContent = '', 4000); }}
  }}).catch(() => {{
    if (msg) {{ msg.textContent = '✗ 복사 실패 — 표 전체 선택 후 Ctrl+C'; setTimeout(() => msg.textContent = '', 5000); }}
  }});
}}
function selectTable(tableId, msgId) {{
  const t = document.getElementById(tableId);
  const msg = msgId ? document.getElementById(msgId) : null;
  if (!t) return;
  const r = document.createRange();
  r.selectNodeContents(t);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(r);
  if (msg) {{ msg.textContent = '✓ 선택됨 — Ctrl+C'; setTimeout(() => msg.textContent = '', 4000); }}
}}

/* 데일리 1열 복사 — 선택 날짜의 값만 줄바꿈 분리 */
function copyDateColumn(tableId, dateSelId, metricSelId, msgId) {{
  const selDate = document.getElementById(dateSelId).value;
  const selMetric = document.getElementById(metricSelId).value;
  const tbody = document.querySelector('#' + tableId + ' tbody');
  const msg = document.getElementById(msgId);
  if (!tbody) return;
  const lines = [];
  for (const row of tbody.rows) {{
    const metric = row.getAttribute('data-metric');
    if (selMetric !== 'all' && metric !== selMetric) continue;
    const cell = row.querySelector('td[data-date="' + selDate + '"]');
    if (cell) lines.push(cell.innerText.trim());
  }}
  if (!lines.length) {{
    if (msg) {{ msg.textContent = '✗ 해당 날짜 값이 없습니다'; setTimeout(() => msg.textContent = '', 4000); }}
    return;
  }}
  const text = lines.join('\\n');
  navigator.clipboard.writeText(text).then(() => {{
    const mLabel = {{all:'매출+수량+주문수', amount:'매출만', qty:'수량만', cnt:'주문수만'}}[selMetric];
    if (msg) {{ msg.textContent = '✓ ' + selDate + ' ' + mLabel + ' ' + lines.length + '개 값 복사됨 — 시트의 해당 열에 Ctrl+V'; setTimeout(() => msg.textContent = '', 6000); }}
  }}).catch(() => {{
    if (msg) {{ msg.textContent = '✗ 복사 실패'; setTimeout(() => msg.textContent = '', 4000); }}
  }});
}}
</script>
</body>
</html>"""


def main():
    days = 30
    date_from = None
    date_to = None
    args = sys.argv[1:]
    if len(args) == 1 and args[0].isdigit():
        days = int(args[0])
    elif len(args) >= 2:
        date_from = datetime.strptime(args[0], "%Y-%m-%d").date()
        date_to = datetime.strptime(args[1], "%Y-%m-%d").date()

    today = date.today()
    if not date_from:
        date_from = today - timedelta(days=days - 1)
    if not date_to:
        date_to = today

    print(f"[1/2] 기간 {date_from} ~ {date_to}")
    html = generate_sku_html(date_from, date_to)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[2/2] 출력: {OUT_FILE}")


if __name__ == "__main__":
    main()
