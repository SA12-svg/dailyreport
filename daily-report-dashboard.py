#!/usr/bin/env python3
"""바른손 데일리 리포트 대시보드 - 시트 자동화"""
import os
import json
import base64
import hmac
import time
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import pymssql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PORT = int(os.getenv('PORT', '10030'))

# ── 인증 ──
# 1) Google 로그인 (권장, 외부 공개용): GOOGLE_CLIENT_ID가 설정되면 활성화.
#    Google이 실제로 본인 확인을 해주므로 @ALLOWED_EMAIL_DOMAIN 계정만 통과.
# 2) Basic Auth (구 방식/로컬 테스트용): DASHBOARD_USER/DASHBOARD_PASSWORD 둘 다 설정 시 활성화.
# 둘 다 설정 안 하면 인증 비활성(로컬 개발 호환).
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
ALLOWED_EMAIL_DOMAIN = os.getenv('ALLOWED_EMAIL_DOMAIN', 'barunn.net')
GOOGLE_AUTH_ENABLED = bool(GOOGLE_CLIENT_ID)

AUTH_USER = os.getenv('DASHBOARD_USER', '')
AUTH_PASSWORD = os.getenv('DASHBOARD_PASSWORD', '')
BASIC_AUTH_ENABLED = bool(AUTH_USER and AUTH_PASSWORD) and not GOOGLE_AUTH_ENABLED
AUTH_ENABLED = GOOGLE_AUTH_ENABLED or BASIC_AUTH_ENABLED

# 세션 쿠키 서명 시크릿. 미설정 시 프로세스 시작마다 새로 생성(재시작하면 재로그인 필요 — 운영 배포시 고정값 권장).
SESSION_SECRET = os.getenv('SESSION_SECRET') or base64.b64encode(os.urandom(32)).decode()
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7일
SESSION_COOKIE_NAME = 'bs_session'

# 브랜드 매핑: (display_key, display_name, sales_gubun_list)
BRANDS = [
    ('barunson', '바른손카드', ['SB']),
    ('barunmall', '바른손몰', ['B', 'H']),
    ('deardeer', '디얼디어', ['SD']),
    ('premier', '프리미어페이퍼', ['SS']),
]
BRANDS_MAP = {key: gubuns for key, _, gubuns in BRANDS}
# 가입(S2_UserInfo.REFERER_SALES_GUBUN)은 sales_Gubun과 코드 체계가 약간 달라(BM 등) 별도 매핑 필요.
# 회원별 REFERER_SALES_GUBUN은 고정값(가입 시 유입/선택 브랜드)임을 실측 확인.
SIGNUP_GUBUN_MAP = {
    'barunson': ['SB'],
    'barunmall': ['B', 'BM', 'H'],
    'deardeer': ['SD'],
    'premier': ['SS'],
}
GIFT_ITEM_TYPES = ('T', 'A', 'P', 'R', 'D', 'B', 'W', 'L')
GIFT_TYPES_SQL = "(" + ",".join(f"'{t}'" for t in GIFT_ITEM_TYPES) + ")"
ALL_GUBUN = ['SB', 'B', 'H', 'SD', 'SS']
ALL_GUBUN_SQL = "('SB','B','H','SD','SS')"


def get_conn():
    return pymssql.connect(
        server=os.getenv("DB_SERVER"),
        port=int(os.getenv("DB_PORT", "1433")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="bar_shop1",
    )


def _brand_key(sg):
    """sales_Gubun → brand key"""
    for key, _, gubuns in BRANDS:
        if sg in gubuns:
            return key
    return None


def _empty_brand_dict(default):
    return {key: default() for key, _, _ in BRANDS}


def dates_for(base_str):
    base = datetime.strptime(base_str, '%Y-%m-%d')
    return {
        'base': base,
        'wow': base - timedelta(days=7),
        'mom': base - timedelta(days=30),
        'yoy': base - timedelta(weeks=52),  # 정확히 52주 전 = 항상 동일 요일 (날짜 기준 아님)
    }


# ─── 1. 샘플주문 수 (주문일 기준) ───
def fetch_sample(conn, dt):
    cur = conn.cursor(as_dict=True)
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute(f"""
        SELECT SALES_GUBUN as sg,
            CASE WHEN MEMBER_ID IS NOT NULL AND MEMBER_ID <> '' THEN 'member' ELSE 'guest' END as ut,
            ISNULL(isOneClickSample,'') as oc,
            COUNT(*) as cnt
        FROM CUSTOM_SAMPLE_ORDER
        WHERE REQUEST_DATE >= %s AND REQUEST_DATE < %s AND STATUS_SEQ >= 1
          AND SALES_GUBUN IN {ALL_GUBUN_SQL}
        GROUP BY SALES_GUBUN,
            CASE WHEN MEMBER_ID IS NOT NULL AND MEMBER_ID <> '' THEN 'member' ELSE 'guest' END,
            ISNULL(isOneClickSample,'')
    """, (d, d1))
    r = _empty_brand_dict(lambda: {'member': 0, 'guest': 0, 'oneclick': 0, 'total': 0,
                                    'guest_ratio': 0, 'oneclick_ratio': 0})
    for row in cur.fetchall():
        bk = _brand_key(row['sg'])
        if not bk:
            continue
        if row['ut'] == 'member':
            r[bk]['member'] += row['cnt']
        else:
            r[bk]['guest'] += row['cnt']
        if row['oc'].strip() == 'Y':
            r[bk]['oneclick'] += row['cnt']
    for bk in r:
        d_ = r[bk]
        d_['total'] = d_['member'] + d_['guest']
        d_['guest_ratio'] = round(d_['guest'] / d_['total'] * 100, 1) if d_['total'] else 0
        d_['oneclick_ratio'] = round(d_['oneclick'] / d_['total'] * 100, 1) if d_['total'] else 0
    return r


# ─── 2. 청첩장 주문 수 (결제일 기준) ───
def fetch_settle_count(conn, dt):
    cur = conn.cursor(as_dict=True)
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute(f"""
        SELECT sales_Gubun as sg, COUNT(DISTINCT order_seq) as cnt
        FROM custom_order
        WHERE settle_date >= %s AND settle_date < %s AND sales_Gubun IN {ALL_GUBUN_SQL}
        GROUP BY sales_Gubun
    """, (d, d1))
    r = _empty_brand_dict(lambda: {'total': 0})
    for row in cur.fetchall():
        bk = _brand_key(row['sg'])
        if bk:
            r[bk]['total'] += row['cnt']
    return r


# ─── 3. 청첩장 주문 매출액 (결제일 기준) ───
def fetch_settle_revenue(conn, dt):
    cur = conn.cursor(as_dict=True)
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute(f"""
        SELECT sales_Gubun as sg, SUM(settle_price) as rev
        FROM custom_order
        WHERE settle_date >= %s AND settle_date < %s AND sales_Gubun IN {ALL_GUBUN_SQL}
        GROUP BY sales_Gubun
    """, (d, d1))
    r = _empty_brand_dict(lambda: {'revenue': 0, 'revenue_no_gift': 0})
    for row in cur.fetchall():
        bk = _brand_key(row['sg'])
        if bk:
            r[bk]['revenue'] += row['rev'] or 0

    # 답례품 매출 (바른손카드만)
    cur.execute("""
        SELECT ISNULL(CAST(SUM(oi.item_sale_price * oi.item_count) AS INT), 0) as grev
        FROM custom_order o JOIN custom_order_item oi ON o.order_seq = oi.order_seq
        WHERE o.settle_date >= %s AND o.settle_date < %s
          AND o.sales_Gubun = 'SB' AND o.settle_cancel_date IS NULL
          AND oi.item_type IN ('T','A','P','R','D','B','W','L')
    """, (d, d1))
    gr = cur.fetchone()
    r['barunson']['revenue_no_gift'] = r['barunson']['revenue'] - (gr['grev'] if gr else 0)
    return r


# ─── 4. 청첩장 주문 수량 (결제일 기준) ───
def fetch_settle_qty(conn, dt):
    cur = conn.cursor(as_dict=True)
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute(f"""
        SELECT o.sales_Gubun as sg,
            SUM(CASE WHEN oi.item_type='C' THEN oi.item_count ELSE 0 END) as qty
        FROM custom_order o JOIN custom_order_item oi ON o.order_seq = oi.order_seq
        WHERE o.settle_date >= %s AND o.settle_date < %s AND o.sales_Gubun IN {ALL_GUBUN_SQL}
        GROUP BY o.sales_Gubun
    """, (d, d1))
    r = _empty_brand_dict(lambda: {'qty': 0})
    for row in cur.fetchall():
        bk = _brand_key(row['sg'])
        if bk:
            r[bk]['qty'] += row['qty'] or 0
    return r


# ─── 바른라운지 이용권 구매현황 (TB_Lounge_Voucher, 구매일 기준) ───
#   lounge.barunsoncard.com 판매는 custom_order/custom_order_item과 별개 시스템(Order_Seq만 채번 공유).
#   TB_Lounge_Voucher가 실제 구매 원장. 취소/환불성 상태는 방어적으로 제외.
def fetch_special_voucher(conn, dt):
    cur = conn.cursor(as_dict=True)
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute("""
        SELECT COUNT(DISTINCT Order_Seq) as cnt,
            ISNULL(SUM(Paid_Price), 0) as rev
        FROM TB_Lounge_Voucher
        WHERE Buy_DateTime >= %s AND Buy_DateTime < %s
          AND Sales_Gubun = 'SB'
          AND Status NOT IN ('CANCELLED', 'CANCELED', 'REFUNDED')
    """, (d, d1))
    row = cur.fetchone()
    return {'cnt': row['cnt'] or 0, 'rev': int(row['rev'] or 0)}


# ─── 청첩장 동반/단독 주문 비율 (결제일 기준) ───
#   동반=청첩장 주문에 답례품/굿즈성 상품(GIFT_ITEM_TYPES)이 함께 결제된 경우
#   단독=청첩장(+봉투 등 기본구성품)만 결제, 답례품/굿즈 없음. 브랜드별 + 전체(all).
#   ※ item_type<>'C' 전체를 기준으로 하면 봉투(E)·서비스(S) 등 거의 모든 주문에 붙는
#     기본 구성품까지 "동반"으로 잡혀 99%대로 무의미해짐 → GIFT_ITEM_TYPES로 한정.
def _fetch_bundle_ratio_range(conn, d_from, d_to):
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""
      SELECT sg, grp, COUNT(*) cnt, SUM(settle_price) rev FROM (
        SELECT o.order_seq, o.sales_Gubun sg, o.settle_price,
          CASE WHEN EXISTS (
            SELECT 1 FROM custom_order_item oi2
            WHERE oi2.order_seq = o.order_seq AND oi2.item_type IN {GIFT_TYPES_SQL}
          ) THEN 'bundle' ELSE 'solo' END grp
        FROM custom_order o
        WHERE o.settle_date >= %s AND o.settle_date < %s AND o.settle_cancel_date IS NULL
          AND o.sales_Gubun IN {ALL_GUBUN_SQL}
      ) t GROUP BY sg, grp""", (d_from, d_to))

    def _blank():
        return {'bundle': 0, 'solo': 0, 'bundle_rev': 0, 'solo_rev': 0}

    by_brand, all_g = {}, _blank()
    for r in cur.fetchall():
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        d = by_brand.setdefault(bk, _blank())
        d[r['grp']] += r['cnt']
        d[f"{r['grp']}_rev"] += int(r['rev'] or 0)
        all_g[r['grp']] += r['cnt']
        all_g[f"{r['grp']}_rev"] += int(r['rev'] or 0)

    def _finish(d):
        tot = d['bundle'] + d['solo']
        d['total'] = tot
        d['bundle_ratio'] = round(d['bundle'] / tot * 100, 1) if tot else 0
        d['solo_ratio'] = round(d['solo'] / tot * 100, 1) if tot else 0
        return d

    out = {'all': _finish(all_g)}
    for key, _, _g in BRANDS:
        out[key] = _finish(by_brand.get(key, _blank()))
    return out


def fetch_bundle_ratio(conn, s, e):
    """30일 윈도 버전 (인사이트용). s,e는 'YYYY-MM-DD' 문자열."""
    return _fetch_bundle_ratio_range(conn, s, e)


def fetch_bundle_ratio_day(conn, dt):
    """단일 일자 버전 (메인 데일리 표 WoW/MoM/YoY용)."""
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    return _fetch_bundle_ratio_range(conn, d, d1)


# ─── 5,6,7. 배송일 기준 (주문수, 매출, 수량) ───
def fetch_delivery(conn, dt):
    cur = conn.cursor(as_dict=True)
    d, d1 = dt.strftime('%Y-%m-%d'), (dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cur.execute(f"""
        SELECT o.sales_Gubun as sg,
            CASE WHEN o.member_id IS NOT NULL AND o.member_id <> '' THEN 'member' ELSE 'guest' END as ut,
            COUNT(DISTINCT o.order_seq) as cnt,
            SUM(o.settle_price) as rev,
            SUM(oi.qty) as qty
        FROM custom_order o
        CROSS APPLY (
            SELECT SUM(CASE WHEN item_type='C' THEN item_count ELSE 0 END) as qty
            FROM custom_order_item WHERE order_seq = o.order_seq
        ) oi
        WHERE o.src_send_date >= %s AND o.src_send_date < %s
          AND o.sales_Gubun IN {ALL_GUBUN_SQL}
        GROUP BY o.sales_Gubun,
            CASE WHEN o.member_id IS NOT NULL AND o.member_id <> '' THEN 'member' ELSE 'guest' END
    """, (d, d1))
    r = _empty_brand_dict(lambda: {
        'member_cnt': 0, 'guest_cnt': 0, 'total_cnt': 0,
        'member_rev': 0, 'guest_rev': 0, 'total_rev': 0,
        'member_qty': 0, 'guest_qty': 0, 'total_qty': 0,
    })
    for row in cur.fetchall():
        bk = _brand_key(row['sg'])
        if not bk:
            continue
        pfx = 'member' if row['ut'] == 'member' else 'guest'
        r[bk][f'{pfx}_cnt'] += row['cnt'] or 0
        r[bk][f'{pfx}_rev'] += row['rev'] or 0
        r[bk][f'{pfx}_qty'] += row['qty'] or 0
    for bk in r:
        for s in ('cnt', 'rev', 'qty'):
            r[bk][f'total_{s}'] = r[bk][f'member_{s}'] + r[bk][f'guest_{s}']
    return r


def fetch_all(base_str):
    periods = dates_for(base_str)
    conn = get_conn()
    data = {}
    for pk, dt in periods.items():
        data[pk] = {
            'date': dt.strftime('%Y-%m-%d'),
            'wd': ['월','화','수','목','금','토','일'][dt.weekday()],
            'sample': fetch_sample(conn, dt),
            'settle_cnt': fetch_settle_count(conn, dt),
            'settle_rev': fetch_settle_revenue(conn, dt),
            'settle_qty': fetch_settle_qty(conn, dt),
            'special_voucher': fetch_special_voucher(conn, dt),
            'delivery': fetch_delivery(conn, dt),
            'bundle': fetch_bundle_ratio_day(conn, dt),
        }
    conn.close()
    return {'base_date': base_str, 'periods': data,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


# ══════════════════════════════════════════════════════════════════
#  인사이트 (상세정보 + 급감경고 + 진단/예측)  — /api/insights
# ══════════════════════════════════════════════════════════════════
def _dec(s):
    """varchar 한글(cp949)이 latin1로 잘못 디코드된 것 보정"""
    if not isinstance(s, str):
        return s
    try:
        return s.encode('latin1').decode('cp949')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _sg_in(gubuns):
    return "(" + ",".join(f"'{g}'" for g in gubuns) + ")"


# ── 일별 시계열 (metric: 'sample_guest' | 'settle_cnt' | 'settle_rev') ──
def daily_series(conn, gubuns, metric, end_dt, days=56):
    cur = conn.cursor(as_dict=True)
    start = (end_dt - timedelta(days=days - 1)).strftime('%Y-%m-%d')
    end = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    sgin = _sg_in(gubuns)
    if metric == 'sample_guest':
        sql = f"""SELECT CONVERT(char(10),REQUEST_DATE,23) d, COUNT(*) v
            FROM CUSTOM_SAMPLE_ORDER
            WHERE REQUEST_DATE>=%s AND REQUEST_DATE<%s AND STATUS_SEQ>=1
              AND SALES_GUBUN IN {sgin} AND (MEMBER_ID IS NULL OR MEMBER_ID='')
            GROUP BY CONVERT(char(10),REQUEST_DATE,23)"""
    elif metric == 'settle_cnt':
        sql = f"""SELECT CONVERT(char(10),settle_date,23) d, COUNT(DISTINCT order_seq) v
            FROM custom_order WHERE settle_date>=%s AND settle_date<%s
              AND settle_cancel_date IS NULL AND sales_Gubun IN {sgin}
            GROUP BY CONVERT(char(10),settle_date,23)"""
    else:  # settle_rev
        sql = f"""SELECT CONVERT(char(10),settle_date,23) d, SUM(settle_price) v
            FROM custom_order WHERE settle_date>=%s AND settle_date<%s
              AND settle_cancel_date IS NULL AND sales_Gubun IN {sgin}
            GROUP BY CONVERT(char(10),settle_date,23)"""
    cur.execute(sql, (start, end))
    m = {r['d']: (r['v'] or 0) for r in cur.fetchall()}
    return [((end_dt - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d'),
             m.get((end_dt - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d'), 0))
            for i in range(days)]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0


# ── 급감 레벨 판정 (공통) ──
#   recent(관측치)가 base(기준선) 대비 얼마나 빠졌는지로 red/yellow 판정
def _level(recent, base):
    drop = (recent - base) / base
    if recent < base * 0.2 or drop <= -0.6:
        return 'red', drop
    if drop <= -0.35:
        return 'yellow', drop
    return None, drop


# ── 급감 감지(추세): 최근7일 평균 vs 직전 28일(8~35일전) 평균 ──
#   min_base: 기준선(직전28일 일평균)이 이 값 미만이면 초소형 볼륨으로 보고 경고 제외(노이즈 방지)
def detect(series, min_base):
    vals = [v for _, v in series]
    if len(vals) < 35:
        return None
    recent = _mean(vals[-7:])
    base = _mean(vals[-35:-7])
    if base < min_base:
        return None
    level, drop = _level(recent, base)
    return {'kind': 'trend', 'window': '최근7일 평균 vs 직전28일 평균',
            'recent': round(recent, 1), 'base': round(base, 1),
            'drop_pct': round(drop * 100, 1), 'level': level}


# ── 급감 감지(당일): 기준일 당일 vs 직전 7일(2~8일전) 평균 ──
#   하루 만에 발생한 급락을 7일 평균에 희석되기 전에 즉시 포착.
#   ※ 기준일 데이터가 미집계(당일 진행중)면 오탐 가능 → 완료된 날짜 기준 조회 권장.
def detect_daily(series, min_base):
    vals = [v for _, v in series]
    if len(vals) < 8:
        return None
    today = vals[-1]
    base = _mean(vals[-8:-1])
    if base < min_base:
        return None
    level, drop = _level(today, base)
    return {'kind': 'daily', 'window': '기준일 당일 vs 직전7일 평균',
            'recent': round(today, 1), 'base': round(base, 1),
            'drop_pct': round(drop * 100, 1), 'level': level}


METRIC_LABEL = {'sample_guest': '비회원 샘플주문', 'settle_cnt': '결제 주문수', 'settle_rev': '결제 매출'}
# 지표별 최소 기준선(일평균): 이 이하 볼륨 브랜드/지표는 급감 판정에서 제외
METRIC_MIN_BASE = {'sample_guest': 3, 'settle_cnt': 5, 'settle_rev': 1_000_000}


def build_alerts(conn, end_dt):
    alerts = []
    for key, name, gubuns in BRANDS:
        for metric in ('sample_guest', 'settle_cnt', 'settle_rev'):
            series = daily_series(conn, gubuns, metric, end_dt)
            min_base = METRIC_MIN_BASE[metric]
            for r in (detect_daily(series, min_base), detect(series, min_base)):
                if r and r['level']:
                    alerts.append({'brand': name, 'metric': METRIC_LABEL[metric],
                                   'level': r['level'], 'kind': r['kind'],
                                   'window': r['window'], 'recent': r['recent'],
                                   'base': r['base'], 'drop_pct': r['drop_pct']})
    # 당일 신호 먼저, red 먼저, 낙폭 큰 순
    alerts.sort(key=lambda a: (a['kind'] != 'daily', a['level'] != 'red', a['drop_pct']))
    return alerts


def fetch_leadtime(conn, s, e):
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""
      SELECT sg, band, COUNT(*) cnt FROM (
        SELECT o.sales_Gubun sg,
          DATEDIFF(day,o.settle_date,TRY_CONVERT(date,
            o.ey+'-'+RIGHT('0'+o.em,2)+'-'+RIGHT('0'+o.ed,2))) ld
        FROM (SELECT o.sales_Gubun,o.settle_date,w.event_year ey,w.event_month em,w.event_Day ed
              FROM custom_order o JOIN custom_order_WeddInfo w ON o.order_seq=w.order_seq
              WHERE o.settle_date>=%s AND o.settle_date<%s AND o.settle_cancel_date IS NULL
                AND o.sales_Gubun IN {ALL_GUBUN_SQL} AND w.event_year IS NOT NULL AND w.event_year<>'') o
      ) x
      CROSS APPLY (SELECT CASE WHEN ld<30 THEN '0-29' WHEN ld<45 THEN '30-44'
        WHEN ld<60 THEN '45-59' WHEN ld<90 THEN '60-89' ELSE '90+' END band) b
      WHERE ld BETWEEN 0 AND 400
      GROUP BY sg, band""", (s, e))
    out = {}
    for r in cur.fetchall():
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        out.setdefault(bk, {})[r['band']] = r['cnt']
    return out


