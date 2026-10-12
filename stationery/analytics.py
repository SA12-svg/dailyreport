"""
기념굿즈(데코소품) 선제대응 대시보드 — 분석 엔진
- 완전 독립형 신규 앱 (C:\\Users\\LG\\deco-dashboard). 기존 파일은 읽기 전용으로만 참조.
- 검증된 매출 쿼리는 기존 build_sku_daily 를 read-only import 로 재사용 (단일 진실원).
  (settle_date 취소필터 / ETC 라인총액 / pearl·sticker set 환산 / 쿠폰 비례배분 모두 반영)
- 산출: KPI, 카테고리 모멘텀, 월말 매출예측(런레이트+YoY), 기획전/선제대응 추천, 데일리 표 데이터

기존 시스템(sku_server, build_sku_daily 등)은 절대 수정하지 않는다.
"""
import os, sys, calendar
from datetime import date, timedelta
from collections import defaultdict

# --- 기존 검증 쿼리 재사용 (read-only) ---
_REF_DIR = os.getenv("DECO_REF_DIR", r"C:\Users\LG\barunson-dashboard")  # Docker 배포 시 env로 지정
if _REF_DIR not in sys.path:
    sys.path.insert(0, _REF_DIR)
import build_sku_daily as B   # noqa: E402

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
DEPTH1 = "기념굿즈"

# "문구류(스테이셔너리)" = 기념굿즈 내 종이/문구 성격 카테고리 (categories.json 이름 기준)
STATIONERY_CATS = ["메시지 카드", "엽서/캘린더"]

# 주간 리포트(WoW)에서 제외할 카테고리 (시즌성 이벤트성 카테고리 등, 사용자 요청 누적)
WEEKLY_EXCLUDE_CATS = {"어버이날"}

# 결제 전환 퍼널: 미결제(이탈) 판정 시 이 일수보다 오래된 주문만 집계 —
# 아직 결제 진행 중인 최근 주문을 이탈로 오판하지 않기 위한 버퍼(리드타임 로직과 동일 관점)
FUNNEL_STALE_DAYS = 3

# "신상품 스포트라이트" 대상 — 출시(added_at) 후 이 일수 이내인 상품만 (main 조회기간과 동일하게 맞춤)
NEW_PRODUCT_WINDOW_DAYS = 45


def _dec(s):
    """S2_Card.Card_Name 등 varchar 한글이 cp949→latin1로 잘못 디코드되어 오는 경우 보정.
    (daily-report-dashboard.py 의 동일 이슈·동일 보정과 같은 관점)"""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin1").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

# 결혼 성수기/비수기 (월). 기존 build_sku_daily 의 SEASON_MAP 과 동일 관점.
SEASON = {1: "비수기", 2: "비수기", 3: "보통", 4: "성수기", 5: "성수기", 6: "보통",
          7: "비수기", 8: "비수기", 9: "성수기", 10: "성수기", 11: "성수기", 12: "보통"}
PEAK_MONTHS = {4, 5, 9, 10, 11}

# 웨딩 예식과 직접 연동되는 카테고리(선물성/시즌성 제외) — 성수기 선제대응 대상 판단용
WEDDING_CATS_HINT = ["포스터", "아크릴", "스탬프", "스티커", "촬영", "퍼즐", "신문", "엽서"]

# 음력 기반 명절(설날/추석) — 매년 날짜가 달라 수기 등록 필요. 2028년 이후분은 등록 시점에 추가.
LUNAR_HOLIDAYS = {
    2026: [("설날", 2, 17), ("추석", 9, 25)],
    2027: [("설날", 2, 7), ("추석", 9, 15)],
}
# 매년 고정 날짜의 선물/기념일 시즌
FIXED_EVENTS = [("화이트데이", 3, 14), ("빼빼로데이", 11, 11), ("크리스마스", 12, 25), ("연말", 12, 31)]


def _vec(e):
    """(code,date) 엔트리 → [cnt,qty,amt, wi_cnt,wi_qty,wi_amt, st_cnt,st_qty,st_amt]"""
    if not e:
        return [0]*9
    wi, st = e.get("wi", {}), e.get("st", {})
    return [e.get("cnt",0), e.get("qty",0), e.get("amount",0),
            wi.get("cnt",0), wi.get("qty",0), wi.get("amount",0),
            st.get("cnt",0), st.get("qty",0), st.get("amount",0)]


def _add(a, b):
    for i in range(9):
        a[i] += b[i]


def _fetch_channel_daily(codes, date_from, date_to, batch_size=100):
    """(code, date) -> {'card': {cnt,qty,amount,wi:{..},st:{..}}, 'mall': {..}}
    바른손카드(sales_Gubun='SB') vs 바른손몰(sales_Gubun IN ('B','H')) 채널 분리 합계 (wi+st 합산,
    청첩장 동반(wi)/단독(st) 세부도 채널별로 함께 보관 — 채널별 동반주문비율/단독주문비율 계산용).
    build_sku_daily.fetch_sku_daily 의 sql1/sql2 쿼리·금액계산 로직을 채널 필터만 추가해 복제한다
    (기존 파일은 read-only import만 하고 수정하지 않는다는 원칙 유지)."""
    if not codes:
        return {}
    def _blank_chan():
        return {"cnt": 0, "qty": 0, "amount": 0,
                 "wi": {"cnt": 0, "qty": 0, "amount": 0},   # 청첩장 동반(custom_order)
                 "st": {"cnt": 0, "qty": 0, "amount": 0}}   # 단독(CUSTOM_ETC_ORDER)
    result = defaultdict(lambda: {"card": _blank_chan(), "mall": _blank_chan()})

    def _merge(code, ds, channel, source, cnt, qty, amt):
        if channel not in ("card", "mall"):
            return
        b = result[(code, ds)][channel]
        b["cnt"] += cnt; b["qty"] += qty; b["amount"] += amt
        sb = b[source]
        sb["cnt"] += cnt; sb["qty"] += qty; sb["amount"] += amt

    CHAN_CASE_WI = ("CASE WHEN o.sales_Gubun = 'SB' THEN 'card' "
                    "WHEN o.sales_Gubun IN ('B','H') THEN 'mall' ELSE 'other' END")
    CHAN_CASE_ST = ("CASE WHEN o.sales_gubun = 'SB' THEN 'card' "
                    "WHEN o.sales_gubun IN ('B','H') THEN 'mall' ELSE 'other' END")

    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        safe = [c.replace("'", "''") for c in batch]
        in_list = ",".join(f"'{c}'" for c in safe)

        sql1 = f"""
        SELECT
            CONVERT(varchar, o.order_date, 23),
            c.Card_Code,
            {CHAN_CASE_WI},
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
        GROUP BY CONVERT(varchar, o.order_date, 23), c.Card_Code, {CHAN_CASE_WI}
        """
        for row in B._run_query_with_retry(sql1):
            d, code, channel, qty, amount, cnt = row
            code_s = str(code)
            qty_v = int(qty or 0)
            amt_v = int(amount or 0)
            cnt_v = int(cnt or 0)
            ov = B.SET_OVERRIDES.get(code_s)
            if ov:
                sets = round(qty_v / ov["qty_per_set"]) if ov["qty_per_set"] else 0
                qty_v = sets
                amt_v = sets * ov["price_per_set"]
            _merge(code_s, str(d)[:10], channel, "wi", cnt_v, qty_v, amt_v)

        sql2 = f"""
        SELECT
            CONVERT(varchar, o.order_date, 23),
            c.Card_Code,
            {CHAN_CASE_ST},
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
        GROUP BY CONVERT(varchar, o.order_date, 23), c.Card_Code, {CHAN_CASE_ST}
        """
        for row in B._run_query_with_retry(sql2):
            d, code, channel, qty, amount, cnt = row
            code_s = str(code)
            qty_v = int(qty or 0)
            amt_v = int(amount or 0)
            cnt_v = int(cnt or 0)
            _merge(code_s, str(d)[:10], channel, "st", cnt_v, qty_v, amt_v)

    return dict(result)


def _fetch_cancel_counts(codes, date_from, date_to, batch_size=100):
    """코드별 '결제 후 취소'된 주문건수 (동반 custom_order + 단독 CUSTOM_ETC_ORDER 합산).
    취소율 분모 = 유효주문(기존 sales 쿼리, settle_cancel_date IS NULL) + 이 취소건수.
    결제 자체가 안 된 미완료 주문은 취소로 잡지 않는다(settle_date IS NOT NULL 유지)."""
    if not codes:
        return {}
    result = defaultdict(int)
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        safe = [c.replace("'", "''") for c in batch]
        in_list = ",".join(f"'{c}'" for c in safe)

        sql1 = f"""
        SELECT c.Card_Code, COUNT(DISTINCT o.order_seq)
        FROM custom_order o WITH (NOLOCK)
        INNER JOIN custom_order_item oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
        INNER JOIN S2_Card c           WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
        WHERE o.settle_date IS NOT NULL
          AND o.settle_cancel_date IS NOT NULL
          AND o.order_date >= '{date_from}'
          AND o.order_date <  DATEADD(day, 1, '{date_to}')
          AND c.Card_Code IN ({in_list})
        GROUP BY c.Card_Code
        """
        for code, cnt in B._run_query_with_retry(sql1):
            result[str(code)] += int(cnt or 0)

        sql2 = f"""
        SELECT c.Card_Code, COUNT(DISTINCT o.order_seq)
        FROM CUSTOM_ETC_ORDER o WITH (NOLOCK)
        INNER JOIN CUSTOM_ETC_ORDER_ITEM oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
        INNER JOIN S2_Card c WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
        WHERE o.settle_date IS NOT NULL
          AND o.settle_Cancel_Date IS NOT NULL
          AND o.order_date >= '{date_from}'
          AND o.order_date <  DATEADD(day, 1, '{date_to}')
          AND c.Card_Code IN ({in_list})
        GROUP BY c.Card_Code
        """
        for code, cnt in B._run_query_with_retry(sql2):
            result[str(code)] += int(cnt or 0)
    return dict(result)


