#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""바른손몰 비회원 샘플/결제 주문 - 4/8 버그 전후 비교"""
import os
import pymssql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

conn = pymssql.connect(
    server=os.getenv("DB_SERVER"),
    port=int(os.getenv("DB_PORT", "1433")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database="bar_shop1",
)

# 바른손몰 = sales_Gubun B, H
def agg(label, sql, params):
    cur = conn.cursor(as_dict=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    m = sum(r['cnt'] for r in rows if r['ut'] == 'member')
    g = sum(r['cnt'] for r in rows if r['ut'] == 'guest')
    tot = m + g
    gr = round(g / tot * 100, 1) if tot else 0
    print(f"  {label}: 전체 {tot:>5}  | 회원 {m:>5}  비회원 {g:>5}  (비회원비율 {gr:>5}%)")
    return tot, m, g, gr

SAMPLE_SQL = """
    SELECT CASE WHEN MEMBER_ID IS NOT NULL AND MEMBER_ID <> '' THEN 'member' ELSE 'guest' END as ut,
           COUNT(*) as cnt
    FROM CUSTOM_SAMPLE_ORDER WITH (NOLOCK)
    WHERE REQUEST_DATE >= %s AND REQUEST_DATE < %s AND STATUS_SEQ >= 1
      AND SALES_GUBUN IN ('B','H')
    GROUP BY CASE WHEN MEMBER_ID IS NOT NULL AND MEMBER_ID <> '' THEN 'member' ELSE 'guest' END
"""

SETTLE_SQL = """
    SELECT CASE WHEN member_id IS NOT NULL AND member_id <> '' THEN 'member' ELSE 'guest' END as ut,
           COUNT(DISTINCT order_seq) as cnt
    FROM custom_order WITH (NOLOCK)
    WHERE settle_date >= %s AND settle_date < %s AND sales_Gubun IN ('B','H')
    GROUP BY CASE WHEN member_id IS NOT NULL AND member_id <> '' THEN 'member' ELSE 'guest' END
"""

periods = [
    ("이전 (4/1~4/7)", '2026-04-01', '2026-04-08'),
    ("이후 (4/8~4/14)", '2026-04-08', '2026-04-15'),
    ("이후 (4/8~4/30)", '2026-04-08', '2026-05-01'),
    ("참고 3월 (3/1~3/31)", '2026-03-01', '2026-04-01'),
]

print("=" * 78)
print("[바른손몰 샘플주문 수] (CUSTOM_SAMPLE_ORDER, REQUEST_DATE 기준)")
print("=" * 78)
for lb, s, e in periods:
    agg(lb, SAMPLE_SQL, (s, e))

print()
print("=" * 78)
print("[바른손몰 결제기준 주문 수] (custom_order, settle_date 기준)")
print("=" * 78)
for lb, s, e in periods:
    agg(lb, SETTLE_SQL, (s, e))

# 일별 상세 (3/25 ~ 4/20) - 샘플 비회원 추이
print()
print("=" * 78)
print("[일별] 바른손몰 샘플주문 (REQUEST_DATE)  -  비회원 급감 확인")
print("=" * 78)
cur = conn.cursor(as_dict=True)
cur.execute("""
    SELECT CONVERT(varchar(10), REQUEST_DATE, 23) as d,
           SUM(CASE WHEN MEMBER_ID IS NOT NULL AND MEMBER_ID <> '' THEN 1 ELSE 0 END) as m,
           SUM(CASE WHEN MEMBER_ID IS NULL OR MEMBER_ID = '' THEN 1 ELSE 0 END) as g,
           COUNT(*) as tot
    FROM CUSTOM_SAMPLE_ORDER WITH (NOLOCK)
    WHERE REQUEST_DATE >= '2026-03-25' AND REQUEST_DATE < '2026-04-21'
      AND STATUS_SEQ >= 1 AND SALES_GUBUN IN ('B','H')
    GROUP BY CONVERT(varchar(10), REQUEST_DATE, 23)
    ORDER BY d
""")
print(f"  {'날짜':<12} {'전체':>6} {'회원':>6} {'비회원':>6} {'비회원%':>8}")
for r in cur.fetchall():
    gr = round(r['g'] / r['tot'] * 100, 1) if r['tot'] else 0
    print(f"  {r['d']:<12} {r['tot']:>6} {r['m']:>6} {r['g']:>6} {gr:>7}%")

conn.close()