def fetch_top_products(conn, s, e, top=15):
    """브랜드별 + 전체(all) TOP N. item_type='C'(청첩장) 한정."""
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""
      SELECT o.sales_Gubun sg, c.Card_Name nm, SUM(oi.item_count) qty,
        COUNT(DISTINCT o.order_seq) ords, CAST(AVG(oi.item_sale_price) AS int) avgp
      FROM custom_order o JOIN custom_order_item oi ON o.order_seq=oi.order_seq
      JOIN S2_Card c ON oi.card_seq=c.Card_Seq
      WHERE o.settle_date>=%s AND o.settle_date<%s AND o.settle_cancel_date IS NULL
        AND oi.item_type='C' AND o.sales_Gubun IN {ALL_GUBUN_SQL}
      GROUP BY o.sales_Gubun, c.Card_Name""", (s, e))
    by_brand = {}
    all_rows = {}
    for r in cur.fetchall():
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        row = {'name': _dec(r['nm']), 'qty': r['qty'], 'ords': r['ords'], 'avgp': r['avgp']}
        by_brand.setdefault(bk, []).append(row)
        a = all_rows.setdefault(row['name'], {'name': row['name'], 'qty': 0, 'ords': 0, '_avgp_sum': 0, '_n': 0})
        a['qty'] += row['qty']; a['ords'] += row['ords']
        a['_avgp_sum'] += row['avgp'] * row['qty']; a['_n'] += row['qty']
    out = {'all': sorted(
        [{'name': a['name'], 'qty': a['qty'], 'ords': a['ords'],
          'avgp': round(a['_avgp_sum'] / a['_n']) if a['_n'] else 0} for a in all_rows.values()],
        key=lambda x: -x['qty'])[:top]}
    for bk, rows in by_brand.items():
        out[bk] = sorted(rows, key=lambda x: -x['qty'])[:top]
    return out


def fetch_sheet_dist(conn, s, e):
    """브랜드별 + 전체(all) 주문당 장수 분포."""
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""
      SELECT sg, band, COUNT(*) orders FROM (
        SELECT o.order_seq, o.sales_Gubun sg, CASE WHEN SUM(oi.item_count)<100 THEN '<100'
          WHEN SUM(oi.item_count)<150 THEN '100-149' WHEN SUM(oi.item_count)<200 THEN '150-199'
          WHEN SUM(oi.item_count)<300 THEN '200-299' ELSE '300+' END band
        FROM custom_order o JOIN custom_order_item oi ON o.order_seq=oi.order_seq
        WHERE o.settle_date>=%s AND o.settle_date<%s AND o.settle_cancel_date IS NULL
          AND oi.item_type='C' AND o.sales_Gubun IN {ALL_GUBUN_SQL}
        GROUP BY o.order_seq, o.sales_Gubun) t GROUP BY sg, band""", (s, e))
    out = {'all': {}}
    for r in cur.fetchall():
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        out.setdefault(bk, {})[r['band']] = r['orders']
        out['all'][r['band']] = out['all'].get(r['band'], 0) + r['orders']
    return out


def fetch_revenue_structure(conn, s, e):
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""SELECT sales_Gubun sg,
        CASE WHEN member_id IS NOT NULL AND member_id<>'' THEN 'm' ELSE 'g' END ut,
        SUM(settle_price) rev, COUNT(DISTINCT order_seq) cnt
      FROM custom_order WHERE settle_date>=%s AND settle_date<%s
        AND settle_cancel_date IS NULL AND sales_Gubun IN {ALL_GUBUN_SQL}
      GROUP BY sales_Gubun, CASE WHEN member_id IS NOT NULL AND member_id<>'' THEN 'm' ELSE 'g' END""",
                (s, e))
    struct = {}
    for r in cur.fetchall():
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        d = struct.setdefault(bk, {'rev': 0, 'cnt': 0, 'm_rev': 0, 'g_rev': 0})
        d['rev'] += r['rev'] or 0
        d['cnt'] += r['cnt']
        d['m_rev' if r['ut'] == 'm' else 'g_rev'] += r['rev'] or 0
    return struct


def fetch_forecast(conn, base_dt):
    """당월 매출 예측: MTD 런레이트 + 작년 동월 실적 비교. 브랜드별 + 전체(all)."""
    cur = conn.cursor(as_dict=True)
    mstart = base_dt.replace(day=1)
    nmonth = (mstart + timedelta(days=32)).replace(day=1)
    days_in_month = (nmonth - mstart).days
    days_elapsed = (base_dt - mstart).days + 1

    def _by_brand_rev(d_from, d_to):
        cur.execute(f"""SELECT sales_Gubun sg, SUM(settle_price) rev FROM custom_order
            WHERE settle_date>=%s AND settle_date<%s AND settle_cancel_date IS NULL
              AND sales_Gubun IN {ALL_GUBUN_SQL} GROUP BY sales_Gubun""", (d_from, d_to))
        out = {}
        for r in cur.fetchall():
            bk = _brand_key(r['sg'])
            if bk:
                out[bk] = r['rev'] or 0
        return out

    mtd_by = _by_brand_rev(mstart.strftime('%Y-%m-%d'), (base_dt + timedelta(days=1)).strftime('%Y-%m-%d'))
    ly_s = mstart.replace(year=mstart.year - 1)
    ly_e = nmonth.replace(year=nmonth.year - 1)
    ly_by = _by_brand_rev(ly_s.strftime('%Y-%m-%d'), ly_e.strftime('%Y-%m-%d'))

    def _one(mtd, ly):
        proj = int(mtd / days_elapsed * days_in_month) if days_elapsed else 0
        return {'mtd': int(mtd), 'days_elapsed': days_elapsed, 'days_in_month': days_in_month,
                'projected': proj, 'last_year_month': int(ly),
                'yoy_pct': round((proj - ly) / ly * 100, 1) if ly else None,
                'month': mstart.strftime('%Y-%m')}

    out = {'all': _one(sum(mtd_by.values()), sum(ly_by.values()))}
    for key, _, _g in BRANDS:
        out[key] = _one(mtd_by.get(key, 0), ly_by.get(key, 0))
    return out


def fetch_cart(conn):
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT COUNT(*) c FROM UserBasket WHERE ExpirationDate >= GETDATE()")
    return {'active': cur.fetchone()['c'],
            'note': '활성 장바구니 수(만료 전). ※현 스키마상 담은 시각·주문 연결 로그가 없어 담기→주문 소요일정은 산출 불가.'}


def build_diagnosis(alerts, rev_struct, forecast, leadtime):
    """규칙 기반 핵심진단 / 권장액션"""
    core, actions = [], []
    reds = [a for a in alerts if a['level'] == 'red']
    yels = [a for a in alerts if a['level'] == 'yellow']
    if reds:
        for a in reds:
            tag = '당일급감' if a['kind'] == 'daily' else '추세급감'
            core.append(f"🔴 [{tag}] {a['brand']} {a['metric']} — {a['window']} {a['recent']} vs {a['base']} ({a['drop_pct']}%)")
            actions.append(f"{a['brand']} {a['metric']} 유입/집계 경로 즉시 점검 (광고·검색유입·트래킹 장애 여부)")
    if yels:
        for a in yels:
            tag = '당일' if a['kind'] == 'daily' else '추세'
            core.append(f"🟡 [{tag}] {a['brand']} {a['metric']} 하락 주의 ({a['drop_pct']}%)")
    if not reds and not yels:
        core.append("✅ 감시 지표(비회원샘플·결제주문수·결제매출)에서 유의미한 급감 신호 없음")
    # 매출 구조 요약
    tot = sum(d['rev'] for d in rev_struct.values()) or 1
    top_brand = max(rev_struct.items(), key=lambda kv: kv[1]['rev'], default=(None, None))
    if top_brand[0]:
        bn = dict((k, n) for k, n, _ in BRANDS)[top_brand[0]]
        core.append(f"최근 30일 매출 1위 {bn} (비중 {round(top_brand[1]['rev']/tot*100,1)}%)")
    # 예측 (전체 브랜드 합산 기준)
    fc = forecast.get('all', {})
    if fc.get('yoy_pct') is not None:
        arrow = '▲' if fc['yoy_pct'] >= 0 else '▼'
        core.append(f"당월({fc['month']}) 예상매출 {fc['projected']:,}원 — 작년동월 대비 {arrow}{abs(fc['yoy_pct'])}%")
        if fc['yoy_pct'] <= -10:
            actions.append(f"당월 예상매출이 작년 대비 {fc['yoy_pct']}% — 프로모션/객단가 방어 검토")
    if not actions:
        actions.append("현재 특이 하락 없음 — 정상 운영 유지, 상위 상품 재고/노출 지속")
    return {'core': core, 'actions': actions}


# ── 예식월 수요 분포: 지금 결제가 어떤 예식월을 향하는가 (선제 제안 근거) ──
def fetch_wedding_month_demand(conn, s, e):
    """브랜드별 + 전체(all)."""
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""
      SELECT o.sales_Gubun sg, w.event_year+'-'+RIGHT('0'+w.event_month,2) ym,
        COUNT(DISTINCT o.order_seq) ords
      FROM custom_order o JOIN custom_order_WeddInfo w ON o.order_seq=w.order_seq
      WHERE o.settle_date>=%s AND o.settle_date<%s AND o.settle_cancel_date IS NULL
        AND o.sales_Gubun IN {ALL_GUBUN_SQL} AND w.event_year IS NOT NULL AND w.event_year<>''
        AND TRY_CONVERT(date, w.event_year+'-'+RIGHT('0'+w.event_month,2)+'-'+RIGHT('0'+w.event_Day,2)) >= %s
      GROUP BY o.sales_Gubun, w.event_year+'-'+RIGHT('0'+w.event_month,2)""", (s, e, s))
    by_brand = {}
    all_ym = {}
    for r in cur.fetchall():
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        by_brand.setdefault(bk, {})[r['ym']] = by_brand.get(bk, {}).get(r['ym'], 0) + r['ords']
        all_ym[r['ym']] = all_ym.get(r['ym'], 0) + r['ords']

    def _finish(ym_cnt):
        rows = [(ym, c) for ym, c in ym_cnt.items() if c >= 5]
        rows.sort(key=lambda x: -x[1])
        tot = sum(c for _, c in rows) or 1
        return [{'ym': ym, 'ords': c, 'pct': round(c / tot * 100, 1)} for ym, c in rows]

    out = {'all': _finish(all_ym)}
    for bk in by_brand:
        out[bk] = _finish(by_brand[bk])
    return out