def _fetch_funnel(codes, date_from, date_to, cutoff_date, batch_size=100):
    """코드별 결제 전환 퍼널: 주문 생성(장바구니 담김) 대비 결제완료 비율.
    결제 후 취소된 건은 '결제 성공(퍼널 통과)'으로 집계 — 취소는 별도(취소 현황) 지표가 다룬다.
    미결제(이탈)는 order_date가 cutoff_date보다 오래된 건만 집계해 아직 결제 진행 중인
    최근 주문의 편향을 피한다(_fetch_leadtime과 동일 관점). 동반(custom_order)+단독
    (CUSTOM_ETC_ORDER) 합산."""
    if not codes:
        return {}
    result = defaultdict(lambda: {"paid": 0, "unpaid": 0})
    cutoff_s = cutoff_date.strftime("%Y-%m-%d")
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        safe = [c.replace("'", "''") for c in batch]
        in_list = ",".join(f"'{c}'" for c in safe)

        sql1 = f"""
        SELECT c.Card_Code,
            COUNT(DISTINCT CASE WHEN o.settle_date IS NOT NULL THEN o.order_seq END),
            COUNT(DISTINCT CASE WHEN o.settle_date IS NULL AND o.order_date < '{cutoff_s}' THEN o.order_seq END)
        FROM custom_order o WITH (NOLOCK)
        INNER JOIN custom_order_item oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
        INNER JOIN S2_Card c           WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
        WHERE o.order_date >= '{date_from}'
          AND o.order_date <  DATEADD(day, 1, '{date_to}')
          AND c.Card_Code IN ({in_list})
        GROUP BY c.Card_Code
        """
        for code, paid, unpaid in B._run_query_with_retry(sql1):
            r = result[str(code)]
            r["paid"] += int(paid or 0); r["unpaid"] += int(unpaid or 0)

        sql2 = f"""
        SELECT c.Card_Code,
            COUNT(DISTINCT CASE WHEN o.settle_date IS NOT NULL THEN o.order_seq END),
            COUNT(DISTINCT CASE WHEN o.settle_date IS NULL AND o.order_date < '{cutoff_s}' THEN o.order_seq END)
        FROM CUSTOM_ETC_ORDER o WITH (NOLOCK)
        INNER JOIN CUSTOM_ETC_ORDER_ITEM oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
        INNER JOIN S2_Card c WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
        WHERE o.order_date >= '{date_from}'
          AND o.order_date <  DATEADD(day, 1, '{date_to}')
          AND c.Card_Code IN ({in_list})
        GROUP BY c.Card_Code
        """
        for code, paid, unpaid in B._run_query_with_retry(sql2):
            r = result[str(code)]
            r["paid"] += int(paid or 0); r["unpaid"] += int(unpaid or 0)
    return dict(result)


def _fetch_total_invites(date_from, date_to):
    """기간 내 결제완료된 청첩장(Card_Div='A01') 주문건수 — 굿즈 Cross-sell 전환율의 분모."""
    sql = f"""
    SELECT COUNT(DISTINCT o.order_seq)
    FROM custom_order o WITH (NOLOCK)
    INNER JOIN custom_order_item oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
    INNER JOIN S2_Card c WITH (NOLOCK) ON oi.card_seq = c.Card_Seq AND c.Card_Div = 'A01'
    WHERE o.settle_date IS NOT NULL AND o.settle_cancel_date IS NULL
      AND o.order_date >= '{date_from}'
      AND o.order_date <  DATEADD(day, 1, '{date_to}')
    """
    rows = B._run_query_with_retry(sql)
    return int(rows[0][0] or 0) if rows else 0


def _fetch_invite_pairs(stationery_codes, date_from, date_to, top_n=15):
    """청첩장(Card_Div='A01') + 문구류 상품이 같은 주문(order_seq)에 함께 담긴 조합 TOP N.
    동반구매(custom_order)만 대상 — 단독주문(CUSTOM_ETC_ORDER)엔 청첩장이 없어 페어링 자체가 성립 안 함."""
    if not stationery_codes:
        return []
    safe = [c.replace("'", "''") for c in stationery_codes]
    in_list = ",".join(f"'{c}'" for c in safe)
    sql = f"""
    SELECT ci.Card_Code, ci.Card_Name, si.Card_Code, si.Card_Name, COUNT(DISTINCT o.order_seq) AS cnt
    FROM custom_order o WITH (NOLOCK)
    INNER JOIN custom_order_item oi1 WITH (NOLOCK) ON o.order_seq = oi1.order_seq
    INNER JOIN S2_Card ci            WITH (NOLOCK) ON oi1.card_seq = ci.Card_Seq AND ci.Card_Div = 'A01'
    INNER JOIN custom_order_item oi2 WITH (NOLOCK) ON o.order_seq = oi2.order_seq
    INNER JOIN S2_Card si            WITH (NOLOCK) ON oi2.card_seq = si.Card_Seq AND si.Card_Code IN ({in_list})
    WHERE o.settle_date IS NOT NULL
      AND o.settle_cancel_date IS NULL
      AND o.order_date >= '{date_from}'
      AND o.order_date <  DATEADD(day, 1, '{date_to}')
    GROUP BY ci.Card_Code, ci.Card_Name, si.Card_Code, si.Card_Name
    ORDER BY cnt DESC
    """
    rows = B._run_query_with_retry(sql)
    out = [{"invite_code": str(r[0]), "invite_name": _dec(r[1]) or "",
            "item_code": str(r[2]), "item_name": _dec(r[3]) or "", "cnt": int(r[4] or 0)} for r in rows]
    return out[:top_n]


def _fetch_invite_pairs_all(codes, date_from, date_to, top_n=30):
    """청첩장(Card_Div='A01') + 전체 등록 기념굿즈 상품코드가 같은 주문에 함께 담긴 조합 TOP N
    (동반주문건수·수량·금액 포함). _fetch_invite_pairs 와 동일 관점(동반구매=custom_order만 대상)이나
    문구류 한정이 아닌 전체 카테고리 대상 + 수량/금액 컬럼 추가. (pearl/커스텀스티커 set 환산은
    미반영 — item_price 원시값 기준. 대략적인 '어떤 조합이 잘 나가는지' 비교용.)"""
    if not codes:
        return []
    safe = [c.replace("'", "''") for c in codes]
    in_list = ",".join(f"'{c}'" for c in safe)
    sql = f"""
    SELECT ci.Card_Code, ci.Card_Name, si.Card_Code, si.Card_Name,
           COUNT(DISTINCT o.order_seq) AS cnt,
           SUM(oi2.item_count) AS qty,
           SUM(oi2.item_count * oi2.item_price) AS amt
    FROM custom_order o WITH (NOLOCK)
    INNER JOIN custom_order_item oi1 WITH (NOLOCK) ON o.order_seq = oi1.order_seq
    INNER JOIN S2_Card ci            WITH (NOLOCK) ON oi1.card_seq = ci.Card_Seq AND ci.Card_Div = 'A01'
    INNER JOIN custom_order_item oi2 WITH (NOLOCK) ON o.order_seq = oi2.order_seq
    INNER JOIN S2_Card si            WITH (NOLOCK) ON oi2.card_seq = si.Card_Seq AND si.Card_Code IN ({in_list})
    WHERE o.settle_date IS NOT NULL
      AND o.settle_cancel_date IS NULL
      AND o.order_date >= '{date_from}'
      AND o.order_date <  DATEADD(day, 1, '{date_to}')
    GROUP BY ci.Card_Code, ci.Card_Name, si.Card_Code, si.Card_Name
    ORDER BY cnt DESC
    """
    rows = B._run_query_with_retry(sql)
    out = [{"invite_code": str(r[0]), "invite_name": _dec(r[1]) or "",
            "item_code": str(r[2]), "item_name": _dec(r[3]) or "",
            "cnt": int(r[4] or 0), "qty": int(r[5] or 0), "amt": int(r[6] or 0)} for r in rows]
    return out[:top_n]


def _fetch_leadtime(codes, today, cur_from_days=45, cur_to_days=15, window_days=30):
    """order_date → 배송일 평균 리드타임(일). 동반(wi)=DELIVERY_INFO.DELIVERY_DATE,
    단독(st)=CUSTOM_ETC_ORDER.delivery_date. 최근 배송이 확정됐을 시점(주문일 기준
    cur_to_days~cur_from_days일 전)만 집계해 '아직 미배송'인 최근 주문의 편향을 피하고,
    직전 동일 길이 구간과 비교해 추세를 본다."""
    empty = {"wi_cur": None, "st_cur": None, "wi_prev": None, "st_prev": None}
    if not codes:
        return empty
    safe = [c.replace("'", "''") for c in codes]
    in_list = ",".join(f"'{c}'" for c in safe)

    def _period(offset_from, offset_to):
        d_from = (today - timedelta(days=offset_from)).strftime("%Y-%m-%d")
        d_to = (today - timedelta(days=offset_to)).strftime("%Y-%m-%d")
        wi_sql = f"""
        SELECT AVG(CAST(DATEDIFF(day, o2.order_date, o2.dd) AS float))
        FROM (
            SELECT DISTINCT o.order_seq, o.order_date, d.DELIVERY_DATE AS dd
            FROM custom_order o WITH (NOLOCK)
            INNER JOIN custom_order_item oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
            INNER JOIN S2_Card c WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
            INNER JOIN DELIVERY_INFO d WITH (NOLOCK) ON d.ORDER_SEQ = o.order_seq
            WHERE o.settle_date IS NOT NULL AND o.settle_cancel_date IS NULL
              AND d.DELIVERY_DATE IS NOT NULL
              AND o.order_date >= '{d_from}' AND o.order_date < DATEADD(day, 1, '{d_to}')
              AND c.Card_Code IN ({in_list})
        ) o2
        """
        st_sql = f"""
        SELECT AVG(CAST(DATEDIFF(day, o2.order_date, o2.dd) AS float))
        FROM (
            SELECT DISTINCT o.order_seq, o.order_date, o.delivery_date AS dd
            FROM CUSTOM_ETC_ORDER o WITH (NOLOCK)
            INNER JOIN CUSTOM_ETC_ORDER_ITEM oi WITH (NOLOCK) ON o.order_seq = oi.order_seq
            INNER JOIN S2_Card c WITH (NOLOCK) ON oi.card_seq = c.Card_Seq
            WHERE o.settle_date IS NOT NULL AND o.settle_Cancel_Date IS NULL
              AND o.delivery_date IS NOT NULL
              AND o.order_date >= '{d_from}' AND o.order_date < DATEADD(day, 1, '{d_to}')
              AND c.Card_Code IN ({in_list})
        ) o2
        """
        wi_rows = B._run_query_with_retry(wi_sql)
        st_rows = B._run_query_with_retry(st_sql)
        wi_v = wi_rows[0][0] if wi_rows else None
        st_v = st_rows[0][0] if st_rows else None
        return (round(wi_v, 1) if wi_v is not None else None,
                round(st_v, 1) if st_v is not None else None)

    wi_cur, st_cur = _period(cur_from_days, cur_to_days)
    wi_prev, st_prev = _period(cur_from_days + window_days, cur_to_days + window_days)
    return {"wi_cur": wi_cur, "st_cur": st_cur, "wi_prev": wi_prev, "st_prev": st_prev}


def _event_action(name):
    """캘린더 이벤트 유형별 선제 액션 가이드 한 줄."""
    if name in ("설날", "추석"):
        return "명절 인사와 함께 청첩장을 전달하는 시즌 — 스티커·엽서 등 소품 재고를 점검하세요."
    if "성수기 시작" in name:
        return "포스터·아크릴·스탬프 등 웨딩 소품 재고·디자인·기획전을 지금 준비하세요."
    if name in ("화이트데이", "빼빼로데이", "크리스마스", "연말"):
        return "선물성 상품(포장·엽서·캘린더 등) 프로모션을 준비하기 좋은 시즌입니다."
    return "다가오는 시즌 수요에 맞춰 재고·기획전을 점검하세요."


def _upcoming_events(today, leadtime_wi=None, within_days=90, buffer_days=3):
    """향후 within_days일 이내 달력 이벤트(명절·기념일·결혼 성수기 시작) + D-day + 주문 마감 권장일.
    마감 권장일 = 이벤트일 - (동반주문 평균 리드타임 + 여유버퍼)."""
    candidates = []
    for y in (today.year, today.year + 1):
        for name, m, d in LUNAR_HOLIDAYS.get(y, []):
            candidates.append((date(y, m, d), name))
        for name, m, d in FIXED_EVENTS:
            candidates.append((date(y, m, d), name))
    # 다음 결혼 성수기 시작월
    for offset in range(1, 13):
        y2 = today.year + (today.month - 1 + offset) // 12
        m2 = (today.month - 1 + offset) % 12 + 1
        if m2 in PEAK_MONTHS:
            candidates.append((date(y2, m2, 1), f"{m2}월 결혼 성수기 시작"))
            break

    events = []
    for ev_date, name in candidates:
        d_day = (ev_date - today).days
        if 0 <= d_day <= within_days:
            deadline = None
            if leadtime_wi:
                deadline = ev_date - timedelta(days=round(leadtime_wi) + buffer_days)
            events.append({
                "name": name, "date": ev_date.strftime("%Y-%m-%d"), "d_day": d_day,
                "deadline": deadline.strftime("%Y-%m-%d") if deadline else None,
                "action": _event_action(name),
            })
    events.sort(key=lambda x: x["d_day"])
    return events


def _load_added_dates():
    """products.json(자동동기화)의 added_at 맵. build_sku_daily.build_sku_list()는 이 필드를
    포함하지 않으므로 신상품 스포트라이트 용도로만 별도 read-only 로드(원본 파일은 수정하지 않음)."""
    products = B.load_json(B.PRODUCTS_FILE, [])
    out = {}
    for p in products:
        code = (p.get("card_code") or "").strip()
        ad = p.get("added_at")
        if code and ad:
            out[code] = ad
    return out


def _build_pareto(sales, today, code2name, code2cat, window_days=28, top_show=15):
    """매출 집중도(ABC/파레토): 최근 window_days일 SKU별 매출 기준으로
    상위 몇 %의 SKU가 매출의 80%를 차지하는지 계산 — MD 재고·기획전 집중도 판단용."""
    d_from = today - timedelta(days=window_days - 1)
    sku_amt = defaultdict(int)
    for (code, ds), e in sales.items():
        try:
            dd = date.fromisoformat(ds)
        except Exception:
            continue
        if d_from <= dd <= today:
            sku_amt[code] += _vec(e)[2]
    items = [{"code": c, "amt": a} for c, a in sku_amt.items() if a > 0]
    items.sort(key=lambda x: -x["amt"])
    total = sum(x["amt"] for x in items)
    n = len(items)
    top_n_80 = n
    cum = 0
    for i, it in enumerate(items, 1):
        cum += it["amt"]
        it["cum_pct"] = round(cum / total * 100.0, 1) if total else 0.0
        it["pct"] = round(it["amt"] / total * 100.0, 1) if total else 0.0
        it["name"] = code2name.get(it["code"], it["code"])
        it["cat"] = code2cat.get(it["code"], "")
        if top_n_80 == n and cum >= total * 0.8:
            top_n_80 = i
    top20_n = max(1, round(n * 0.2)) if n else 0
    top20_share = round(sum(x["amt"] for x in items[:top20_n]) / total * 100.0, 1) if total and n else 0.0
    return {
        "window_days": window_days, "total_amt": total, "total_skus": n,
        "top_n_80": top_n_80,
        "top_n_80_pct": round(top_n_80 / n * 100.0, 1) if n else 0.0,
        "top20_n": top20_n, "top20_share": top20_share,
        "rows": items[:top_show],
    }


def _build_new_products(sales, code2cat, code2name, today, window_days=NEW_PRODUCT_WINDOW_DAYS):
    """최근 출시 상품(added_at 기준) 스포트라이트 — 출시 후 누적 판매·일평균 매출.
    홈페이지 자동 동기화(sync_products.py)가 멈춰있으면 신상품이 조용히 대시보드에서
    누락될 수 있어, 출시일 대비 매출 0인 상품을 바로 알아볼 수 있게 한다."""
    added = _load_added_dates()
    cutoff = today - timedelta(days=window_days)
    rows = []
    for code, ad_s in added.items():
        try:
            ad = date.fromisoformat(ad_s)
        except Exception:
            continue
        if ad < cutoff or ad > today:
            continue
        cnt = qty = amt = 0
        d = ad
        while d <= today:
            e = sales.get((code, d.strftime("%Y-%m-%d")))
            if e:
                v = _vec(e)
                cnt += v[0]; qty += v[1]; amt += v[2]
            d += timedelta(days=1)
        days_live = (today - ad).days + 1
        rows.append({
            "code": code, "name": code2name.get(code, code), "cat": code2cat.get(code, ""),
            "added_at": ad_s, "days_live": days_live,
            "cnt": cnt, "qty": qty, "amt": amt,
            "avg_daily_amt": round(amt / days_live) if days_live else 0,
        })
    rows.sort(key=lambda r: (-r["amt"], -r["days_live"]))
    return rows


SF_POSTER_CAT = "셀프 포스터(sf_)"
SF_POSTER_META = {"name": SF_POSTER_CAT, "icon": "🖼️", "color": "#37474F", "bg": "#ECEFF1"}


def _sf_poster_items():
    """SF_ 로 시작하고 상품명에 '포스터'가 들어간 코드(예: SF_poster_001 셀프 포스터) → [(code, name, regdate)].
    기념굿즈 등록목록(sku_list)에 없어 S2_Card에서 직접 찾는다."""
    rows = B._run_query_with_retry(
        "SELECT Card_Code, Card_Name, RegDate FROM S2_Card WITH (NOLOCK) WHERE Card_Code LIKE 'SF[_]%'")
    return [(str(r[0]), _dec(r[1] or "").strip(), r[2]) for r in rows if "포스터" in _dec(r[1] or "")]