# ── 한국 캘린더 (예식/굿즈 사업 훅) ──
_SOLAR_EVENTS = [
    (1, 1, '신정', '연말연시', '새해 인사/감사 굿즈, 새해 첫 예식 시즌 오픈'),
    (2, 14, '발렌타인데이', '기념일', '커플 타깃 — 청첩장/축하 굿즈 감성 프로모션'),
    (3, 1, '삼일절', '공휴일', '연휴 배송·제작 일정 공지'),
    (3, 14, '화이트데이', '기념일', '커플 타깃 프로모션 · 봄 예식 시즌 상품 전면'),
    (5, 8, '어버이날', '가정의달', '감사 굿즈/답례품 수요 — 관련 상품 노출 강화'),
    (5, 21, '부부의날', '기념일', '부부/커플 감성 마케팅, 결혼 준비 콘텐츠'),
    (6, 6, '현충일', '공휴일', '연휴 배송·제작 일정 공지'),
    (8, 15, '광복절', '공휴일', '연휴 배송·제작 일정 공지 · 가을 예식 컬렉션 예열'),
    (10, 3, '개천절', '공휴일', '연휴 배송·제작 일정 공지'),
    (10, 9, '한글날', '공휴일', '연휴 배송·제작 일정 공지'),
    (11, 11, '빼빼로데이', '기념일', '굿즈/선물 프로모션'),
    (12, 25, '크리스마스', '연말', '연말 감사 굿즈 · 겨울 감성 컬렉션 · 연말 예식'),
]
# 음력 명절 (제작·배송 장기 리드타임이라 별도 취급)
_LUNAR = {
    '설날': {2025: '2025-01-29', 2026: '2026-02-17', 2027: '2027-02-06'},
    '추석': {2025: '2025-10-06', 2026: '2026-09-25', 2027: '2027-09-15'},
}
_HOLIDAY_HOOK = '명절 가족모임 → 상견례·예식 결정 증가로 직후 샘플/문의 급증. 명절 배송중단·제작일정 사전 공지, 성수기 재고 확보.'


def _upcoming_events(base_dt, horizon=45):
    res = []
    for (m, d, name, tag, hook) in _SOLAR_EVENTS:
        for yr in (base_dt.year, base_dt.year + 1):
            try:
                ev = datetime(yr, m, d)
            except ValueError:
                continue
            diff = (ev - base_dt).days
            if 0 <= diff <= horizon:
                res.append((diff, name, tag, hook))
                break
    # 명절: 가장 가까운 다음 것 1개 (호라이즌 무관, 장기 대비)
    for name, hook in (('설날', _HOLIDAY_HOOK), ('추석', _HOLIDAY_HOOK)):
        best = None
        for yr, ds in _LUNAR[name].items():
            ev = datetime.strptime(ds, '%Y-%m-%d')
            diff = (ev - base_dt).days
            if 0 <= diff and (best is None or diff < best[0]):
                best = (diff, name, '명절', hook)
        if best and best[0] <= 90:
            res.append(best)
    res.sort()
    return res


def _lead_label(d):
    if d <= 3:
        return f'🔴 D-{d} 임박'
    if d <= 14:
        return f'🟠 D-{d} 지금 준비'
    return f'🟡 D-{d} 사전 기획'


_SEASON = {1: '겨울 비수기', 2: '겨울 비수기', 3: '봄 성수기', 4: '봄 성수기', 5: '봄 성수기',
           6: '초여름', 7: '여름 비수기', 8: '여름 비수기', 9: '가을 성수기',
           10: '가을 성수기', 11: '가을 성수기', 12: '연말'}


# ── 선제 제안 엔진: 예식월 역산 + 계절/공휴일 + 베스트셀러 ──
def build_proactive(base_dt, top_products, wedding_demand):
    sug = []
    # 1) 시즌 수요창 (예식월 역산) — 가장 강한 선행 신호
    if wedding_demand:
        top = wedding_demand[:3]
        lead_ym = top[0]['ym']
        try:
            lead_month = int(lead_ym.split('-')[1])
            season = _SEASON.get(lead_month, '')
        except (ValueError, IndexError):
            season = ''
        share = ' · '.join(f"{t['ym'][5:]}월 {t['pct']}%" for t in top)
        sug.append({'lead': '지금', 'tag': '시즌수요',
            'text': f"현재 결제 주문의 예식월: {share}. {season} 수요가 유입 중 → "
                    f"{season} 컬렉션·베스트셀러를 메인 전면 배치하고 지금이 '{season} 기획전' 적기."})
        # 신제품 타이밍
        sug.append({'lead': '1~2주', 'tag': '신제품',
            'text': f"신제품 매주 출시 시: 다음 2~4주 출시분은 {season}({lead_ym[:4]}년 {lead_month}월 예식) 테마로 구성 — "
                    f"수요 유입기 초반에 노출해야 검색·샘플 단계를 선점."})
    # 2) 베스트셀러 기획전/할인
    if top_products:
        names = [p['name'] for p in top_products[:3]]
        avgp = [p['avgp'] for p in top_products[:5] if p['avgp']]
        band = f"평균 장당 {round(sum(avgp)/len(avgp)):,}원대" if avgp else ''
        sug.append({'lead': '이번 주', 'tag': '기획전',
            'text': f"베스트셀러 「{', '.join(names)}」 묶음 한정 할인/세트 기획전으로 회전 가속 ({band} 집중). "
                    f"상위권은 이미 검증된 수요라 할인 탄력이 큼."})
        # 가격대 다변화
        sug.append({'lead': '1~2주', 'tag': '객단가',
            'text': "상위 상품이 특정 가격대에 몰려 있으면 객단가 정체 위험 → 프리미엄(고단가) 라인을 인기상품 옆에 큐레이션해 업셀 유도."})
    # 3) 다가오는 공휴일/기념일/명절
    for (d, name, tag, hook) in _upcoming_events(base_dt):
        sug.append({'lead': _lead_label(d), 'tag': tag,
            'text': f"{name}({(base_dt+timedelta(days=d)).strftime('%m/%d')}, D-{d}) — {hook}"})
    return sug