def _with_sf_poster(sku_list, cat_order, cat_meta, sales, channel_sales, d_from, d_to):
    """주간 리포트·데일리 주문 표 전용: sf_ 포스터를 '셀프 포스터(sf_)' 카테고리로 끼워 넣은 사본 반환.
    (다른 섹션 KPI/모멘텀 등에는 영향 없음 — 원본 리스트/맵은 건드리지 않는다)"""
    items = _sf_poster_items()
    if not items:
        return sku_list, cat_order, cat_meta, sales, channel_sales
    codes = [c for c, _, _ in items]
    sku2 = list(sku_list) + [{"card_code": c, "name": n, "category": SF_POSTER_CAT, "discontinued": False}
                             for c, n, _ in items]
    order2 = list(cat_order)
    order2.insert(order2.index("웨딩포스터") + 1 if "웨딩포스터" in order2 else len(order2), SF_POSTER_CAT)
    meta2 = dict(cat_meta); meta2[SF_POSTER_CAT] = SF_POSTER_META
    sales2 = dict(sales); sales2.update(B.fetch_sku_daily(codes, d_from, d_to))
    chan2 = channel_sales
    if channel_sales is not None:
        chan2 = dict(channel_sales); chan2.update(_fetch_channel_daily(codes, d_from, d_to))
    return sku2, order2, meta2, sales2, chan2


def _build_sf_poster(today, r7_from):
    """sf_ 포스터의 최근 7일 / 출시 후 누적 수량·주문·매출 (문구류 스포트라이트용)."""
    items = _sf_poster_items()
    out = {"codes": [c for c, _, _ in items], "r7_qty": 0, "r7_cnt": 0, "r7_amt": 0,
           "total_qty": 0, "since": None}
    if not items:
        return out
    since = min((d.date() if hasattr(d, "date") else today) for _, _, d in items)
    out["since"] = since.strftime("%Y-%m-%d")
    sales = B.fetch_sku_daily(out["codes"], out["since"], today.strftime("%Y-%m-%d"))
    r7_s = r7_from.strftime("%Y-%m-%d")
    for (_, ds), e in sales.items():
        out["total_qty"] += e["qty"]
        if ds >= r7_s:
            out["r7_qty"] += e["qty"]; out["r7_cnt"] += e["cnt"]; out["r7_amt"] += e["amount"]
    return out


def compute(today=None):
    today = today or date.today()

    sku_list = B.build_sku_list()
    categories = B.load_json(B.CATEGORIES_FILE, [])
    cat_meta = {c["name"]: c for c in categories}
    code2cat = {s["card_code"]: s["category"] for s in sku_list}
    code2name = {s["card_code"]: s.get("name","") for s in sku_list}
    codes = [s["card_code"] for s in sku_list]

    # 카테고리 순서: categories.json 순서 유지 + 데이터에만 있는 것 뒤에
    cat_order = [c["name"] for c in categories]
    for s in sku_list:
        if s["category"] and s["category"] not in cat_order:
            cat_order.append(s["category"])

    # "문구류" = STATIONERY_CATS 소속 등록 상품코드
    stationery_codes = [s["card_code"] for s in sku_list if s["category"] in STATIONERY_CATS]

    # --- 데이터 fetch ---
    N_MAIN = 49  # 모멘텀(최근7/직전7/28일평균) + 데일리표 + 주간리포트 WoW(전전주·직전3주블록)
    main_from = today - timedelta(days=N_MAIN - 1)
    sales = B.fetch_sku_daily(codes, main_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), batch_size=100)

    # 작년 동월 (YoY 예측 비교)
    ly_year = today.year - 1
    ly_from = date(ly_year, today.month, 1)
    ly_last = calendar.monthrange(ly_year, today.month)[1]
    ly_to = date(ly_year, today.month, ly_last)
    sales_ly = B.fetch_sku_daily(codes, ly_from.strftime("%Y-%m-%d"), ly_to.strftime("%Y-%m-%d"), batch_size=100)

    # --- 카테고리 × 일자 벡터 집계 (main 기간) ---
    dates_main = [main_from + timedelta(days=i) for i in range(N_MAIN)]
    dstr_main = [d.strftime("%Y-%m-%d") for d in dates_main]
    cat_day = {c: {ds: [0]*9 for ds in dstr_main} for c in cat_order}
    for (code, ds), e in sales.items():
        c = code2cat.get(code)
        if c is None or ds not in cat_day.get(c, {}):
            continue
        _add(cat_day[c][ds], _vec(e))

    def cat_sum(cat, d_from, d_to, idx):
        """cat 의 [d_from, d_to] 구간 idx 지표 합 (둘 다 date)"""
        t = 0
        d = d_from
        while d <= d_to:
            ds = d.strftime("%Y-%m-%d")
            if ds in cat_day[cat]:
                t += cat_day[cat][ds][idx]
            d += timedelta(days=1)
        return t

    # 기간 경계
    r7_from = today - timedelta(days=6)                 # 최근 7일
    p7_from, p7_to = today - timedelta(days=13), today - timedelta(days=7)   # 직전 7일
    b28_from, b28_to = today - timedelta(days=34), today - timedelta(days=7)  # 직전 28일 (recent7 이전)
    mstart = today.replace(day=1)

    # --- 리드타임 (주문일 → 배송일, 동반/단독 평균 + 추세) ---
    leadtime = _fetch_leadtime(codes, today)

    # --- 채널 분리 (바른손카드 vs 바른손몰, sales_Gubun 기준) ---
    # main_from(49일 전)까지 폭넓게 조회해 KPI 채널요약뿐 아니라 WoW 리포트(최대 41일 전)·
    # 데일리 기본뷰(21일)에서도 재사용한다 (쿼리 왕복 최소화).
    channel_sales = _fetch_channel_daily(codes, main_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    r7_from_s, today_s = r7_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    cat_chan_r7 = defaultdict(lambda: {"card": 0, "mall": 0})
    chan_day = defaultdict(lambda: {"card": {"cnt": 0, "qty": 0, "amount": 0},
                                     "mall": {"cnt": 0, "qty": 0, "amount": 0}})
    for (code, ds), e in channel_sales.items():
        for ch in ("card", "mall"):
            for k in ("cnt", "qty", "amount"):
                chan_day[ds][ch][k] += e[ch][k]
        if r7_from_s <= ds <= today_s:
            c = code2cat.get(code)
            if c is not None:
                cat_chan_r7[c]["card"] += e["card"]["amount"]
                cat_chan_r7[c]["mall"] += e["mall"]["amount"]

    def chan_sum(d_from, d_to, ch, metric):
        t = 0
        d = d_from
        while d <= d_to:
            ds = d.strftime("%Y-%m-%d")
            if ds in chan_day:
                t += chan_day[ds][ch][metric]
            d += timedelta(days=1)
        return t

    # --- 카테고리 모멘텀 ---
    cat_rows = []
    for cat in cat_order:
        if cat not in cat_day:
            continue
        r7_cnt = cat_sum(cat, r7_from, today, 0)
        p7_cnt = cat_sum(cat, p7_from, p7_to, 0)
        b28_cnt = cat_sum(cat, b28_from, b28_to, 0)
        b28_avg7 = b28_cnt / 4.0  # 28일 → 7일 환산 평균
        r7_amt = cat_sum(cat, r7_from, today, 2)
        p7_amt = cat_sum(cat, p7_from, p7_to, 2)
        # 최근 7일 동반율
        r7_wi = cat_sum(cat, r7_from, today, 3)
        r7_st = cat_sum(cat, r7_from, today, 6)
        attach = (r7_wi / r7_cnt * 100.0) if r7_cnt else 0.0
        # 모멘텀: 최근7일 vs 28일평균(7일환산). 노이즈 방지 위해 baseline 기준.
        if b28_avg7 >= 1.0:
            mom = (r7_cnt - b28_avg7) / b28_avg7 * 100.0
        elif r7_cnt > 0:
            mom = 100.0  # 무(無)에서 발생 → 신규 상승
        else:
            mom = 0.0
        # 14일 스파크라인 (일별 주문수)
        spark = [cat_day[cat][ (today - timedelta(days=13-i)).strftime("%Y-%m-%d") ][0]
                 for i in range(14)]
        meta = cat_meta.get(cat, {})
        # 최근 4주 총 주문 (활성 판단)
        total28 = cat_sum(cat, today - timedelta(days=27), today, 0)
        chan = cat_chan_r7.get(cat, {"card": 0, "mall": 0})
        # 평균 객단가(AOV) — 최근7일 vs 직전7일
        aov_r7 = (r7_amt / r7_cnt) if r7_cnt else 0.0
        aov_p7 = (p7_amt / p7_cnt) if p7_cnt else 0.0
        aov_delta = ((aov_r7 - aov_p7) / aov_p7 * 100.0) if aov_p7 else None
        cat_rows.append({
            "name": cat, "icon": meta.get("icon","📦"),
            "r7_cnt": r7_cnt, "p7_cnt": p7_cnt, "b28_avg7": round(b28_avg7,1),
            "r7_amt": r7_amt, "p7_amt": p7_amt, "attach": round(attach,1),
            "r7_wi": r7_wi, "r7_st": r7_st,
            "card_r7_amt": chan["card"], "mall_r7_amt": chan["mall"],
            "mom": round(mom,1), "spark": spark, "total28": total28,
            "season": SEASON.get(today.month,""),
            "aov_r7": round(aov_r7), "aov_p7": round(aov_p7),
            "aov_delta": None if aov_delta is None else round(aov_delta, 1),
        })

    # --- 전체 KPI ---
    def grand_sum(d_from, d_to, idx):
        return sum(cat_sum(c, d_from, d_to, idx) for c in cat_day)

    today_cnt = grand_sum(today, today, 0)
    lastweek_sameday = today - timedelta(days=7)
    lw_cnt = grand_sum(lastweek_sameday, lastweek_sameday, 0)
    r7_cnt_all = grand_sum(r7_from, today, 0)
    p7_cnt_all = grand_sum(p7_from, p7_to, 0)
    r7_wi_all = grand_sum(r7_from, today, 3)
    r7_st_all = grand_sum(r7_from, today, 6)
    r7_wi_amt = grand_sum(r7_from, today, 5)
    r7_st_amt = grand_sum(r7_from, today, 8)
    p7_wi_all = grand_sum(p7_from, p7_to, 3)
    attach_all = (r7_wi_all / r7_cnt_all * 100.0) if r7_cnt_all else 0.0
    attach_prev = (p7_wi_all / p7_cnt_all * 100.0) if p7_cnt_all else 0.0
    mom_all = ((r7_cnt_all - p7_cnt_all)/p7_cnt_all*100.0) if p7_cnt_all else (100.0 if r7_cnt_all else 0.0)

    # --- 채널(바른손카드/바른손몰) KPI 요약 ---
    r7_amt_all = grand_sum(r7_from, today, 2)
    channel = {}
    for label, d_from, d_to, all_cnt, all_amt in (
        ("today", today, today, today_cnt, grand_sum(today, today, 2)),
        ("r7", r7_from, today, r7_cnt_all, r7_amt_all),
    ):
        channel[label] = {
            "all_cnt": all_cnt, "all_amt": all_amt,
            "card_cnt": chan_sum(d_from, d_to, "card", "cnt"), "card_amt": chan_sum(d_from, d_to, "card", "amount"),
            "mall_cnt": chan_sum(d_from, d_to, "mall", "cnt"), "mall_amt": chan_sum(d_from, d_to, "mall", "amount"),
        }

    # --- 월말 매출 예측 (런레이트) + YoY ---
    dim = calendar.monthrange(today.year, today.month)[1]
    mtd_amt = grand_sum(mstart, today, 2)
    mtd_cnt = grand_sum(mstart, today, 0)
    channel["mtd"] = {
        "all_cnt": mtd_cnt, "all_amt": mtd_amt,
        "card_cnt": chan_sum(mstart, today, "card", "cnt"), "card_amt": chan_sum(mstart, today, "card", "amount"),
        "mall_cnt": chan_sum(mstart, today, "mall", "cnt"), "mall_amt": chan_sum(mstart, today, "mall", "amount"),
    }
    elapsed = today.day
    proj_amt = int(mtd_amt / elapsed * dim) if elapsed else 0
    # 작년 동월 실적 (전월 + MTD 동일시점)
    ly_full_amt = sum(_vec(e)[2] for (c,ds),e in sales_ly.items())
    ly_mtd_amt = 0
    for (code, ds), e in sales_ly.items():
        try:
            dd = int(ds[8:10])
        except Exception:
            continue
        if dd <= today.day:
            ly_mtd_amt += _vec(e)[2]
    yoy_proj = ((proj_amt - ly_full_amt)/ly_full_amt*100.0) if ly_full_amt else None
    yoy_pace = ((mtd_amt - ly_mtd_amt)/ly_mtd_amt*100.0) if ly_mtd_amt else None

    forecast = {
        "month": f"{today.year}-{today.month:02d}",
        "mtd_amt": mtd_amt, "mtd_cnt": mtd_cnt,
        "elapsed": elapsed, "dim": dim,
        "proj_amt": proj_amt,
        "ly_full_amt": ly_full_amt, "ly_mtd_amt": ly_mtd_amt,
        "yoy_proj": None if yoy_proj is None else round(yoy_proj,1),
        "yoy_pace": None if yoy_pace is None else round(yoy_pace,1),
        "season": SEASON.get(today.month,""),
    }

    # --- 요일 패턴 (최근 4주) ---
    wd_cnt = [0]*7
    for i in range(28):
        d = today - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        s = sum(cat_day[c][ds][0] for c in cat_day if ds in cat_day[c])
        wd_cnt[d.weekday()] += s
    best_wd = max(range(7), key=lambda k: wd_cnt[k]) if any(wd_cnt) else None

    # --- 라이징 상품 TOP (최근7일 vs 직전7일 SKU 단위) ---
    sku_r7 = defaultdict(int); sku_p7 = defaultdict(int); sku_amt = defaultdict(int)
    for (code, ds), e in sales.items():
        v = _vec(e)
        try:
            dd = date.fromisoformat(ds)
        except Exception:
            continue
        if r7_from <= dd <= today:
            sku_r7[code] += v[0]; sku_amt[code] += v[2]
        elif p7_from <= dd <= p7_to:
            sku_p7[code] += v[0]
    rising = []
    for code, r in sku_r7.items():
        p = sku_p7.get(code, 0)
        if r >= 2 and r > p:
            delta = r - p
            rising.append({"code": code, "name": code2name.get(code, code),
                           "cat": code2cat.get(code, ""), "r7": r, "p7": p,
                           "delta": delta, "amt": sku_amt.get(code,0)})
    rising.sort(key=lambda x: (-x["delta"], -x["amt"]))
    rising = rising[:5]

    # --- 하락 상품 TOP (최근7일 vs 직전7일 SKU 단위, rising과 대칭) ---
    declining = []
    for code, p in sku_p7.items():
        r = sku_r7.get(code, 0)
        if p >= 2 and p > r:
            declining.append({"code": code, "name": code2name.get(code, code),
                              "cat": code2cat.get(code, ""), "r7": r, "p7": p,
                              "delta": p - r, "amt": sku_amt.get(code, 0)})
    declining.sort(key=lambda x: -x["delta"])
    declining = declining[:5]

    # --- 베스트 품목 (최근 7일 매출순, 전체 + 문구류 한정) ---
    best_sorted = sorted(
        ({"code": code, "name": code2name.get(code, code), "cat": code2cat.get(code, ""),
          "amt": amt, "cnt": sku_r7.get(code, 0)} for code, amt in sku_amt.items() if amt > 0),
        key=lambda x: -x["amt"])
    best_products = best_sorted[:10]
    best_products_stationery = [p for p in best_sorted if p["cat"] in STATIONERY_CATS][:10]

    # --- 다가오는 캘린더 이벤트 (명절/기념일/결혼 성수기 시작) ---
    events = _upcoming_events(today, leadtime.get("wi_cur"))

    # --- 카테고리별 인기상품(최근7일 매출순) = '추천 상품' 원천 ---
    cat_top = defaultdict(list)
    for code, amt in sku_amt.items():
        c = code2cat.get(code)
        if c is None:
            continue
        cat_top[c].append({"code": code, "name": code2name.get(code, code),
                           "amt": amt, "cnt": sku_r7.get(code, 0)})
    for c in list(cat_top.keys()):
        cat_top[c].sort(key=lambda x: -x["amt"])
        cat_top[c] = cat_top[c][:6]

    # --- 카테고리별 기획전 데이터 (기획전 페이지 /promo 에서 사용) ---
    promos = {}
    for c in cat_rows:
        promos[c["name"]] = {
            "name": c["name"], "icon": c["icon"],
            "color": cat_meta.get(c["name"], {}).get("color", "#37474F"),
            "bg": cat_meta.get(c["name"], {}).get("bg", "#ECEFF1"),
            "mom": c["mom"], "r7_cnt": c["r7_cnt"], "r7_amt": c["r7_amt"],
            "attach": c["attach"], "season": c["season"],
            "top": cat_top.get(c["name"], []),
        }

    # --- 기획전 / 선제대응 추천 (룰 기반, 근거 수치 포함) ---
    recs = _build_recommendations(cat_rows, forecast, rising, today, best_wd, wd_cnt, cat_top)

    # --- 취소/취소율 (최근 28일, 결제 후 취소 vs 유효주문) — 카테고리별 + 전체 ---
    c28_from = today - timedelta(days=27)
    cancel_counts = _fetch_cancel_counts(codes, c28_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    cat_cancel = defaultdict(int)
    for code, cnt in cancel_counts.items():
        c = code2cat.get(code)
        if c is not None:
            cat_cancel[c] += cnt
    cancel_rows = []
    for c in cat_rows:
        valid = c["total28"]
        cc = cat_cancel.get(c["name"], 0)
        rate = (cc / (valid + cc) * 100.0) if (valid + cc) else 0.0
        cancel_rows.append({"name": c["name"], "icon": c["icon"], "valid": valid, "cancel": cc, "rate": round(rate, 1)})
    cancel_rows.sort(key=lambda x: -x["rate"])
    overall_valid = sum(r["valid"] for r in cancel_rows)
    overall_cancel = sum(r["cancel"] for r in cancel_rows)
    overall_rate = (overall_cancel / (overall_valid + overall_cancel) * 100.0) if (overall_valid + overall_cancel) else 0.0
    cancel = {"rows": cancel_rows, "overall_valid": overall_valid, "overall_cancel": overall_cancel,
              "overall_rate": round(overall_rate, 1)}

    # --- 결제 전환 퍼널 (최근 28일, 주문생성→결제완료) — 카테고리별 + 전체 ---
    funnel_cutoff = today - timedelta(days=FUNNEL_STALE_DAYS)
    funnel_counts = _fetch_funnel(codes, c28_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), funnel_cutoff)
    cat_funnel = defaultdict(lambda: {"paid": 0, "unpaid": 0})
    for code, v in funnel_counts.items():
        c = code2cat.get(code)
        if c is not None:
            cat_funnel[c]["paid"] += v["paid"]; cat_funnel[c]["unpaid"] += v["unpaid"]
    funnel_rows = []
    for c in cat_rows:
        f = cat_funnel.get(c["name"], {"paid": 0, "unpaid": 0})
        denom = f["paid"] + f["unpaid"]
        rate = (f["paid"] / denom * 100.0) if denom else None
        funnel_rows.append({"name": c["name"], "icon": c["icon"], "paid": f["paid"], "unpaid": f["unpaid"],
                            "rate": None if rate is None else round(rate, 1)})
    funnel_rows.sort(key=lambda x: (x["rate"] if x["rate"] is not None else 999))
    overall_paid = sum(r["paid"] for r in funnel_rows)
    overall_unpaid = sum(r["unpaid"] for r in funnel_rows)
    overall_funnel_rate = (overall_paid / (overall_paid + overall_unpaid) * 100.0) if (overall_paid + overall_unpaid) else None
    funnel = {"rows": funnel_rows, "window_days": 28, "stale_days": FUNNEL_STALE_DAYS,
              "overall_paid": overall_paid, "overall_unpaid": overall_unpaid,
              "overall_rate": None if overall_funnel_rate is None else round(overall_funnel_rate, 1)}

    # --- 청첩장 → 굿즈 Cross-sell 전환율 (최근 7일) — 전체 청첩장 판매 대비 카테고리별 동반 비율 ---
    total_invites_r7 = _fetch_total_invites(r7_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    cross_rows = []
    for c in cat_rows:
        rate = (c["r7_wi"] / total_invites_r7 * 100.0) if total_invites_r7 else None
        cross_rows.append({"name": c["name"], "icon": c["icon"], "r7_wi": c["r7_wi"],
                           "rate": None if rate is None else round(rate, 1)})
    cross_rows.sort(key=lambda x: -(x["rate"] or 0))
    cross_sell = {"total_invites_r7": total_invites_r7, "rows": cross_rows}

    # --- 매출 집중도(파레토/ABC, 최근 28일 SKU 기준) ---
    pareto = _build_pareto(sales, today, code2name, code2cat, window_days=28)

    # --- 신상품 성과 스포트라이트 (출시 후 45일 이내) ---
    new_products = _build_new_products(sales, code2cat, code2name, today)

    # --- 문구류(메시지카드/엽서·캘린더) 스포트라이트 — 카테고리 모멘텀·취소 데이터 재사용 ---
    stat_names = set(STATIONERY_CATS)
    stat_rows = [c for c in cat_rows if c["name"] in stat_names]
    stat_r7_cnt = sum(c["r7_cnt"] for c in stat_rows)
    stat_r7_amt = sum(c["r7_amt"] for c in stat_rows)
    stat_r7_wi = sum(c["r7_wi"] for c in stat_rows)
    stat_r7_st = sum(c["r7_st"] for c in stat_rows)
    stat_b28_avg7 = sum(c["b28_avg7"] for c in stat_rows)
    stat_r7_qty = sum(cat_sum(c, r7_from, today, 1) for c in stat_names if c in cat_day)
    stat_valid28 = sum(c["valid"] for c in cancel_rows if c["name"] in stat_names)
    stat_cancel = sum(c["cancel"] for c in cancel_rows if c["name"] in stat_names)
    stationery = {
        "codes": stationery_codes,
        "r7_cnt": stat_r7_cnt, "r7_amt": stat_r7_amt, "r7_qty": stat_r7_qty,
        "r7_wi": stat_r7_wi, "r7_st": stat_r7_st,
        "attach": round((stat_r7_wi / stat_r7_cnt * 100.0) if stat_r7_cnt else 0.0, 1),
        "mom": round(((stat_r7_cnt - stat_b28_avg7) / stat_b28_avg7 * 100.0) if stat_b28_avg7 >= 1.0
                     else (100.0 if stat_r7_cnt > 0 else 0.0), 1),
        "valid28": stat_valid28, "cancel_cnt": stat_cancel,
        "cancel_rate": round((stat_cancel / (stat_valid28 + stat_cancel) * 100.0) if (stat_valid28 + stat_cancel) else 0.0, 1),
    }

    # --- sf_ 포스터 (셀프 포스터, 기념굿즈 등록목록 밖 코드) — 문구류 스포트라이트에 수량 표시 ---
    stationery["sf_poster"] = _build_sf_poster(today, r7_from)

    # --- 청첩장 × 문구류 페어링 (최근 90일, 동반구매만) ---
    pairs_from = today - timedelta(days=89)
    pairs = _fetch_invite_pairs(stationery_codes, pairs_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")) \
        if stationery_codes else []

    # --- 청첩장 × 전체 기념굿즈 페어링 (최근 90일, 동반구매만) — 카테고리 무관 전체 코드 대상 ---
    pairs_all = _fetch_invite_pairs_all(codes, pairs_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")) \
        if codes else []
    for p in pairs_all:
        p["item_cat"] = code2cat.get(p["item_code"], "")

    # --- 데일리 표 데이터 (기본 최근 21일; 기간 변경은 compute_daily/API 로) ---
    dd_from = today - timedelta(days=20)
    dates_daily = [dd_from + timedelta(days=i) for i in range(21)]
    # 주간 리포트·데일리 표에만 sf_ 포스터 포함 (main 49일 창으로 한 번 조회해 두 표가 공유)
    sf_sku, sf_order, sf_meta, sf_sales, sf_chan = _with_sf_poster(
        sku_list, cat_order, cat_meta, sales, channel_sales,
        main_from.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    daily = _build_daily(dates_daily, sf_sales, sf_sku, sf_order, sf_meta, today)

    # --- 데일리 기본뷰(21일) 카테고리별 채널(카드/몰) 매출 — 참고용 정적 요약 ---
    cat_chan_daily = defaultdict(lambda: {"card": 0, "mall": 0})
    dd_from_s = dd_from.strftime("%Y-%m-%d")
    for (code, ds), e in channel_sales.items():
        if dd_from_s <= ds <= today_s:
            c = code2cat.get(code)
            if c is not None:
                cat_chan_daily[c]["card"] += e["card"]["amount"]
                cat_chan_daily[c]["mall"] += e["mall"]["amount"]
    cat_icon = {c["name"]: c["icon"] for c in cat_rows}
    daily_channel = [
        {"name": name, "icon": cat_icon.get(name, "📦"), "card": v["card"], "mall": v["mall"]}
        for name, v in sorted(cat_chan_daily.items(), key=lambda kv: -(kv[1]["card"] + kv[1]["mall"]))
        if v["card"] or v["mall"]
    ]

    # --- 주간 리포트 (직전 2주 합계 + 지난주 일별, WoW) — 일요일 시작. 기준 주 = 지난주(완결 주) ---
    weekly = _build_weekly(sf_sku, sf_order, sf_meta, sf_sales, today - timedelta(days=7), today, channel_sales=sf_chan)

    return {
        "today": today.strftime("%Y-%m-%d"),
        "weekday": WEEKDAY_KR[today.weekday()],
        "depth1": DEPTH1,
        "kpi": {
            "today_cnt": today_cnt, "lw_cnt": lw_cnt,
            "r7_cnt": r7_cnt_all, "p7_cnt": p7_cnt_all, "mom_all": round(mom_all,1),
            "attach_all": round(attach_all,1), "attach_prev": round(attach_prev,1),
            "r7_wi_cnt": r7_wi_all, "r7_st_cnt": r7_st_all,
            "r7_wi_amt": r7_wi_amt, "r7_st_amt": r7_st_amt,
            "mtd_amt": mtd_amt, "proj_amt": proj_amt,
        },
        "cat_rows": cat_rows,
        "forecast": forecast,
        "recs": recs,
        "rising": rising,
        "declining": declining,
        "events": events,
        "channel": channel,
        "leadtime": leadtime,
        "weekday_pattern": {"counts": wd_cnt, "best": best_wd,
                            "labels": WEEKDAY_KR},
        "daily": daily,
        "daily_channel": daily_channel,
        "weekly": weekly,
        "promos": promos,
        "stationery": stationery,
        "best_products": best_products,
        "best_products_stationery": best_products_stationery,
        "cancel": cancel,
        "pairs": pairs,
        "pairs_all": pairs_all,
        "funnel": funnel,
        "cross_sell": cross_sell,
        "pareto": pareto,
        "new_products": new_products,
    }


def _sun_start(d):
    """주 시작 = 일요일. (기존 build_sku_daily 와 동일 관점)"""
    return d - timedelta(days=(d.weekday() + 1) % 7)


# 일요일 시작, 연초(1/1이 속한 일요일 주) = 1주차. 오프셋 없음.
# 검증: 2026-07-05(일)~07-11(토) = 28주차 (today 2026-07-08이 여기 속함).
WEEK_LABEL_OFFSET = 0


def week_number(d):
    """일요일 시작 주차 번호."""
    ws = _sun_start(d)
    first = _sun_start(date(d.year, 1, 1))
    return ((ws - first).days // 7) + 1 + WEEK_LABEL_OFFSET


def _build_weekly(sku_list, cat_order, cat_meta, sales, ref_date, today=None, channel_sales=None):
    """이미지 포맷 주간 리포트. 기준 주(ref_date가 속한 주)를 '최신 주'로 하여
      - W(n-2)/W(n-1): 합산(수량·주문·금액)
      - W(n): 데일리(일별 수량) + 합산   ← 기준 주(기본=이번주, 진행중일 수 있음)
      - 총 누적 합산 = 세 주 합
    행은 3주간 '판매된' 상품(주문 1건 이상)만. 상품코드 포함, 카테고리 합계/WoW/총합계.
    vec9 인덱스: [0]주문 [1]수량 [2]금액. sales 는 w_a~기준주 를 포함해야 함."""
    today = today or ref_date
    ref_ws = _sun_start(ref_date)                  # 기준 주 시작(일)
    w_c = ref_ws                                   # 최신 주(일별) = 기준 주
    w_b = ref_ws - timedelta(days=7)
    w_a = ref_ws - timedelta(days=14)
    # WoW 계산용 이전 주들
    w_pre1 = ref_ws - timedelta(days=21)           # W(a) 직전주 → W(a) WoW
    w_pre2 = ref_ws - timedelta(days=28)
    w_pre3 = ref_ws - timedelta(days=35)           # 총누적 WoW용 직전 3주 블록(w_pre1~3)
    is_current = (ref_ws == _sun_start(today))     # 기준 주가 진행중인 이번주인지
    def wnum(ws):
        first = _sun_start(date((ws + timedelta(days=6)).year, 1, 1))
        return ((ws - first).days // 7) + 1 + WEEK_LABEL_OFFSET
    def rng(ws):
        return ws.strftime("%Y-%m-%d"), (ws + timedelta(days=6)).strftime("%Y-%m-%d")
    (af, at), (bf, bt), (cf, ct) = rng(w_a), rng(w_b), rng(w_c)
    weeks = [
        {"n": wnum(w_a), "from": af, "to": at},
        {"n": wnum(w_b), "from": bf, "to": bt},
        {"n": wnum(w_c), "from": cf, "to": ct, "daily": True, "current": is_current},
    ]
    daily_dates = [w_c + timedelta(days=i) for i in range(7)]
    daily_dstr = [d.strftime("%Y-%m-%d") for d in daily_dates]

    def wk(code, ws):
        t = [0]*9
        for i in range(7):
            _add(t, _vec(sales.get((code, (ws + timedelta(days=i)).strftime("%Y-%m-%d")))))
        return t

    by_cat = defaultdict(list)
    for s in sku_list:
        by_cat[s["category"]].append(s)

    def _blank():
        return {"wa": [0]*9, "wb": [0]*9, "wc": [0]*9, "tot": [0]*9,
                "pre": [0]*9, "tot_pre": [0]*9,          # W(a) WoW용, 총누적 WoW용
                "daily": [[0]*9 for _ in range(7)],
                "daily_prev": [[0]*9 for _ in range(7)],  # 일별 WoW용(전주 같은 요일)
                "chan": {"card": 0, "mall": 0}}           # W(a)~W(c) 3주 전체 바른손카드/바른손몰 매출

    cats_out = []
    grand = _blank()
    for cat in cat_order:
        if cat in WEEKLY_EXCLUDE_CATS:
            continue
        skus = by_cat.get(cat, [])
        if not skus:
            continue
        meta = cat_meta.get(cat, {})
        skus_out = []
        sub = _blank()
        for s in skus:
            code = s["card_code"]
            wa, wb, wc = wk(code, w_a), wk(code, w_b), wk(code, w_c)
            if (wa[0] + wb[0] + wc[0]) <= 0:      # 3주간 판매 없는 상품 제외
                continue
            daily = [_vec(sales.get((code, ds))) for ds in daily_dstr]
            tot = [wa[i] + wb[i] + wc[i] for i in range(9)]
            # WoW용 이전 데이터
            pre = wk(code, w_pre1)                                  # W(a) 직전주
            tot_pre = [0]*9
            for pw in (w_pre1, w_pre2, w_pre3):
                _add(tot_pre, wk(code, pw))                          # 직전 3주 블록(총누적 WoW)
            wb_daily = [_vec(sales.get((code, (w_b + timedelta(days=i)).strftime("%Y-%m-%d"))))
                        for i in range(7)]                           # 전주 같은 요일(일별 WoW)
            skus_out.append({"code": code, "name": s.get("name", ""),
                             "disc": bool(s.get("discontinued", False)),
                             "wa": wa, "wb": wb, "wc": wc, "daily": daily, "tot": tot})
            for k, v in (("wa", wa), ("wb", wb), ("wc", wc), ("tot", tot),
                         ("pre", pre), ("tot_pre", tot_pre)):
                _add(sub[k], v); _add(grand[k], v)
            for i in range(7):
                _add(sub["daily"][i], daily[i]); _add(grand["daily"][i], daily[i])
                _add(sub["daily_prev"][i], wb_daily[i]); _add(grand["daily_prev"][i], wb_daily[i])
            if channel_sales:
                for ws in (w_a, w_b, w_c):
                    for i in range(7):
                        e = channel_sales.get((code, (ws + timedelta(days=i)).strftime("%Y-%m-%d")))
                        if e:
                            sub["chan"]["card"] += e["card"]["amount"]; grand["chan"]["card"] += e["card"]["amount"]
                            sub["chan"]["mall"] += e["mall"]["amount"]; grand["chan"]["mall"] += e["mall"]["amount"]
        if not skus_out:
            continue
        cats_out.append({"name": cat, "icon": meta.get("icon", "📦"),
                         "color": meta.get("color", "#37474F"), "bg": meta.get("bg", "#ECEFF1"),
                         "skus": skus_out, "sub": sub})

    # 카테고리 순서 = 3주 합계 금액(매출) 내림차순 (categories.json 등록 순서 대신 매출 순위로 정렬)
    cats_out.sort(key=lambda c: -c["sub"]["tot"][2])

    # ---- 주차별 바른손카드/바른손몰 수량·주문·금액 + 청첩장 동반(wi)/단독(st) 주문수 ----
    # (전체 등록 SKU 기준 채널 합계 — 위 카테고리·상품 행과 별개로, 주차별 채널 요약 표에 사용)
    def _blank_chan_wk():
        return {"cnt": 0, "qty": 0, "amt": 0, "wi_cnt": 0, "st_cnt": 0}
    chan_weeks = {"wa": {"card": _blank_chan_wk(), "mall": _blank_chan_wk()},
                  "wb": {"card": _blank_chan_wk(), "mall": _blank_chan_wk()},
                  "wc": {"card": _blank_chan_wk(), "mall": _blank_chan_wk()}}
    if channel_sales:
        date_wk = {}
        for wk_key, ws in (("wa", w_a), ("wb", w_b), ("wc", w_c)):
            for i in range(7):
                date_wk[(ws + timedelta(days=i)).strftime("%Y-%m-%d")] = wk_key
        for (code, ds), e in channel_sales.items():
            wk_key = date_wk.get(ds)
            if wk_key is None:
                continue
            for ch in ("card", "mall"):
                b = e.get(ch)
                if not b:
                    continue
                a = chan_weeks[wk_key][ch]
                a["cnt"] += b["cnt"]; a["qty"] += b["qty"]; a["amt"] += b["amount"]
                a["wi_cnt"] += b.get("wi", {}).get("cnt", 0)
                a["st_cnt"] += b.get("st", {}).get("cnt", 0)

    return {
        "weeks": weeks,
        "chan_weeks": chan_weeks,
        "daily_dates": daily_dstr,
        "daily_wd": [WEEKDAY_KR[d.weekday()] for d in daily_dates],
        "daily_weekend": [d.weekday() >= 5 for d in daily_dates],
        "today": today.strftime("%Y-%m-%d"),
        "cats": cats_out,
        "grand": grand,
    }


def compute_weekly(ref_date, today=None):
    """지정 기준일(ref_date)이 속한 주 + 직전 2주 주간 리포트 데이터. 독립 조회(경량)."""
    today = today or date.today()
    if isinstance(ref_date, str):
        ref_date = date.fromisoformat(ref_date)
    sku_list = B.build_sku_list()
    categories = B.load_json(B.CATEGORIES_FILE, [])
    cat_meta = {c["name"]: c for c in categories}
    codes = [s["card_code"] for s in sku_list]
    cat_order = [c["name"] for c in categories]
    for s in sku_list:
        if s["category"] and s["category"] not in cat_order:
            cat_order.append(s["category"])
    ref_ws = _sun_start(ref_date)
    fetch_from = ref_ws - timedelta(days=35)   # WoW(전전주·직전3주블록)까지 포함
    d_to = min(ref_ws + timedelta(days=6), today)
    if d_to < fetch_from:
        d_to = ref_ws + timedelta(days=6)
    sales = B.fetch_sku_daily(codes, fetch_from.strftime("%Y-%m-%d"), d_to.strftime("%Y-%m-%d"), batch_size=100)
    channel_sales = _fetch_channel_daily(codes, fetch_from.strftime("%Y-%m-%d"), d_to.strftime("%Y-%m-%d"))
    sku_list, cat_order, cat_meta, sales, channel_sales = _with_sf_poster(
        sku_list, cat_order, cat_meta, sales, channel_sales,
        fetch_from.strftime("%Y-%m-%d"), d_to.strftime("%Y-%m-%d"))
    return _build_weekly(sku_list, cat_order, cat_meta, sales, ref_date, today, channel_sales=channel_sales)


def _build_recommendations(cat_rows, forecast, rising, today, best_wd, wd_cnt, cat_top=None):
    cat_top = cat_top or {}
    recs = []
    # 활성 카테고리만 (최근 28일 주문 1건 이상)
    active = [c for c in cat_rows if c["total28"] >= 1]

    # R1. 모멘텀 급상승 → 기획전 밀어주기 (추천 기획전명 + 추천 상품 + 기획전 페이지 링크)
    for c in sorted(active, key=lambda x: -x["mom"]):
        if c["mom"] >= 40 and c["r7_cnt"] >= 3:
            tops = cat_top.get(c["name"], [])[:3]
            prod_names = [t["name"] for t in tops]
            promo_name = f"{c['icon']} 지금 뜨는 {c['name']} 기획전"
            recs.append({
                "level": "good", "icon": "🔥", "tag": "모멘텀 급상승",
                "title": f"{c['icon']} {c['name']} — 기획전으로 상승세 굳히기",
                "body": f"최근 7일 주문 {c['r7_cnt']}건으로 28일 평균({c['b28_avg7']}건/주) 대비 "
                        f"<b>+{c['mom']:.0f}%</b> 급증. 관심이 몰릴 때 기획전·상단 노출로 모멘텀을 극대화하세요.",
                "metric": f"+{c['mom']:.0f}%", "sort": -c["mom"],
                "promo_name": promo_name, "products": prod_names,
                "link": c["name"], "cta": "기획전 페이지 보기",
            })
    # R2. 급감 경보 → 선제 점검
    for c in sorted(active, key=lambda x: x["mom"]):
        if c["mom"] <= -40 and c["b28_avg7"] >= 1:
            recs.append({
                "level": "critical", "icon": "⚠️", "tag": "급감 경보",
                "title": f"{c['icon']} {c['name']} — 하락 원인 선제 점검",
                "body": f"최근 7일 주문 {c['r7_cnt']}건으로 평소({c['b28_avg7']}건/주) 대비 "
                        f"<b>{c['mom']:.0f}%</b> 급감. 노출 위치·품절·가격을 점검하고 반등 프로모션을 검토하세요.",
                "metric": f"{c['mom']:.0f}%", "sort": c["mom"] - 1000,
            })
    # R3. 크로스셀 기회 (동반율 낮은데 단독 볼륨 있음)
    for c in sorted(active, key=lambda x: -x["r7_st"]):
        if c["r7_cnt"] >= 3 and c["attach"] < 35 and c["r7_st"] >= 2:
            recs.append({
                "level": "warning", "icon": "🎁", "tag": "크로스셀 기회",
                "title": f"{c['icon']} {c['name']} — 청첩장 결제단계 번들 노출",
                "body": f"최근 7일 {c['r7_cnt']}건 중 단독구매가 {c['r7_st']}건(동반율 {c['attach']:.0f}%)로 낮음. "
                        f"청첩장 주문 흐름에 번들·추천으로 끼워 넣으면 부착률을 끌어올릴 여지가 큽니다.",
                "metric": f"동반율 {c['attach']:.0f}%", "sort": -c["r7_st"] + 50,
            })
    # R4. 성수기 선제 대응 (다음 달이 성수기)
    nxt = (today.month % 12) + 1
    if nxt in PEAK_MONTHS:
        wed = [c for c in active if any(h in c["name"] for h in WEDDING_CATS_HINT)]
        names = ", ".join(f"{c['icon']}{c['name']}" for c in sorted(wed, key=lambda x:-x['r7_amt'])[:4])
        recs.append({
            "level": "good", "icon": "📅", "tag": "성수기 선제",
            "title": f"다음 달 {nxt}월 = 결혼 성수기 — 웨딩소품 선제 준비",
            "body": f"{nxt}월은 예식이 몰리는 성수기입니다. {names} 등 웨딩 연동 상품의 재고·디자인·기획전을 "
                    f"지금 준비해 두면 수요 급증에 앞서 대응할 수 있습니다.",
            "metric": f"{nxt}월 성수기", "sort": 200,
        })
    # R5. 라이징 상품 스포트라이트 (추천 상품 = 상승 상품 상위)
    if rising:
        top = rising[0]
        prod_names = [r["name"] for r in rising[:3]]
        recs.append({
            "level": "good", "icon": "🌟", "tag": "라이징 상품",
            "title": f"신흥 인기 상품 — 기획전 대표로 내세우기",
            "body": f"<b>{top['name']}</b>({top['cat']})가 최근 7일 {top['r7']}건으로 직전 7일({top['p7']}건) 대비 "
                    f"+{top['delta']}건 상승. 상승 상품을 전면에 세우면 유입 대비 전환이 좋습니다.",
            "metric": f"+{top['delta']}건", "sort": 100,
            "promo_name": f"🌟 이번주 라이징 상품 기획전",
            "products": prod_names,
            "link": top["cat"], "cta": "기획전 페이지 보기",
        })
    # R6. 요일 타이밍
    if best_wd is not None and sum(wd_cnt) > 0:
        recs.append({
            "level": "info", "icon": "🗓️", "tag": "발송 타이밍",
            "title": f"주문이 몰리는 요일 = {WEEKDAY_KR[best_wd]}요일",
            "body": f"최근 4주 요일별 주문을 보면 <b>{WEEKDAY_KR[best_wd]}요일</b> 주문이 가장 많습니다"
                    f"({wd_cnt[best_wd]}건). 기획전 오픈·쿠폰 발송을 이 타이밍에 맞추면 노출 효율이 높습니다.",
            "metric": f"{WEEKDAY_KR[best_wd]}요일", "sort": 300,
        })

    recs.sort(key=lambda x: x["sort"])
    return recs


def _build_daily(dates, sales, sku_list, cat_order, cat_meta, today):
    """주어진 dates(리스트) × 카테고리/SKU 데일리 표 데이터 생성.
    sales 는 해당 기간을 포함하는 (code,date)->엔트리 맵."""
    dstr = [d.strftime("%Y-%m-%d") for d in dates]
    by_cat = defaultdict(list)
    for s in sku_list:
        by_cat[s["category"]].append(s)

    cats_out = []
    for cat in cat_order:
        skus = by_cat.get(cat, [])
        if not skus:
            continue
        meta = cat_meta.get(cat, {})
        skus_out = []
        has = False
        for s in skus:
            code = s["card_code"]
            day_vecs = []; tot = [0]*9
            for ds in dstr:
                v = _vec(sales.get((code, ds)))
                day_vecs.append(v); _add(tot, v)
            if tot[0] > 0:
                has = True
            skus_out.append({"code": code, "name": s.get("name",""),
                             "disc": bool(s.get("discontinued",False)),
                             "days": day_vecs, "total": tot})
        cats_out.append({"name": cat, "icon": meta.get("icon","📦"),
                         "color": meta.get("color","#37474F"), "bg": meta.get("bg","#ECEFF1"),
                         "has": has, "skus": skus_out})
    return {
        "date_from": dstr[0] if dstr else "",
        "date_to": dstr[-1] if dstr else "",
        "dates": dstr,
        "weekdays": [WEEKDAY_KR[d.weekday()] for d in dates],
        "is_weekend": [d.weekday() >= 5 for d in dates],
        "today": today.strftime("%Y-%m-%d"),
        "cats": cats_out,
    }


def compute_daily(date_from, date_to, today=None):
    """지정 기간의 데일리 표 데이터만 독립 조회 (모멘텀/예측과 무관 — 빠른 API용).
    기간을 바꿔도 무거운 전체 재계산 없이 이 함수만 호출한다."""
    today = today or date.today()
    if isinstance(date_from, str):
        date_from = date.fromisoformat(date_from)
    if isinstance(date_to, str):
        date_to = date.fromisoformat(date_to)
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    sku_list = B.build_sku_list()
    categories = B.load_json(B.CATEGORIES_FILE, [])
    cat_meta = {c["name"]: c for c in categories}
    codes = [s["card_code"] for s in sku_list]
    cat_order = [c["name"] for c in categories]
    for s in sku_list:
        if s["category"] and s["category"] not in cat_order:
            cat_order.append(s["category"])

    sales = B.fetch_sku_daily(codes, date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d"), batch_size=100)
    sku_list, cat_order, cat_meta, sales, _ = _with_sf_poster(
        sku_list, cat_order, cat_meta, sales, None,
        date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d"))
    days = (date_to - date_from).days + 1
    dates = [date_from + timedelta(days=i) for i in range(days)]
    return _build_daily(dates, sales, sku_list, cat_order, cat_meta, today)


if __name__ == "__main__":
    import io, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    r = compute()
    print("today:", r["today"], r["weekday"])
    print("KPI:", r["kpi"])
    print("forecast:", r["forecast"])
    print(f"추천 {len(r['recs'])}건:")
    for rec in r["recs"]:
        print(f"  [{rec['tag']}] {rec['title']} — {rec['metric']}")
    print("모멘텀 상위:")
    for c in sorted(r["cat_rows"], key=lambda x:-x["mom"])[:8]:
        print(f"  {c['name']}: r7={c['r7_cnt']} b28avg={c['b28_avg7']} mom={c['mom']}% attach={c['attach']}%")