def fetch_insights(base_str):
    base_dt = datetime.strptime(base_str, '%Y-%m-%d')
    s = (base_dt - timedelta(days=29)).strftime('%Y-%m-%d')
    e = (base_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    conn = get_conn()
    alerts = build_alerts(conn, base_dt)
    rev_struct = fetch_revenue_structure(conn, s, e)
    forecast = fetch_forecast(conn, base_dt)
    leadtime = fetch_leadtime(conn, s, e)
    top_products = fetch_top_products(conn, s, e)
    wedding_demand = fetch_wedding_month_demand(conn, s, e)
    out = {
        'base': base_str, 'window': f'{s} ~ {base_str} (30일)',
        'alerts': alerts,
        'leadtime': leadtime,
        'top_products': top_products,
        'sheet_dist': fetch_sheet_dist(conn, s, e),
        'revenue_structure': rev_struct,
        'forecast': forecast,
        'cart': fetch_cart(conn),
        'wedding_demand': wedding_demand,
        'bundle_ratio_30d': fetch_bundle_ratio(conn, s, e),
        'proactive': build_proactive(base_dt, top_products.get('all', []), wedding_demand.get('all', [])),
        'diagnosis': build_diagnosis(alerts, rev_struct, forecast, leadtime),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    conn.close()
    return out


# ══════════════════════════════════════════════════════════════════
#  가입→샘플→구매 퍼널 (코호트 기반 실측 전환율)  — /api/funnel
# ══════════════════════════════════════════════════════════════════
FUNNEL_WINDOWS = [('24h', timedelta(hours=24)), ('48h', timedelta(hours=48)),
                  ('1w', timedelta(days=7)), ('2w', timedelta(days=14)),
                  ('3w', timedelta(days=21)), ('4w', timedelta(days=28))]


def _week_start(d):
    return (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def fetch_funnel(base_str, weeks=8, brand=None):
    base_dt = datetime.strptime(base_str, '%Y-%m-%d')
    this_week_start = _week_start(base_dt)
    first_week_start = this_week_start - timedelta(weeks=weeks - 1)
    range_end = this_week_start + timedelta(days=7)
    buf_end = range_end + timedelta(days=35)  # 코호트 마지막 주까지 4주 전환 추적 여유
    fws, re_, be_ = first_week_start.strftime('%Y-%m-%d'), range_end.strftime('%Y-%m-%d'), buf_end.strftime('%Y-%m-%d')

    signup_flt, sample_flt, order_flt = '', '', ''
    if brand and brand in SIGNUP_GUBUN_MAP:
        signup_flt = "AND REFERER_SALES_GUBUN IN (" + ",".join(f"'{g}'" for g in SIGNUP_GUBUN_MAP[brand]) + ")"
        sg = BRANDS_MAP.get(brand, [])
        sample_flt = "AND SALES_GUBUN IN (" + ",".join(f"'{g}'" for g in sg) + ")" if sg else ''
        order_flt = "AND sales_Gubun IN (" + ",".join(f"'{g}'" for g in sg) + ")" if sg else ''

    # 상관 서브쿼리 대신 3개의 단순 인덱스 스캔 + 파이썬 조인.
    # 실측상 하나의 커넥션으로 여러 쿼리를 연달아 실행하면 일정 시간(~13초) 후 서버가 세션을 끊는 현상이 있어
    # (Azure SQL 리소스 거버너 추정) 쿼리마다 커넥션을 새로 열고 바로 닫는다.
    def run(sql, params):
        c = get_conn()
        try:
            cu = c.cursor(as_dict=True)
            cu.execute(sql, params)
            return cu.fetchall()
        finally:
            c.close()

    # 가입: S2_UserInfo는 PK가 (uid, site_div) 복합키라 회원당 여러 행 가능 → uid로 GROUP BY 필수
    # REFERER_SALES_GUBUN은 회원별 고정값(가입 시 유입 브랜드)이라 MIN()으로 대표값 사용
    signup_rows = run(f"""
        SELECT uid, MIN(reg_date) as reg_date FROM S2_UserInfo
        WHERE reg_date >= %s AND reg_date < %s {signup_flt} GROUP BY uid
    """, (fws, re_))

    # 샘플: 가입 코호트 구간 + 전환추적 버퍼까지 전체 샘플요청 (uid, 요청일)
    sample_rows = run(f"""
        SELECT MEMBER_ID as uid, REQUEST_DATE as d FROM CUSTOM_SAMPLE_ORDER
        WHERE STATUS_SEQ >= 1 AND MEMBER_ID IS NOT NULL AND MEMBER_ID <> ''
          AND REQUEST_DATE >= %s AND REQUEST_DATE < %s {sample_flt}
    """, (fws, be_))

    # 결제: 가입/샘플 코호트 구간 + 전환추적 버퍼까지 전체 결제완료 주문 (uid, 결제일)
    order_rows = run(f"""
        SELECT member_id as uid, settle_date as d FROM custom_order
        WHERE settle_date IS NOT NULL AND settle_cancel_date IS NULL
          AND settle_date >= %s AND settle_date < %s {order_flt}
    """, (fws, be_))

    sample_by_uid, order_by_uid = {}, {}
    for r in sample_rows:
        sample_by_uid.setdefault(r['uid'], []).append(r['d'])
    for r in order_rows:
        order_by_uid.setdefault(r['uid'], []).append(r['d'])

    def first_after(dates, anchor):
        after = [d for d in dates if d >= anchor]
        return min(after) if after else None

    signups = []
    for r in signup_rows:
        uid, rd = r['uid'], r['reg_date']
        signups.append({
            'uid': uid, 'reg_date': rd,
            'first_sample': first_after(sample_by_uid.get(uid, []), rd),
            'first_order': first_after(order_by_uid.get(uid, []), rd),
        })
    samples = []
    for r in sample_rows:
        uid, rq = r['uid'], r['d']
        samples.append({'uid': uid, 'req_date': rq, 'first_order': first_after(order_by_uid.get(uid, []), rq)})

    now = datetime.now()
    WIN_NAMES = [w for w, _ in FUNNEL_WINDOWS]

    def rate(rows, anchor_k, target_k, win):
        if not rows:
            return None
        hit = sum(1 for r in rows if r[target_k] is not None and r[target_k] - r[anchor_k] <= win)
        return round(hit / len(rows) * 100, 2)

    def build_metric(rows, anchor_k, target_k, wk_end):
        vals = {}
        for wname, win in FUNNEL_WINDOWS:
            measurable = now >= wk_end + win
            vals[wname] = (rate(rows, anchor_k, target_k, win) if measurable else None, measurable)
        return vals

    # 1차: 주차별 실측값 계산 (아직 충분한 시간이 안 지난 구간은 measurable=False)
    weeks_raw = []
    for i in range(weeks):
        wk_start = first_week_start + timedelta(weeks=i)
        wk_end = wk_start + timedelta(days=7)
        cohort = [r for r in signups if wk_start <= r['reg_date'] < wk_end]
        scohort = [r for r in samples if wk_start <= r['req_date'] < wk_end]
        weeks_raw.append({
            'week_start': wk_start, 'wk_end': wk_end,
            'signup_cnt': len(cohort), 'sample_cnt': len(scohort),
            's2s': build_metric(cohort, 'reg_date', 'first_sample', wk_end),
            's2o': build_metric(cohort, 'reg_date', 'first_order', wk_end),
            'sm2o': build_metric(scohort, 'req_date', 'first_order', wk_end),
        })

    # 2차: 아직 시간이 덜 지난 구간은 "과거 주차들의 (짧은창→긴창) 평균 비율"로 예상치 추정
    def add_projection(metric):
        n = len(WIN_NAMES)
        ratio_samples = {}
        for wr in weeks_raw:
            vals = wr[metric]
            for ai in range(n):
                av, ameas = vals[WIN_NAMES[ai]]
                if not ameas or not av:
                    continue
                for ti in range(ai + 1, n):
                    tv, tmeas = vals[WIN_NAMES[ti]]
                    if tmeas and tv is not None:
                        ratio_samples.setdefault((ai, ti), []).append(tv / av)
        for wr in weeks_raw:
            vals = wr[metric]
            k = max([i for i in range(n) if vals[WIN_NAMES[i]][1]], default=-1)
            out = {}
            for i in range(n):
                v, meas = vals[WIN_NAMES[i]]
                if meas:
                    out[WIN_NAMES[i]] = {'v': v, 'est': False}
                elif k >= 0:
                    rs = ratio_samples.get((k, i))
                    anchor_v = vals[WIN_NAMES[k]][0]
                    if rs and anchor_v is not None:
                        proj = round(min(100, anchor_v * (sum(rs) / len(rs))), 2)
                        out[WIN_NAMES[i]] = {'v': proj, 'est': True}
                    else:
                        out[WIN_NAMES[i]] = {'v': None, 'est': False}
                else:
                    out[WIN_NAMES[i]] = {'v': None, 'est': False}
            wr[metric] = out

    for m in ('s2s', 's2o', 'sm2o'):
        add_projection(m)

    weeks_out = []
    for wr in weeks_raw:
        weeks_out.append({
            'week_start': wr['week_start'].strftime('%Y-%m-%d'),
            'week_label': f"{wr['week_start'].strftime('%m/%d')}~{(wr['wk_end'] - timedelta(days=1)).strftime('%m/%d')}",
            'signup_cnt': wr['signup_cnt'], 'sample_cnt': wr['sample_cnt'],
            'signup_to_sample': wr['s2s'], 'signup_to_order': wr['s2o'], 'sample_to_order': wr['sm2o'],
        })
    return {'weeks': weeks_out, 'updated_at': now.strftime('%Y-%m-%d %H:%M:%S')}


# ══════════════════════════════════════════════════════════════════
#  신제품 추적 (등록일 기준 상품별 샘플수·원주문 전환율)  — /api/newproducts
# ══════════════════════════════════════════════════════════════════
CARDBRAND_LABELS = {
    'B': '바른손카드', 'C': '더카드', 'S': '비핸즈', 'X': '디어디어', 'W': 'W카드',
    'N': '네이처', 'I': '이니스', 'H': '비핸즈프리미엄', 'F': '플라워', 'D': '디자인카드',
    'P': '프리미어', 'M': '모바일', 'G': '글로벌', 'U': '유니세프', 'Y': '유니크', 'K': '비케이',
    'T': '프리미어더카드', 'A': '기타',
}
CARDDIV_LABELS = {'A01': '일반청첩장', 'A02': '봉투', 'A03': '감사장', 'A04': '스티커', 'A05': '식권/부속', 'B01': '포토북/앨범'}


def fetch_new_products(base_str, days_back=90, brand=None):
    base_dt = datetime.strptime(base_str, '%Y-%m-%d')
    start = (base_dt - timedelta(days=days_back)).strftime('%Y-%m-%d')
    end = (base_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor(as_dict=True)
    brand_filter = "AND c.CardBrand = %s" if brand else ""
    params = (start, end, start, end, start, end) + ((brand,) if brand else ())
    cur.execute(f"""
        SELECT c.Card_Seq, c.Card_Code, c.Card_Name, c.CardBrand, c.Card_Div,
               c.RegDate, c.Card_Price,
               ISNULL(sm.sample_cnt, 0) as sample_cnt,
               ISNULL(od.order_cnt, 0) as order_cnt,
               ISNULL(od.order_qty, 0) as order_qty,
               ISNULL(od.revenue, 0) as revenue
        FROM S2_Card c
        LEFT JOIN (
            SELECT CARD_SEQ, COUNT(*) as sample_cnt
            FROM CUSTOM_SAMPLE_ORDER_ITEM
            WHERE REG_DATE >= %s AND REG_DATE < %s
            GROUP BY CARD_SEQ
        ) sm ON sm.CARD_SEQ = c.Card_Seq
        LEFT JOIN (
            SELECT oi.card_seq, COUNT(DISTINCT o.order_seq) as order_cnt,
                   SUM(oi.item_count) as order_qty,
                   SUM(oi.item_sale_price * oi.item_count) as revenue
            FROM custom_order_item oi
            JOIN custom_order o ON o.order_seq = oi.order_seq
            WHERE o.settle_date >= %s AND o.settle_date < %s AND o.settle_cancel_date IS NULL
            GROUP BY oi.card_seq
        ) od ON od.card_seq = c.Card_Seq
        WHERE c.RegDate >= %s AND c.RegDate < %s {brand_filter}
        ORDER BY c.RegDate DESC, sample_cnt DESC
    """, params)
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        conv = round(r['order_cnt'] / r['sample_cnt'] * 100, 1) if r['sample_cnt'] else None
        out.append({
            'card_seq': r['Card_Seq'], 'code': r['Card_Code'], 'name': _dec(r['Card_Name']),
            'brand': r['CardBrand'], 'brand_label': CARDBRAND_LABELS.get(r['CardBrand'], r['CardBrand']),
            'div': r['Card_Div'], 'div_label': CARDDIV_LABELS.get(r['Card_Div'], r['Card_Div']),
            'reg_date': r['RegDate'].strftime('%Y-%m-%d') if r['RegDate'] else None,
            'price': r['Card_Price'],
            'sample_cnt': r['sample_cnt'], 'order_cnt': r['order_cnt'],
            'order_qty': r['order_qty'], 'revenue': r['revenue'], 'conversion': conv,
        })
    return {'products': out, 'start': start, 'end': base_dt.strftime('%Y-%m-%d'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


# ══════════════════════════════════════════════════════════════════
#  부가상품 (청첩장 외 품목, item_type != 'C')  — /api/addon
# ══════════════════════════════════════════════════════════════════
def fetch_addon(base_str, days_back=7):
    base_dt = datetime.strptime(base_str, '%Y-%m-%d')
    start = (base_dt - timedelta(days=days_back - 1)).strftime('%Y-%m-%d')
    end = (base_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor(as_dict=True)
    # SKU(card_seq) 단위까지 집계 — item_type 합계는 SKU 합을 파이썬에서 다시 더해서 만듦(주문 단위 중복집계 방지)
    cur.execute(f"""
        SELECT o.sales_Gubun as sg, oi.item_type, oi.card_seq,
            c.Card_Code as code, c.Card_ERPCode as erp_code, c.Card_Name as name, c.CardBrand as cbrand,
            SUM(oi.item_count) as qty,
            SUM(oi.item_sale_price * oi.item_count) as revenue
        FROM custom_order o JOIN custom_order_item oi ON o.order_seq = oi.order_seq
        LEFT JOIN S2_Card c ON c.Card_Seq = oi.card_seq
        WHERE o.settle_date >= %s AND o.settle_date < %s AND o.settle_cancel_date IS NULL
          AND oi.item_type <> 'C' AND o.sales_Gubun IN {ALL_GUBUN_SQL}
        GROUP BY o.sales_Gubun, oi.item_type, oi.card_seq, c.Card_Code, c.Card_ERPCode, c.Card_Name, c.CardBrand
    """, (start, end))
    rows = cur.fetchall()
    conn.close()

    by_type = {}
    for r in rows:
        bk = _brand_key(r['sg'])
        if not bk:
            continue
        t = r['item_type']
        te = by_type.setdefault(t, {'item_type': t, 'qty': 0, 'revenue': 0, 'by_brand': {}, 'skus': {}})
        qty, rev = r['qty'] or 0, r['revenue'] or 0
        te['qty'] += qty
        te['revenue'] += rev
        te['by_brand'][bk] = te['by_brand'].get(bk, 0) + rev
        sk = r['card_seq']
        se = te['skus'].setdefault(sk, {
            'card_seq': sk, 'code': r['code'] or '(코드없음)',
            'erp_code': r['erp_code'] or '-',
            'name': _dec(r['name']) if r['name'] else '(옵션/기타 항목 — 상품마스터 없음)',
            'brand_label': CARDBRAND_LABELS.get(r['cbrand'], r['cbrand'] or '-'),
            'qty': 0, 'revenue': 0,
        })
        se['qty'] += qty
        se['revenue'] += rev

    items = []
    for te in by_type.values():
        sku_list = sorted(te['skus'].values(), key=lambda x: -x['revenue'])
        items.append({
            'item_type': te['item_type'], 'qty': te['qty'], 'revenue': te['revenue'],
            'sku_cnt': len(sku_list), 'by_brand': te['by_brand'], 'skus': sku_list,
        })
    items.sort(key=lambda x: -x['revenue'])
    return {'items': items, 'start': start, 'end': base_dt.strftime('%Y-%m-%d'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


# ══════════════════════════════════════════════════════════════════
#  베스트 청첩장 랭킹 (주간/월간/연간)  — /api/best
# ══════════════════════════════════════════════════════════════════
def _period_range(base_dt, period):
    if period == 'month':
        s = base_dt.replace(day=1)
        e = s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1)
        label = s.strftime('%Y년 %m월')
    elif period == 'year':
        s = base_dt.replace(month=1, day=1)
        e = s.replace(year=s.year + 1)
        label = f"{s.year}년"
    else:  # week
        s = _week_start(base_dt)
        e = s + timedelta(days=7)
        label = f"{s.strftime('%Y-%m-%d')} ~ {(e - timedelta(days=1)).strftime('%Y-%m-%d')}"
    return s, e, label


def fetch_best_products(base_str, period='week', brand=None, top=30):
    base_dt = datetime.strptime(base_str, '%Y-%m-%d')
    s, e, label = _period_range(base_dt, period)
    start, end = s.strftime('%Y-%m-%d'), e.strftime('%Y-%m-%d')
    brand_filter = ''
    if brand and brand in BRANDS_MAP:
        gubuns = BRANDS_MAP[brand]
        brand_filter = "AND o.sales_Gubun IN (" + ",".join(f"'{g}'" for g in gubuns) + ")"
    conn = get_conn()
    cur = conn.cursor(as_dict=True)
    cur.execute(f"""
        SELECT oi.card_seq, c.Card_Code as code, c.Card_Name as name, c.CardBrand as cbrand,
               c.Card_Div as div, c.Card_Price as price,
            COUNT(DISTINCT o.order_seq) as order_cnt,
            SUM(oi.item_count) as qty,
            SUM(oi.item_sale_price * oi.item_count) as revenue
        FROM custom_order o JOIN custom_order_item oi ON o.order_seq = oi.order_seq
        LEFT JOIN S2_Card c ON c.Card_Seq = oi.card_seq
        WHERE o.settle_date >= %s AND o.settle_date < %s AND o.settle_cancel_date IS NULL
          AND oi.item_type = 'C' {brand_filter}
        GROUP BY oi.card_seq, c.Card_Code, c.Card_Name, c.CardBrand, c.Card_Div, c.Card_Price
        ORDER BY revenue DESC
    """, (start, end))
    rows = cur.fetchall()
    conn.close()
    products = []
    for i, r in enumerate(rows[:top]):
        products.append({
            'rank': i + 1, 'card_seq': r['card_seq'], 'code': r['code'] or '-',
            'name': _dec(r['name']) if r['name'] else '(상품마스터 없음)',
            'brand_label': CARDBRAND_LABELS.get(r['cbrand'], r['cbrand'] or '-'),
            'div_label': CARDDIV_LABELS.get(r['div'], r['div'] or '-'),
            'price': r['price'], 'order_cnt': r['order_cnt'], 'qty': r['qty'], 'revenue': r['revenue'],
        })
    return {'products': products, 'period': period, 'label': label, 'start': start,
            'end': (e - timedelta(days=1)).strftime('%Y-%m-%d'), 'total_count': len(rows),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>바른손 데일리 리포트</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',-apple-system,sans-serif;background:#f5f5f5;color:#333;font-size:13px}
.hdr{background:linear-gradient(135deg,#0d47a1,#1565c0);color:#fff;padding:14px 24px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.hdr h1{font-size:17px}
.hdr-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:6px}
.dn{display:flex;gap:3px;align-items:center}
.dn button,.dn input{padding:4px 10px;border:1px solid rgba(255,255,255,.3);border-radius:4px;background:rgba(255,255,255,.12);color:#fff;cursor:pointer;font-size:12px;font-family:inherit}
.dn input[type=date]{color-scheme:dark}
.dn button:hover{background:rgba(255,255,255,.25)}
.btn-y{background:rgba(255,255,255,.22)!important;font-weight:700}
.hi{font-size:11px;opacity:.65;margin-left:auto}
.ct{max-width:1200px;margin:0 auto;padding:14px}
.sec{margin-bottom:16px;background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);overflow:hidden}
.sh{background:#f8f9fa;padding:9px 14px;font-weight:700;font-size:13px;border-bottom:1px solid #e8e8e8;display:flex;align-items:center;gap:6px}
.sh .bg{font-size:10px;background:#e3f2fd;color:#1565c0;padding:2px 7px;border-radius:10px;font-weight:500}
table{width:100%;border-collapse:collapse}
th{background:#fafafa;padding:6px 8px;text-align:center;font-size:10.5px;color:#888;border-bottom:1px solid #eee;white-space:nowrap}
td{padding:6px 8px;text-align:center;border-bottom:1px solid #f5f5f5;white-space:nowrap;font-size:12px}
tr:hover td{background:#f8f9ff}
.bl{text-align:left;font-weight:600;color:#1a237e;background:#f8f9fa;min-width:85px;font-size:12px}
.sl{text-align:left;padding-left:20px;color:#555;font-size:11.5px}
.n{font-variant-numeric:tabular-nums;font-weight:500}
.hl td{background:#fffde7!important;font-weight:600}
.chg{font-size:10px;font-weight:600;padding:1px 4px;border-radius:3px;display:inline-block}
.up{color:#c62828;background:#ffebee}
.dn2{color:#1565c0;background:#e3f2fd}
.fl{color:#9e9e9e;background:#f5f5f5}
.sr td{background:#f0f0f0;padding:2px;border:none}
.tot td{background:#e8eaf6!important;font-weight:700}
.ft{text-align:center;font-size:10px;color:#aaa;padding:10px}
.ld{text-align:center;padding:40px;color:#888;font-size:14px}
.cp-btn{margin-left:auto;padding:3px 10px;border:1px solid #ccc;border-radius:4px;background:#fff;color:#555;cursor:pointer;font-size:11px;font-family:inherit;transition:all .2s}
.cp-btn:hover{background:#e3f2fd;color:#1565c0;border-color:#90caf9}
.cp-btn.ok{background:#c8e6c9;color:#2e7d32;border-color:#a5d6a7}
.chart-wrap{padding:14px;border-top:1px solid #eee;background:#fafafa}
.chart-wrap canvas{max-height:260px}
/* ── 인사이트/경고 ── */
.alert{border-radius:8px;padding:11px 14px;margin-bottom:8px;font-size:13px;font-weight:600;display:flex;gap:10px;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.alert.red{background:#ffebee;color:#b71c1c;border-left:5px solid #c62828}
.alert.yellow{background:#fff8e1;color:#e65100;border-left:5px solid #f9a825}
.alert.ok{background:#e8f5e9;color:#1b5e20;border-left:5px solid #2e7d32}
.alert .em{font-size:16px}
.alert .sub{font-weight:400;font-size:11.5px;opacity:.85;margin-left:6px}
.icard{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:16px;overflow:hidden}
.icard .sh{background:#f8f9fa;padding:9px 14px;font-weight:700;font-size:13px;border-bottom:1px solid #e8e8e8}
.icard .bd{padding:12px 14px}
.diag li{margin:5px 0;line-height:1.5;font-size:12.5px;list-style:none}
.diag .act li{color:#0d47a1}
.brtabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.brtab{padding:5px 12px;border:1px solid #ddd;border-radius:14px;background:#fff;color:#555;cursor:pointer;font-size:11.5px;font-family:inherit;font-weight:600}
.brtab:hover{background:#f0f3ff}
.brtab.on{background:#1565c0;color:#fff;border-color:#1565c0}
.kpi{display:flex;gap:14px;flex-wrap:wrap}
.kpi .box{flex:1;min-width:150px;background:#f8f9ff;border:1px solid #e8eaf6;border-radius:6px;padding:10px 12px}
.kpi .box .lb{font-size:11px;color:#888}
.kpi .box .vv{font-size:18px;font-weight:700;color:#1a237e;font-variant-numeric:tabular-nums;margin-top:3px}
.kpi .box .sm{font-size:11px;margin-top:2px}
.note{font-size:11px;color:#999;margin-top:8px}
.sug{display:flex;gap:8px;align-items:flex-start;padding:8px 0;border-bottom:1px solid #f2f2f2;font-size:12.5px;line-height:1.5}
.sug:last-child{border-bottom:none}
.sug .lead{flex:0 0 auto;font-size:11px;font-weight:700;color:#555;white-space:nowrap;min-width:74px}
.sug .tag{flex:0 0 auto;font-size:10px;font-weight:700;color:#fff;padding:2px 7px;border-radius:10px;white-space:nowrap}
.sug .txt{flex:1}
.pagetabs{display:flex;gap:4px;margin-top:8px}
.ptab{padding:6px 16px;border:none;border-radius:6px 6px 0 0;background:rgba(255,255,255,.1);color:rgba(255,255,255,.75);cursor:pointer;font-size:12.5px;font-family:inherit;font-weight:600}
.ptab:hover{background:rgba(255,255,255,.2);color:#fff}
.ptab.on{background:#f5f5f5;color:#0d47a1}
.page{display:none}
.page.on{display:block}
.funtbl th,.funtbl td{font-size:11px}
.funtbl .grp-s{background:#e8f0fe}
.funtbl .grp-o{background:#fce4ec}
.funtbl .grp-so{background:#e8f5e9}
.mini-ctl{display:flex;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid #eee;font-size:12px;color:#666}
.mini-ctl select,.mini-ctl input{padding:3px 8px;border:1px solid #ddd;border-radius:4px;font-size:12px;font-family:inherit}
.prodtbl td.name{text-align:left;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.conv-hi{color:#c62828;font-weight:700}
.conv-lo{color:#999}
</style>
</head>
<body>
<div class="hdr">
  <h1>바른손 통합 대시보드</h1>
  <div class="hdr-row">
    <div class="dn">
      <button onclick="mv(-1)">&larr;</button>
      <input type="date" id="dp" onchange="go()">
      <button onclick="mv(1)">&rarr;</button>
      <button class="btn-y" onclick="goY()">어제</button>
      <button onclick="mv(-7)">-1주</button>
      <button onclick="mv(-30)">-1월</button>
    </div>
    <div class="hi" id="hi"></div>
  </div>
  <div class="pagetabs" id="pagetabs">
    <button class="ptab on" data-p="daily" onclick="switchPage('daily')">📊 일별 리포트</button>
    <button class="ptab" data-p="funnel" onclick="switchPage('funnel')">🔻 가입→샘플→구매 퍼널</button>
    <button class="ptab" data-p="newprod" onclick="switchPage('newprod')">🆕 신제품 추적</button>
    <button class="ptab" data-p="addon" onclick="switchPage('addon')">🎁 부가상품</button>
    <button class="ptab" data-p="best" onclick="switchPage('best')">🏆 베스트청첩장</button>
  </div>
</div>

<div class="page on" id="page-daily">
<div class="ct" id="alertbox"></div>
<div class="ct" id="ins"><div class="ld">인사이트 로딩 중...</div></div>
<div class="ct" id="main"><div class="ld">로딩 중...</div></div>
<div class="ft" id="ft"></div>
</div>

<div class="page" id="page-funnel">
<div class="ct">
  <div class="sec">
    <div class="sh">가입→샘플→구매 코호트 퍼널 <span class="bg">실측(가입일/샘플일 기준 추적)</span>
      <button class="cp-btn" style="margin-left:auto" onclick="loadFunnel(true)">새로고침</button>
    </div>
    <div class="mini-ctl">
      조회 범위:
      <select id="funWeeks" onchange="loadFunnel(true)">
        <option value="8">최근 8주</option><option value="12">최근 12주</option>
        <option value="26" selected>최근 26주(반기)</option><option value="52">최근 52주(1년)</option>
      </select>
      <span style="margin-left:auto;color:#999">※ 상단 날짜선택으로 더 과거로 이동 가능 · 회색 <b>~물결</b> 값은 아직 시간이 덜 지나 과거 주차의 (짧은창→긴창) 평균 전환비율로 추정한 예상치</span>
    </div>
    <div class="ct" style="padding:0 14px 10px">
      <div class="brtabs" id="funBrandTabs">
        <div class="brtab on" data-b="" onclick="setFunBrand('')">전체</div>
        <div class="brtab" data-b="barunson" onclick="setFunBrand('barunson')">바른손카드</div>
        <div class="brtab" data-b="barunmall" onclick="setFunBrand('barunmall')">바른손몰</div>
        <div class="brtab" data-b="deardeer" onclick="setFunBrand('deardeer')">디얼디어</div>
        <div class="brtab" data-b="premier" onclick="setFunBrand('premier')">프리미어페이퍼</div>
      </div>
    </div>
    <div id="funnelBody"><div class="ld">불러오는 중...</div></div>
  </div>
</div>
</div>

<div class="page" id="page-newprod">
<div class="ct">
  <div class="sec">
    <div class="sh">신제품 추적 (상품 등록일 기준) <span class="bg">샘플수 → 원주문 전환율</span>
      <button class="cp-btn" style="margin-left:auto" onclick="loadNewProd(true)">새로고침</button>
    </div>
    <div class="mini-ctl">
      기간:
      <select id="npDays" onchange="loadNewProd(true)">
        <option value="30">최근 30일</option><option value="60">최근 60일</option>
        <option value="90" selected>최근 90일</option><option value="180">최근 180일</option>
      </select>
      브랜드:
      <select id="npBrand" onchange="loadNewProd(true)">
        <option value="">전체</option><option value="B">바른손카드</option><option value="C">더카드</option>
        <option value="S">비핸즈</option><option value="X">디어디어</option><option value="W">W카드</option>
      </select>
      정렬:
      <select id="npSort" onchange="renderNewProd(lastNewProdData)">
        <option value="sample">샘플수 많은순</option><option value="revenue" selected>매출 많은순</option>
        <option value="reg_date">등록일 최신순</option><option value="conversion">전환율 높은순</option>
      </select>
    </div>
    <div id="newprodBody"><div class="ld">불러오는 중...</div></div>
  </div>
</div>
</div>

<div class="page" id="page-addon">
<div class="ct">
  <div class="sec">
    <div class="sh">부가상품 매출 (청첩장 외 품목) <span class="bg">item_type 기준, 청첩장 코드 'C' 제외</span>
      <button class="cp-btn" style="margin-left:auto" onclick="loadAddon(true)">새로고침</button>
    </div>
    <div class="mini-ctl">
      기간:
      <select id="adDays" onchange="loadAddon(true)">
        <option value="7" selected>최근 7일</option><option value="30">최근 30일</option>
        <option value="90">최근 90일</option>
      </select>
      <span style="margin-left:auto;color:#999">※ item_type 코드별 정확한 한글 품목명은 확인 중 — 코드 그대로 표시</span>
    </div>
    <div id="addonBody"><div class="ld">불러오는 중...</div></div>
  </div>
</div>
</div>

<div class="page" id="page-best">
<div class="ct">
  <div class="sec">
    <div class="sh">베스트 청첩장 랭킹 <span class="bg" id="bestLabel">-</span>
      <button class="cp-btn" style="margin-left:auto" onclick="loadBest(true)">새로고침</button>
    </div>
    <div class="mini-ctl">
      단위:
      <select id="bestPeriod" onchange="loadBest(true)">
        <option value="week" selected>주간</option><option value="month">월간</option><option value="year">연간</option>
      </select>
      TOP:
      <select id="bestTop" onchange="loadBest(true)">
        <option value="20">20</option><option value="30" selected>30</option><option value="50">50</option>
      </select>
      <span style="margin-left:auto;color:#999">※ 기준일은 상단 날짜선택 사용 — 주간=해당 주(월~일), 월간=해당 월, 연간=해당 연도. 매출(카드+환불제외) 기준 정렬</span>
    </div>
    <div class="ct" style="padding:0 14px 10px">
      <div class="brtabs" id="bestBrandTabs">
        <div class="brtab on" data-b="" onclick="setBestBrand('')">전체</div>
        <div class="brtab" data-b="barunson" onclick="setBestBrand('barunson')">바른손카드</div>
        <div class="brtab" data-b="barunmall" onclick="setBestBrand('barunmall')">바른손몰</div>
        <div class="brtab" data-b="deardeer" onclick="setBestBrand('deardeer')">디얼디어</div>
        <div class="brtab" data-b="premier" onclick="setBestBrand('premier')">프리미어페이퍼</div>
      </div>
    </div>
    <div id="bestBody"><div class="ld">불러오는 중...</div></div>
  </div>
</div>
</div>

<script>
const BR=[['barunson','바른손카드'],['barunmall','바른손몰'],['deardeer','디얼디어'],['premier','프리미어페이퍼']];
let D,sel;
function ts(){return new Date().toISOString().slice(0,10)}
function ys(){const d=new Date();d.setDate(d.getDate()-1);return d.toISOString().slice(0,10)}
sel=ys();
function init(){const p=document.getElementById('dp');p.value=sel;p.max=ts()}
function onDateChanged(){
  loaded.funnel = false; loaded.newprod = false; loaded.addon = false; loaded.best = false;
  const cur = document.querySelector('.ptab.on');
  const p = cur ? cur.dataset.p : 'daily';
  if (p === 'daily') fd();
  else if (p === 'funnel') loadFunnel();
  else if (p === 'newprod') loadNewProd();
  else if (p === 'addon') loadAddon();
  else if (p === 'best') loadBest();
}
function go(){sel=document.getElementById('dp').value;onDateChanged()}
function mv(n){const d=new Date(sel);d.setDate(d.getDate()+n);if(d>new Date())return;sel=d.toISOString().slice(0,10);document.getElementById('dp').value=sel;onDateChanged()}
function goY(){sel=ys();document.getElementById('dp').value=sel;onDateChanged()}
function f(n){return n==null?'-':n.toLocaleString('ko-KR')}
function fw(n){return n==null?'-':n.toLocaleString('ko-KR')+'원'}
function fp(n){return n==null?'-':n+'%'}
function pc(a,b){
  if(!b&&!a)return'<span class="chg fl">-</span>';
  if(!b)return'<span class="chg up">NEW</span>';
  const p=((a-b)/b*100).toFixed(1);
  if(p>0)return`<span class="chg up">▲${p}%</span>`;
  if(p<0)return`<span class="chg dn2">▼${Math.abs(p)}%</span>`;
  return'<span class="chg fl">0%</span>';
}
function thdr(p){
  return`<th>기준일<br>${p.base.date}(${p.base.wd})</th>
  <th>1주전<br>${p.wow.date}(${p.wow.wd})</th><th>WoW</th>
  <th>1개월전<br>${p.mom.date}(${p.mom.wd})</th><th>MoM</th>
  <th>1년전<br>${p.yoy.date}(${p.yoy.wd})</th><th>YoY</th>`;
}
function vals(p,sec,bk,key){
  return[p.base[sec][bk][key],p.wow[sec][bk][key],p.mom[sec][bk][key],p.yoy[sec][bk][key]];
}
function drow(label,v,fmt,cls){
  const[b,w,m,y]=v;
  return`<td class="sl">${label}</td>
  <td class="n">${fmt(b)}</td><td class="n">${fmt(w)}</td><td>${pc(b,w)}</td>
  <td class="n">${fmt(m)}</td><td>${pc(b,m)}</td>
  <td class="n">${fmt(y)}</td><td>${pc(b,y)}</td>`;
}
function sumVals(p,sec,key){
  return['base','wow','mom','yoy'].map(pk=>BR.reduce((s,[bk])=>s+(p[pk][sec][bk][key]||0),0));
}
function svVals(p,key){
  return['base','wow','mom','yoy'].map(pk=>p[pk].special_voucher[key]);
}

function cpBtn(id,label){
  return `<button class="cp-btn" onclick="copySection('${id}')" id="cpb-${id}">${label||'복사'}</button>`;
}
function copySection(id){
  const lines=[];
  const sec=document.getElementById('sec-'+id);
  if(!sec)return;
  const rows=sec.querySelectorAll('tbody tr');
  rows.forEach(tr=>{
    if(tr.classList.contains('sr'))return;
    // find the base-date column (first .n cell)
    const cells=tr.querySelectorAll('td.n');
    if(cells.length>=1){
      const val=cells[0].textContent.trim();
      lines.push(val);
    }
  });
  const txt=lines.join('\n');
  navigator.clipboard.writeText(txt).then(()=>{
    const btn=document.getElementById('cpb-'+id);
    btn.textContent='복사됨!';btn.classList.add('ok');
    setTimeout(()=>{btn.textContent='복사';btn.classList.remove('ok');},1500);
  });
}
const charts={};
function makeChart(id,labels,datasets,isWon){
  setTimeout(()=>{
    const el=document.getElementById(id);
    if(!el)return;
    if(charts[id]){charts[id].destroy();}
    charts[id]=new Chart(el,{
      type:'bar',
      data:{labels,datasets},
      options:{
        responsive:true,maintainAspectRatio:false,
        plugins:{
          legend:{position:'top',labels:{font:{size:11},usePointStyle:true,pointStyle:'rectRounded'}},
          tooltip:{callbacks:{label:function(ctx){
            let v=ctx.raw;
            return ctx.dataset.label+': '+(isWon?v.toLocaleString()+'원':v.toLocaleString());
          }}}
        },
        scales:{
          y:{beginAtZero:true,ticks:{font:{size:10},callback:v=>isWon?(v>=10000?(v/10000)+'만':v.toLocaleString()):v.toLocaleString()}},
          x:{ticks:{font:{size:11}}}
        }
      }
    });
  },50);
}
function chartData(p,metric,bk,ky){
  return ['base','wow','mom','yoy'].map(pk=>{
    const pd=p[pk];if(!pd)return null;
    const md=pd[metric];if(!md)return null;
    const bd=md[bk];if(!bd)return null;
    return bd[ky]??null;
  });
}
function addChart(id,p,metric,ky,isWon){
  const labels=[];const base=[];const wow=[];const mom=[];const yoy=[];
  BR.forEach(([bk,bn])=>{
    const d=chartData(p,metric,bk,ky);
    labels.push(bn);base.push(d[0]);wow.push(d[1]);mom.push(d[2]);yoy.push(d[3]);
  });
  // add total
  labels.push('합계');
  const totD=['base','wow','mom','yoy'].map(pk=>{
    const pd=p[pk];if(!pd)return 0;
    const md=pd[metric];if(!md)return 0;
    let s=0;BR.forEach(([bk])=>{const bd=md[bk];if(bd)s+=(bd[ky]||0);});return s;
  });
  base.push(totD[0]);wow.push(totD[1]);mom.push(totD[2]);yoy.push(totD[3]);
  const ds=[
    {label:'기준일',data:base,backgroundColor:'#1565c0',borderRadius:3},
    {label:'1주전(WoW)',data:wow,backgroundColor:'#90caf9',borderRadius:3},
    {label:'1개월전(MoM)',data:mom,backgroundColor:'#ff8a65',borderRadius:3},
    {label:'1년전(YoY)',data:yoy,backgroundColor:'#a5d6a7',borderRadius:3}
  ];
  return `<div class="chart-wrap"><canvas id="${id}" height="240"></canvas></div>`;
}
function renderCharts(p){
  // sample
  addChartReal('ch-sample',p,'sample','total',false);
  addChartReal('ch-sc',p,'settle_cnt','total',false);
  addChartReal('ch-sr',p,'settle_rev','revenue',true);
  addChartReal('ch-sq',p,'settle_qty','qty',false);
  addChartReal('ch-dc',p,'delivery','total_cnt',false);
  addChartReal('ch-dr',p,'delivery','total_rev',true);
  addChartReal('ch-dq',p,'delivery','total_qty',false);
}
function addChartReal(id,p,metric,ky,isWon){
  const labels=[];const base=[];const wow=[];const mom=[];const yoy=[];
  BR.forEach(([bk,bn])=>{
    const d=chartData(p,metric,bk,ky);
    labels.push(bn);base.push(d[0]);wow.push(d[1]);mom.push(d[2]);yoy.push(d[3]);
  });
  labels.push('합계');
  const totD=['base','wow','mom','yoy'].map(pk=>{
    const pd=p[pk];if(!pd)return 0;
    const md=pd[metric];if(!md)return 0;
    let s=0;BR.forEach(([bk])=>{const bd=md[bk];if(bd)s+=(bd[ky]||0);});return s;
  });
  base.push(totD[0]);wow.push(totD[1]);mom.push(totD[2]);yoy.push(totD[3]);
  const ds=[
    {label:'기준일',data:base,backgroundColor:'#1565c0',borderRadius:3},
    {label:'1주전(WoW)',data:wow,backgroundColor:'#90caf9',borderRadius:3},
    {label:'1개월전(MoM)',data:mom,backgroundColor:'#ff8a65',borderRadius:3},
    {label:'1년전(YoY)',data:yoy,backgroundColor:'#a5d6a7',borderRadius:3}
  ];
  makeChart(id,labels,ds,isWon);
}
function render(){
  if(!D)return;
  const p=D.periods;
  let h='';

  // ─── 1. 샘플주문 수 (주문일 기준) ───
  let t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    const rows=[['회원','member',f],['비회원','guest',f],['원클릭','oneclick',f],
                ['전체','total',f]];
    rows.forEach(([lb,ky,fm],i)=>{
      const v=vals(p,'sample',bk,ky);
      const isTot=ky==='total';
      t+=`<tr${isTot?' class="hl"':''}>`;
      if(i===0)t+=`<td class="bl" rowspan="${rows.length}">${bn}</td>`;
      t+=drow(lb,v,fm)+'</tr>';
    });
    t+='<tr class="sr"><td colspan="9"></td></tr>';
  });
  // 합계
  const stot=sumVals(p,'sample','total');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',stot,f)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">샘플주문 수 <span class="bg">주문일 기준</span>${cpBtn('sample')}</div><table id="sec-sample">${t}</table><div class="chart-wrap"><canvas id="ch-sample" height="240"></canvas></div></div>`;

  // ─── 2. 청첩장 주문 수 (결제일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    const v=vals(p,'settle_cnt',bk,'total');
    t+=`<tr class="hl"><td class="bl">${bn}</td>${drow('전체',v,f)}</tr>`;
  });
  const sctot=sumVals(p,'settle_cnt','total');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',sctot,f)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 주문 수 <span class="bg">결제일 기준</span>${cpBtn('sc')}</div><table id="sec-sc">${t}</table><div class="chart-wrap"><canvas id="ch-sc" height="240"></canvas></div></div>`;

  // ─── 3. 청첩장 주문 매출액 (결제일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    const isB=bk==='barunson';
    const rc=isB?2:1;
    const v=vals(p,'settle_rev',bk,'revenue');
    t+=`<tr class="hl"><td class="bl" rowspan="${rc}">${bn}</td>${drow('전체',v,fw)}</tr>`;
    if(isB){
      const vg=vals(p,'settle_rev',bk,'revenue_no_gift');
      t+=`<tr>${drow('전체(-답례품)',vg,fw)}</tr>`;
    }
  });
  const srtot=sumVals(p,'settle_rev','revenue');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',srtot,fw)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 주문 매출액 <span class="bg">결제일 기준</span>${cpBtn('sr')}</div><table id="sec-sr">${t}</table><div class="chart-wrap"><canvas id="ch-sr" height="240"></canvas></div></div>`;

  // ─── 4. 청첩장 주문 수량 (결제일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    const v=vals(p,'settle_qty',bk,'qty');
    t+=`<tr class="hl"><td class="bl">${bn}</td>${drow('전체',v,f)}</tr>`;
  });
  const sqtot=sumVals(p,'settle_qty','qty');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',sqtot,f)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 주문 수량 <span class="bg">결제일 기준 / 청첩장(C)만</span>${cpBtn('sq')}</div><table id="sec-sq">${t}</table><div class="chart-wrap"><canvas id="ch-sq" height="240"></canvas></div></div>`;

  // ─── 청첩장 동반/단독 주문 비율 (결제일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  const bRows=[['동반(답례품/굿즈 포함)','bundle',f],['단독(청첩장만)','solo',f],
               ['동반비율','bundle_ratio',fp],['단독비율','solo_ratio',fp]];
  BR.forEach(([bk,bn])=>{
    bRows.forEach(([lb,ky,fm],i)=>{
      const v=vals(p,'bundle',bk,ky);
      t+=`<tr${ky==='bundle_ratio'?' class="hl"':''}>`;
      if(i===0)t+=`<td class="bl" rowspan="${bRows.length}">${bn}</td>`;
      t+=drow(lb,v,fm)+'</tr>';
    });
    t+='<tr class="sr"><td colspan="9"></td></tr>';
  });
  bRows.forEach(([lb,ky,fm],i)=>{
    const v=vals(p,'bundle','all',ky);
    t+=`<tr class="tot">`;
    if(i===0)t+=`<td class="bl" rowspan="${bRows.length}">전체</td>`;
    t+=drow(lb,v,fm)+'</tr>';
  });
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 동반/단독 주문 비율 <span class="bg">결제일 기준 · 동반=청첩장+답례품/굿즈 함께 결제 / 단독=청첩장(+기본구성품)만</span>${cpBtn('br')}</div><table id="sec-br">${t}</table></div>`;

  // ─── 특가이용권 (바른라운지 MD247, 결제일 기준) ───
  const svCnt=svVals(p,'cnt'), svRev=svVals(p,'rev');
  t=`<thead><tr><th>지표</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  t+=`<tr class="hl"><td class="bl">결제건수</td>${drow('전체',svCnt,f)}</tr>`;
  t+=`<tr class="hl"><td class="bl">매출액</td>${drow('전체',svRev,fw)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">바른라운지 이용권 구매현황 <span class="bg">구매일 기준 / 바른손카드</span>${cpBtn('sv')}</div><table id="sec-sv">${t}</table></div>`;

  // ─── 5. 청첩장 주문 수 (배송일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    [['회원','member_cnt'],['비회원','guest_cnt'],['전체','total_cnt']].forEach(([lb,ky],i)=>{
      const v=vals(p,'delivery',bk,ky);
      t+=`<tr${ky==='total_cnt'?' class="hl"':''}>`;
      if(i===0)t+=`<td class="bl" rowspan="3">${bn}</td>`;
      t+=drow(lb,v,f)+'</tr>';
    });
    t+='<tr class="sr"><td colspan="9"></td></tr>';
  });
  const dctot=sumVals(p,'delivery','total_cnt');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',dctot,f)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 주문 수 <span class="bg">배송일 기준 / 주말 배송없음</span>${cpBtn('dc')}</div><table id="sec-dc">${t}</table><div class="chart-wrap"><canvas id="ch-dc" height="240"></canvas></div></div>`;

  // ─── 6. 청첩장 주문 매출액 (배송일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    [['회원','member_rev'],['비회원','guest_rev'],['전체','total_rev']].forEach(([lb,ky],i)=>{
      const v=vals(p,'delivery',bk,ky);
      t+=`<tr${ky==='total_rev'?' class="hl"':''}>`;
      if(i===0)t+=`<td class="bl" rowspan="3">${bn}</td>`;
      t+=drow(lb,v,fw)+'</tr>';
    });
    t+='<tr class="sr"><td colspan="9"></td></tr>';
  });
  const drtot=sumVals(p,'delivery','total_rev');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',drtot,fw)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 주문 매출액 <span class="bg">배송일 기준</span>${cpBtn('dr')}</div><table id="sec-dr">${t}</table><div class="chart-wrap"><canvas id="ch-dr" height="240"></canvas></div></div>`;

  // ─── 7. 청첩장 주문 수량 (배송일 기준) ───
  t=`<thead><tr><th>브랜드</th><th>구분</th>${thdr(p)}</tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    [['회원','member_qty'],['비회원','guest_qty'],['전체','total_qty']].forEach(([lb,ky],i)=>{
      const v=vals(p,'delivery',bk,ky);
      t+=`<tr${ky==='total_qty'?' class="hl"':''}>`;
      if(i===0)t+=`<td class="bl" rowspan="3">${bn}</td>`;
      t+=drow(lb,v,f)+'</tr>';
    });
    t+='<tr class="sr"><td colspan="9"></td></tr>';
  });
  const dqtot=sumVals(p,'delivery','total_qty');
  t+=`<tr class="tot"><td class="bl">합계</td>${drow('전체',dqtot,f)}</tr>`;
  t+='</tbody>';
  h+=`<div class="sec"><div class="sh">청첩장 주문 수량 <span class="bg">배송일 기준 / 청첩장(C)만</span>${cpBtn('dq')}</div><table id="sec-dq">${t}</table><div class="chart-wrap"><canvas id="ch-dq" height="240"></canvas></div></div>`;

  document.getElementById('main').innerHTML=h;
  renderCharts(p);
}

// ─── 인사이트 (경고 + 상세정보 + 진단/예측) ───
const BRMAP={SB:'바른손카드'};
let insBrand='all';
let lastInsights=null;
function num(n){return n==null?'-':n.toLocaleString('ko-KR')}
function won(n){return n==null?'-':n.toLocaleString('ko-KR')+'원'}
function eok(n){if(n==null)return'-';return (n/100000000).toFixed(2)+'억'}
function setInsBrand(k){insBrand=k;if(lastInsights)renderInsights(lastInsights);}
function loadInsights(){
  const box=document.getElementById('alertbox');
  const ins=document.getElementById('ins');
  ins.innerHTML='<div class="ld">인사이트 로딩 중...</div>';
  fetch('/api/insights?date='+sel).then(r=>r.json()).then(I=>{
    if(I.error){ins.innerHTML='<div class="ld" style="color:#c62828">인사이트 오류: '+I.error+'</div>';return;}
    lastInsights=I;
    renderAlerts(I);
    renderInsights(I);
  }).catch(e=>{ins.innerHTML='<div class="ld" style="color:#c62828">인사이트 연결 오류: '+e.message+'</div>'});
}
function renderAlerts(I){
  const box=document.getElementById('alertbox');
  let h='';
  if(!I.alerts||!I.alerts.length){
    h=`<div class="alert ok"><span class="em">✅</span>급감 하락신호 없음 <span class="sub">(비회원샘플·결제주문수·결제매출 / 당일 vs 직전7일 · 최근7일 vs 직전28일)</span></div>`;
  }else{
    I.alerts.forEach(a=>{
      const em=a.level==='red'?'🔴':'🟡';
      const tag=a.kind==='daily'?'당일급감':'추세';
      h+=`<div class="alert ${a.level}"><span class="em">${em}</span><b>[${tag}]</b> ${a.brand} · ${a.metric} ${a.drop_pct}% 하락
        <span class="sub">${a.window||''} · ${a.recent} vs ${a.base}</span></div>`;
    });
  }
  box.innerHTML=h;
}
function renderInsights(I){
  const ins=document.getElementById('ins');
  let h='';
  const D2=I.diagnosis||{core:[],actions:[]};
  // 핵심진단 + 권장액션
  h+=`<div class="icard"><div class="sh">🧭 핵심진단 · 권장액션 <span style="font-weight:400;font-size:11px;color:#888">최근 30일 · ${I.window||''}</span></div><div class="bd">`;
  h+=`<div style="font-weight:700;font-size:12px;color:#555;margin-bottom:4px">핵심진단</div><ul class="diag">`;
  D2.core.forEach(c=>h+=`<li>· ${c}</li>`);
  h+=`</ul><div style="font-weight:700;font-size:12px;color:#555;margin:10px 0 4px">권장액션</div><ul class="diag act">`;
  D2.actions.forEach(c=>h+=`<li>▸ ${c}</li>`);
  h+=`</ul></div></div>`;
  // 🔮 선제 제안 (1~2주 전)
  const PR=I.proactive||[];
  const tagClr={ '시즌수요':'#00695c','신제품':'#6a1b9a','기획전':'#c62828','객단가':'#e65100',
    '기념일':'#ad1457','공휴일':'#546e7a','명절':'#4527a0','연말':'#1565c0','가정의달':'#2e7d32','연말연시':'#1565c0' };
  h+=`<div class="icard"><div class="sh">🔮 선제 제안 <span style="font-weight:400;font-size:11px;color:#888">계절·공휴일·베스트셀러 기반 · 1~2주 선행</span></div><div class="bd">`;
  if(!PR.length){ h+=`<div class="note">제안 데이터 없음</div>`; }
  PR.forEach(p=>{
    const clr=tagClr[p.tag]||'#555';
    h+=`<div class="sug"><span class="lead">${p.lead}</span><span class="tag" style="background:${clr}">${p.tag}</span><span class="txt">${p.text}</span></div>`;
  });
  h+=`</div></div>`;
  // 브랜드 선택 탭 (예식월수요/예측매출/인기상품/주문장수분포에 적용)
  const brTabs=[['all','전체'],...BR];
  h+=`<div class="brtabs">`+brTabs.map(([k,n])=>
    `<button class="brtab${k===insBrand?' on':''}" onclick="setInsBrand('${k}')">${n}</button>`).join('')+`</div>`;
  const bn=(Object.fromEntries(brTabs))[insBrand]||'전체';

  // 예식월 수요 (선제 근거)
  const WD=(I.wedding_demand||{})[insBrand]||[];
  if(WD.length){
    h+=`<div class="icard"><div class="sh">📅 예식월 수요 분포 <span style="font-weight:400;font-size:11px;color:#888">${bn} · 현재 결제 주문이 향하는 예식월 / 리드타임 역산</span></div>`;
    h+=`<table><thead><tr><th>예식월</th>${WD.slice(0,8).map(w=>`<th>${w.ym.slice(2)}</th>`).join('')}</tr></thead><tbody>`;
    h+=`<tr><td class="bl">주문수</td>${WD.slice(0,8).map(w=>`<td class="n">${num(w.ords)}</td>`).join('')}</tr>`;
    h+=`<tr><td class="bl">비중</td>${WD.slice(0,8).map(w=>`<td class="n">${w.pct}%</td>`).join('')}</tr>`;
    h+=`</tbody></table><div class="bd note">※ 상위 예식월 = 지금 유입 중인 수요. 이 시즌 상품을 지금 전면 배치하면 검색·샘플 단계를 선점.</div></div>`;
  } else {
    h+=`<div class="icard"><div class="sh">📅 예식월 수요 분포 <span style="font-weight:400;font-size:11px;color:#888">${bn}</span></div><div class="bd note">해당 브랜드는 최근 30일 예식월별 5건 미만이라 표시할 데이터가 없습니다.</div></div>`;
  }
  // 예측매출
  const F=(I.forecast||{})[insBrand]||{};
  h+=`<div class="icard"><div class="sh">📈 예측매출 <span style="font-weight:400;font-size:11px;color:#888">${bn} · ${F.month||''} 런레이트</span></div><div class="bd"><div class="kpi">`;
  h+=`<div class="box"><div class="lb">당월 누적(MTD)</div><div class="vv">${eok(F.mtd)}</div><div class="sm" style="color:#888">${F.days_elapsed}/${F.days_in_month}일 경과</div></div>`;
  h+=`<div class="box"><div class="lb">당월 예상매출</div><div class="vv">${eok(F.projected)}</div><div class="sm" style="color:#888">일평균 × ${F.days_in_month}일</div></div>`;
  const yc=F.yoy_pct;const yclr=yc==null?'#888':(yc>=0?'#c62828':'#1565c0');
  h+=`<div class="box"><div class="lb">작년 동월 실적</div><div class="vv">${eok(F.last_year_month)}</div><div class="sm" style="color:${yclr};font-weight:700">${yc==null?'-':(yc>=0?'▲':'▼')+Math.abs(yc)+'% (YoY 예상)'}</div></div>`;
  h+=`</div></div></div>`;
  // 매출구조 (브랜드별 30일)
  const RS=I.revenue_structure||{};
  const rtot=Object.values(RS).reduce((s,d)=>s+(d.rev||0),0)||1;
  h+=`<div class="icard"><div class="sh">💰 매출구조 <span style="font-weight:400;font-size:11px;color:#888">최근 30일 결제 기준</span></div>`;
  h+=`<table><thead><tr><th>브랜드</th><th>매출</th><th>비중</th><th>주문수</th><th>객단가</th><th>회원매출</th><th>비회원매출</th></tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    const d=RS[bk];if(!d)return;
    const aov=d.cnt?Math.round(d.rev/d.cnt):0;
    h+=`<tr><td class="bl">${bn}</td><td class="n">${won(d.rev)}</td><td class="n">${(d.rev/rtot*100).toFixed(1)}%</td>
      <td class="n">${num(d.cnt)}</td><td class="n">${won(aov)}</td><td class="n">${won(d.m_rev)}</td><td class="n">${won(d.g_rev)}</td></tr>`;
  });
  h+=`<tr class="tot"><td class="bl">합계</td><td class="n">${won(rtot)}</td><td class="n">100%</td><td colspan="4"></td></tr>`;
  h+=`</tbody></table></div>`;
  // 예식 전 리드타임 분포
  const LT=I.leadtime||{};const bands=['0-29','30-44','45-59','60-89','90+'];
  h+=`<div class="icard"><div class="sh">💍 예식 전 리드타임 분포 <span style="font-weight:400;font-size:11px;color:#888">결제일→예식일(일) / 최근 30일 결제</span></div>`;
  h+=`<table><thead><tr><th>브랜드</th>${bands.map(b=>`<th>${b}일</th>`).join('')}<th>합계</th></tr></thead><tbody>`;
  BR.forEach(([bk,bn])=>{
    const d=LT[bk];if(!d)return;
    const tot=bands.reduce((s,b)=>s+(d[b]||0),0);
    h+=`<tr><td class="bl">${bn}</td>${bands.map(b=>`<td class="n">${num(d[b]||0)}</td>`).join('')}<td class="n" style="font-weight:700">${num(tot)}</td></tr>`;
  });
  h+=`</tbody></table><div class="bd note">※ 대부분 예식 60~90일+ 전에 청첩장 결제. 리드타임이 짧아지면 급한 수요/재고회전 신호.</div></div>`;
  // 인기 상품 TOP + 가격대
  const TP=(I.top_products||{})[insBrand]||[];
  h+=`<div class="icard"><div class="sh">🏆 인기 상품 TOP${TP.length} · 가격대 <span style="font-weight:400;font-size:11px;color:#888">${bn} · 청첩장(C) / 최근 30일 결제 / 수량순</span></div>`;
  h+=`<table><thead><tr><th>순위</th><th style="text-align:left">상품명</th><th>주문수</th><th>수량</th><th>평균단가</th></tr></thead><tbody>`;
  TP.forEach((p,i)=>{
    h+=`<tr><td class="n">${i+1}</td><td style="text-align:left;padding-left:14px">${p.name}</td><td class="n">${num(p.ords)}</td><td class="n">${num(p.qty)}</td><td class="n">${won(p.avgp)}</td></tr>`;
  });
  h+=`</tbody></table></div>`;
  // 주문 장수 분포
  const SD=(I.sheet_dist||{})[insBrand]||{};const sbands=['<100','100-149','150-199','200-299','300+'];
  const stot=sbands.reduce((s,b)=>s+(SD[b]||0),0)||1;
  h+=`<div class="icard"><div class="sh">📄 주문 장수 분포 <span style="font-weight:400;font-size:11px;color:#888">${bn} · 주문당 청첩장 장수 / 최근 30일 결제</span></div>`;
  h+=`<table><thead><tr><th>장수 구간</th>${sbands.map(b=>`<th>${b}</th>`).join('')}</tr></thead><tbody>`;
  h+=`<tr><td class="bl">주문수</td>${sbands.map(b=>`<td class="n">${num(SD[b]||0)}</td>`).join('')}</tr>`;
  h+=`<tr><td class="bl">비중</td>${sbands.map(b=>`<td class="n">${((SD[b]||0)/stot*100).toFixed(1)}%</td>`).join('')}</tr>`;
  h+=`</tbody></table></div>`;
  // 장바구니
  const C=I.cart||{};
  h+=`<div class="icard"><div class="sh">🛒 장바구니 현황</div><div class="bd"><div class="kpi">
    <div class="box"><div class="lb">활성 장바구니(만료 전)</div><div class="vv">${num(C.active)}</div></div></div>
    <div class="note">${C.note||''}</div></div></div>`;
  ins.innerHTML=h;
}

function fd(){
  loadInsights();
  document.getElementById('main').innerHTML='<div class="ld">데이터를 불러오는 중...</div>';
  fetch('/api/data?date='+sel).then(r=>r.json()).then(d=>{
    if(d.error){
      document.getElementById('main').innerHTML='<div class="ld" style="color:#c62828">DB 오류: '+d.error+'</div>';
      return;
    }
    if(!d.periods||!d.periods.base){
      document.getElementById('main').innerHTML='<div class="ld" style="color:#c62828">데이터 없음: 응답 형식 오류</div>';
      return;
    }
    D=d;
    const b=d.periods.base;
    document.getElementById('hi').textContent=`${b.date}(${b.wd}) | WoW:${d.periods.wow.date} MoM:${d.periods.mom.date} YoY:${d.periods.yoy.date}`;
    document.getElementById('ft').textContent='갱신: '+d.updated_at+' | 자동 새로고침: 5분마다';
    render();
  }).catch(e=>{document.getElementById('main').innerHTML='<div class="ld" style="color:#c62828">연결 오류: '+e.message+'</div>'});
}
// ─── 자동 새로고침 (5분마다) ───
let autoRefreshInterval = 5 * 60 * 1000; // 5분
let lastAutoDate = sel;

function autoRefresh() {
  const newYs = ys();
  // 날짜가 바뀌었으면 (자정 지남) 자동으로 어제 날짜로 전환
  if (newYs !== lastAutoDate) {
    sel = newYs;
    document.getElementById('dp').value = sel;
    document.getElementById('dp').max = ts();
    lastAutoDate = newYs;
  }
  fd();
}

// 5분마다 자동 새로고침
setInterval(autoRefresh, autoRefreshInterval);

// ─── 매일 8시 자동 갱신 ───
function scheduleEightAM() {
  const now = new Date();
  let next8 = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 8, 0, 0);
  if (now >= next8) {
    next8.setDate(next8.getDate() + 1);
  }
  const ms = next8 - now;
  setTimeout(() => {
    sel = ys();
    document.getElementById('dp').value = sel;
    document.getElementById('dp').max = ts();
    lastAutoDate = sel;
    fd();
    // 다음날 8시 재예약
    scheduleEightAM();
  }, ms);
  const hh = Math.floor(ms/3600000);
  const mm = Math.floor((ms%3600000)/60000);
  console.log(`다음 8시 자동 갱신: ${next8.toLocaleString()} (${hh}시간 ${mm}분 후)`);
}

scheduleEightAM();

// ─── 마지막 갱신 시각 표시 ───
function updateRefreshTime() {
  const ft = document.getElementById('ft');
  if (ft && D) {
    ft.textContent = '갱신: ' + D.updated_at + ' | 자동 새로고침: 5분마다 | 다음 8시 갱신 예정';
  }
}

// ─── 페이지(탭) 전환 ───
const loaded = {funnel: false, newprod: false, addon: false, best: false};
function switchPage(p) {
  document.querySelectorAll('.ptab').forEach(b => b.classList.toggle('on', b.dataset.p === p));
  document.querySelectorAll('.page').forEach(el => el.classList.toggle('on', el.id === 'page-' + p));
  if (p === 'funnel' && !loaded.funnel) loadFunnel();
  if (p === 'newprod' && !loaded.newprod) loadNewProd();
  if (p === 'addon' && !loaded.addon) loadAddon();
  if (p === 'best' && !loaded.best) loadBest();
}

function fmtRate(v) { return v == null ? '<span style="color:#ccc">-</span>' : v + '%'; }
function fmtCell(c) {
  if (!c || c.v == null) return '<span style="color:#ccc">-</span>';
  return c.est ? '<span style="color:#9e9e9e;font-style:italic">~' + c.v + '%</span>' : (c.v + '%');
}

// ─── 공통: fetch + 1회 자동 재시도 + 실패 시 재시도 버튼(호출자 함수명 지정) ───
function fetchWithRetry(url, elId, onData, retryCall) {
  const el = document.getElementById(elId);
  function attempt(isRetry) {
    fetch(url).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(d => { if (d.error) throw new Error(d.error); onData(d); })
      .catch(e => {
        if (!isRetry) { setTimeout(() => attempt(true), 800); return; }
        el.innerHTML = '<div class="ld">일시적 조회 오류가 발생했습니다 (DB 커넥션 순단으로 추정).<br>' +
          '<button class="cp-btn" style="margin-top:8px" onclick="' + retryCall + '">다시 시도</button></div>';
      });
  }
  attempt(false);
}

// ─── 가입→샘플→구매 퍼널 ───
let funBrand = '';
function setFunBrand(b) {
  funBrand = b;
  document.querySelectorAll('#funBrandTabs .brtab').forEach(el => el.classList.toggle('on', el.dataset.b === b));
  loadFunnel(true);
}
function loadFunnel(force) {
  const wk = document.getElementById('funWeeks').value;
  fetchWithRetry('/api/funnel?date=' + sel + '&weeks=' + wk + '&brand=' + funBrand, 'funnelBody',
    d => { loaded.funnel = true; renderFunnel(d); }, 'loadFunnel(true)');
}
function renderFunnel(d) {
  const cols = ['24h', '48h', '1w', '2w', '3w', '4w'];
  const colLbl = { '24h': '24시간', '48h': '48시간', '1w': '1주', '2w': '2주', '3w': '3주', '4w': '4주' };
  let h = '<div style="overflow-x:auto"><table class="funtbl">';
  h += '<tr><th rowspan="2">주차</th><th rowspan="2">가입수</th><th rowspan="2">샘플수</th>';
  h += '<th colspan="6" class="grp-s">가입→샘플 전환율</th><th colspan="6" class="grp-o">가입→구매 전환율</th><th colspan="6" class="grp-so">샘플→구매 전환율</th></tr>';
  h += '<tr>' + cols.map(c => '<th class="grp-s">' + colLbl[c] + '</th>').join('') +
       cols.map(c => '<th class="grp-o">' + colLbl[c] + '</th>').join('') +
       cols.map(c => '<th class="grp-so">' + colLbl[c] + '</th>').join('') + '</tr>';
  d.weeks.forEach(w => {
    h += '<tr><td class="bl">' + w.week_label + '</td><td class="n">' + f(w.signup_cnt) + '</td><td class="n">' + f(w.sample_cnt) + '</td>';
    h += cols.map(c => '<td class="n">' + fmtCell(w.signup_to_sample[c]) + '</td>').join('');
    h += cols.map(c => '<td class="n">' + fmtCell(w.signup_to_order[c]) + '</td>').join('');
    h += cols.map(c => '<td class="n">' + fmtCell(w.sample_to_order[c]) + '</td>').join('');
    h += '</tr>';
  });
  h += '</table></div>';
  h += '<div class="note" style="padding:8px 14px">가입=S2_UserInfo.reg_date(실제 회원가입일) · 샘플=CUSTOM_SAMPLE_ORDER 유효건(STATUS_SEQ≥1) · 구매=custom_order 결제완료건(취소 제외). 갱신: ' + d.updated_at + '</div>';
  document.getElementById('funnelBody').innerHTML = h;
}

// ─── 신제품 추적 ───
let lastNewProdData = null;
const NP_SORTERS = {
  sample: (a, b) => b.sample_cnt - a.sample_cnt,
  revenue: (a, b) => b.revenue - a.revenue,
  reg_date: (a, b) => (a.reg_date < b.reg_date ? 1 : a.reg_date > b.reg_date ? -1 : 0),
  conversion: (a, b) => (b.conversion == null ? -1 : b.conversion) - (a.conversion == null ? -1 : a.conversion),
};
function loadNewProd(force) {
  const days = document.getElementById('npDays').value;
  const brand = document.getElementById('npBrand').value;
  fetchWithRetry('/api/newproducts?date=' + sel + '&days=' + days + '&brand=' + brand, 'newprodBody',
    d => { loaded.newprod = true; lastNewProdData = d; renderNewProd(d); }, 'loadNewProd(true)');
}
function renderNewProd(d) {
  if (!d || !d.products.length) { document.getElementById('newprodBody').innerHTML = '<div class="ld">해당 기간 등록된 신제품이 없습니다</div>'; return; }
  const sortKey = document.getElementById('npSort').value;
  const products = d.products.slice().sort(NP_SORTERS[sortKey]);
  let h = '<div style="overflow-x:auto"><table class="prodtbl">';
  h += '<tr><th>등록일</th><th>브랜드</th><th>카테고리</th><th>코드</th><th>상품명</th><th>단가</th><th>샘플수</th><th>주문수</th><th>주문수량</th><th>매출</th><th>전환율</th></tr>';
  products.forEach(p => {
    const convCls = p.conversion == null ? '' : (p.conversion >= 5 ? 'conv-hi' : 'conv-lo');
    h += '<tr><td>' + p.reg_date + '</td><td>' + p.brand_label + '</td><td>' + p.div_label + '</td><td>' + p.code + '</td>' +
         '<td class="name" title="' + p.name + '">' + p.name + '</td><td class="n">' + fw(p.price) + '</td>' +
         '<td class="n">' + f(p.sample_cnt) + '</td><td class="n">' + f(p.order_cnt) + '</td><td class="n">' + f(p.order_qty) + '</td>' +
         '<td class="n">' + fw(p.revenue) + '</td><td class="n ' + convCls + '">' + fmtRate(p.conversion) + '</td></tr>';
  });
  h += '</table></div>';
  h += '<div class="note" style="padding:8px 14px">전환율 = 원주문수÷샘플수(해당 상품, 고객 매칭 아닌 상품단위 근사치). 등록 상품 ' + products.length + '개. 갱신: ' + d.updated_at + '</div>';
  document.getElementById('newprodBody').innerHTML = h;
}

// ─── 부가상품 ───
function loadAddon(force) {
  const days = document.getElementById('adDays').value;
  fetchWithRetry('/api/addon?date=' + sel + '&days=' + days, 'addonBody',
    d => { loaded.addon = true; renderAddon(d); }, 'loadAddon(true)');
}
let addonData = null;
function renderAddon(d) {
  addonData = d;
  if (!d.items.length) { document.getElementById('addonBody').innerHTML = '<div class="ld">데이터 없음</div>'; return; }
  const totalRev = d.items.reduce((a, x) => a + x.revenue, 0);
  let h = '<div style="overflow-x:auto"><table class="prodtbl">';
  h += '<tr><th></th><th>item_type</th><th>상품종류수</th><th>수량</th><th>매출</th><th>매출비중</th></tr>';
  d.items.forEach((it, i) => {
    const pct = totalRev ? (it.revenue / totalRev * 100).toFixed(1) : 0;
    h += '<tr style="cursor:pointer" onclick="toggleAddonType(' + i + ')"><td>▶</td><td class="bl">' + it.item_type + '</td><td class="n">' + f(it.sku_cnt) + '</td><td class="n">' + f(it.qty) + '</td>' +
         '<td class="n">' + fw(it.revenue) + '</td><td class="n">' + pct + '%</td></tr>';
    h += '<tr id="addonSkuRow' + i + '" hidden><td colspan="6" style="padding:0;background:#fafbff">' +
         '<div id="addonSkuBody' + i + '" style="padding:8px 20px"></div></td></tr>';
  });
  h += '<tr class="tot"><td></td><td class="bl">합계</td><td class="n">' + f(d.items.reduce((a, x) => a + x.sku_cnt, 0)) + '</td>' +
       '<td class="n">' + f(d.items.reduce((a, x) => a + x.qty, 0)) + '</td><td class="n">' + fw(totalRev) + '</td><td></td></tr>';
  h += '</table></div>';
  h += '<div class="note" style="padding:8px 14px">' + d.start + ' ~ ' + d.end + ' 결제완료 기준(취소 제외) · 상품종류수=해당 item_type에 팔린 서로 다른 SKU 개수 · 행 클릭 시 SKU 상세 펼침. 갱신: ' + d.updated_at + '</div>';
  document.getElementById('addonBody').innerHTML = h;
}
function toggleAddonType(i) {
  const row = document.getElementById('addonSkuRow' + i);
  const body = document.getElementById('addonSkuBody' + i);
  const willShow = row.hidden;
  row.hidden = !willShow;
  if (willShow && !body.dataset.filled) {
    const it = addonData.items[i];
    let h = '<table class="prodtbl" style="background:#fff"><tr><th>코드</th><th>ERP코드</th><th>상품명</th><th>브랜드</th><th>수량</th><th>매출</th></tr>';
    it.skus.forEach(s => {
      h += '<tr><td>' + s.code + '</td><td>' + s.erp_code + '</td><td class="name" title="' + s.name + '">' + s.name + '</td>' +
           '<td>' + s.brand_label + '</td><td class="n">' + f(s.qty) + '</td><td class="n">' + fw(s.revenue) + '</td></tr>';
    });
    h += '</table>';
    body.innerHTML = h;
    body.dataset.filled = '1';
  }
}

// ─── 베스트 청첩장 랭킹 ───
let bestBrand = '';
function setBestBrand(b) {
  bestBrand = b;
  document.querySelectorAll('#bestBrandTabs .brtab').forEach(el => el.classList.toggle('on', el.dataset.b === b));
  loadBest(true);
}
function loadBest(force) {
  const period = document.getElementById('bestPeriod').value;
  const top = document.getElementById('bestTop').value;
  fetchWithRetry('/api/best?date=' + sel + '&period=' + period + '&top=' + top + '&brand=' + bestBrand, 'bestBody',
    d => { loaded.best = true; renderBest(d); }, 'loadBest(true)');
}
function renderBest(d) {
  document.getElementById('bestLabel').textContent = d.label + ' (' + {week:'주간',month:'월간',year:'연간'}[d.period] + ')';
  if (!d.products.length) { document.getElementById('bestBody').innerHTML = '<div class="ld">해당 기간 판매 데이터가 없습니다</div>'; return; }
  let h = '<div style="overflow-x:auto"><table class="prodtbl">';
  h += '<tr><th>순위</th><th>코드</th><th>상품명</th><th>브랜드</th><th>카테고리</th><th>단가</th><th>주문건수</th><th>수량</th><th>매출</th></tr>';
  d.products.forEach(p => {
    h += '<tr><td class="n" style="font-weight:700">' + p.rank + '</td><td>' + p.code + '</td>' +
         '<td class="name" title="' + p.name + '">' + p.name + '</td><td>' + p.brand_label + '</td><td>' + p.div_label + '</td>' +
         '<td class="n">' + fw(p.price) + '</td><td class="n">' + f(p.order_cnt) + '</td><td class="n">' + f(p.qty) + '</td>' +
         '<td class="n">' + fw(p.revenue) + '</td></tr>';
  });
  h += '</table></div>';
  h += '<div class="note" style="padding:8px 14px">' + d.start + ' ~ ' + d.end + ' 결제완료 기준(취소 제외), 청첩장(item_type=C)만 집계, 전체 판매 상품 ' + d.total_count + '개 중 상위 ' + d.products.length + '개. 갱신: ' + d.updated_at + '</div>';
  document.getElementById('bestBody').innerHTML = h;
}

init();fd();
</script>
</body>
</html>"""


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>바른손 대시보드 로그인</title>
<script src="https://accounts.google.com/gsi/client" async defer></script>
<style>
body{font-family:'Segoe UI',-apple-system,sans-serif;background:#f5f5f5;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{background:#fff;padding:40px 48px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center}
h1{font-size:18px;margin-bottom:8px;color:#1a237e}
p{font-size:13px;color:#888;margin-bottom:24px}
</style></head>
<body>
<div class="box">
  <h1>바른손 통합 대시보드</h1>
  <p>@__ALLOWED_DOMAIN__ 계정으로 로그인하세요</p>
  <div id="g_id_onload"
    data-client_id="__GOOGLE_CLIENT_ID__"
    data-login_uri="/auth/google"
    data-hd="__ALLOWED_DOMAIN__">
  </div>
  <div class="g_id_signin" data-type="standard" data-theme="outline" data-size="large"></div>
</div>
</body></html>"""


def _sign(payload: str) -> str:
    return base64.urlsafe_b64encode(
        hmac.new(SESSION_SECRET.encode(), payload.encode(), 'sha256').digest()
    ).decode()


def make_session_cookie(email):
    payload = f"{email}|{int(time.time()) + SESSION_MAX_AGE}"
    sig = _sign(payload)
    value = base64.urlsafe_b64encode(payload.encode()).decode() + '.' + sig
    return value


def verify_session_cookie(value):
    try:
        b64_payload, sig = value.split('.', 1)
        payload = base64.urlsafe_b64decode(b64_payload.encode()).decode()
        if not hmac.compare_digest(_sign(payload), sig):
            return None
        email, _, exp = payload.rpartition('|')
        if int(exp) < time.time():
            return None
        return email
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    def _session_email(self):
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return None
        c = SimpleCookie()
        c.load(cookie_header)
        if SESSION_COOKIE_NAME not in c:
            return None
        return verify_session_cookie(c[SESSION_COOKIE_NAME].value)

    def _check_auth(self):
        """인증 비활성 시 항상 통과. Google 모드면 세션 쿠키, Basic 모드면 Authorization 헤더 검사."""
        if not AUTH_ENABLED:
            return True
        if GOOGLE_AUTH_ENABLED:
            email = self._session_email()
            return bool(email and email.lower().endswith('@' + ALLOWED_EMAIL_DOMAIN.lower()))
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode('utf-8')
            user, _, pw = decoded.partition(':')
        except Exception:
            return False
        return hmac.compare_digest(user, AUTH_USER) and hmac.compare_digest(pw, AUTH_PASSWORD)

    def _send_auth_required(self, is_api=False):
        if GOOGLE_AUTH_ENABLED and not is_api:
            html = LOGIN_HTML.replace('__GOOGLE_CLIENT_ID__', GOOGLE_CLIENT_ID).replace('__ALLOWED_DOMAIN__', ALLOWED_EMAIL_DOMAIN)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return
        self.send_response(401)
        if BASIC_AUTH_ENABLED:
            self.send_header('WWW-Authenticate', 'Basic realm="Barunson Dashboard"')
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write('401 Unauthorized'.encode('utf-8'))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/auth/google' and GOOGLE_AUTH_ENABLED:
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length).decode('utf-8')
                form = parse_qs(body)
                credential = form.get('credential', [None])[0]
                from google.oauth2 import id_token as google_id_token
                from google.auth.transport import requests as google_requests
                info = google_id_token.verify_oauth2_token(
                    credential, google_requests.Request(), GOOGLE_CLIENT_ID
                )
                email = info.get('email', '')
                email_verified = info.get('email_verified', False)
                hd = info.get('hd', '')
                ok = (email_verified and hd.lower() == ALLOWED_EMAIL_DOMAIN.lower()
                      and email.lower().endswith('@' + ALLOWED_EMAIL_DOMAIN.lower()))
                if not ok:
                    self.send_response(403)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(f'허용되지 않은 계정입니다 (@{ALLOWED_EMAIL_DOMAIN} 계정만 가능)'.encode('utf-8'))
                    return
                cookie_value = make_session_cookie(email)
                self.send_response(302)
                self.send_header('Location', '/')
                self.send_header(
                    'Set-Cookie',
                    f'{SESSION_COOKIE_NAME}={cookie_value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_MAX_AGE}'
                )
                self.end_headers()
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(f'로그인 처리 오류: {e}'.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'ok')
            return
        is_api = parsed.path.startswith('/api/')
        if not self._check_auth():
            self._send_auth_required(is_api=is_api)
            return
        if parsed.path in ('/api/data', '/api/insights', '/api/funnel', '/api/newproducts', '/api/addon', '/api/best'):
            try:
                qs = parse_qs(parsed.query)
                bd = qs.get('date', [None])[0]
                if not bd:
                    bd = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                if parsed.path == '/api/insights':
                    data = fetch_insights(bd)
                elif parsed.path == '/api/funnel':
                    weeks = int(qs.get('weeks', ['8'])[0])
                    fbrand = qs.get('brand', [None])[0] or None
                    data = fetch_funnel(bd, weeks=weeks, brand=fbrand)
                elif parsed.path == '/api/newproducts':
                    days = int(qs.get('days', ['90'])[0])
                    brand = qs.get('brand', [None])[0] or None
                    data = fetch_new_products(bd, days_back=days, brand=brand)
                elif parsed.path == '/api/addon':
                    days = int(qs.get('days', ['7'])[0])
                    data = fetch_addon(bd, days_back=days)
                elif parsed.path == '/api/best':
                    period = qs.get('period', ['week'])[0]
                    bbrand = qs.get('brand', [None])[0] or None
                    top = int(qs.get('top', ['30'])[0])
                    data = fetch_best_products(bd, period=period, brand=bbrand, top=top)
                else:
                    data = fetch_all(bd)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f"바른손 데일리 리포트: http://localhost:{PORT}")
    print(f"기본: 어제. Ctrl+C 종료.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        srv.server_close()
