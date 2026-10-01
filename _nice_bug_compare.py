#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""바른손몰 비회원 - 4/8 버그 후 기간을 전년/전월/전주 동기간과 비교"""
import os, sys
import pymssql
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = pymssql.connect(
    server=os.getenv("DB_SERVER"), port=int(os.getenv("DB_PORT", "1433")),
    user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"), database="bar_shop1",
)

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

def agg(label, sql, s, e):
    cur = conn.cursor(as_dict=True)
    cur.execute(sql, (s, e))
    rows = cur.fetchall()
    m = sum(r['cnt'] for r in rows if r['ut'] == 'member')
    g = sum(r['cnt'] for r in rows if r['ut'] == 'guest')
    tot = m + g
    gr = round(g / tot * 100, 1) if tot else 0
    print(f"  {label:<26} 전체 {tot:>5} | 회원 {m:>5}  비회원 {g:>5}  (비회원비율 {gr:>5}%)")

# 버그 후 7일 윈도우와 동기간 비교
WINDOWS_7 = [
    ("기준 4/8~4/14 (버그후)", '2026-04-08', '2026-04-15'),
    ("이전주 4/1~4/7",         '2026-04-01', '2026-04-08'),
    ("이전달 3/8~3/14",        '2026-03-08', '2026-03-15'),
    ("전년도 2025/4/8~4/14",   '2025-04-08', '2025-04-15'),
]
print("="*80)
print("■ 7일 윈도우 비교  (버그후 4/8~4/14 vs 전주/전월/전년 동기간)")
print("="*80)
print("[샘플주문 수 / REQUEST_DATE]")
for lb, s, e in WINDOWS_7: agg(lb, SAMPLE_SQL, s, e)
print("\n[결제기준 주문 수 / settle_date]")
for lb, s, e in WINDOWS_7: agg(lb, SETTLE_SQL, s, e)

# 버그 후 4/8~4/30 윈도우와 동기간 비교
WINDOWS_L = [
    ("기준 4/8~4/30 (버그후)", '2026-04-08', '2026-05-01'),
    ("이전달 3/8~3/30",        '2026-03-08', '2026-03-31'),
    ("전년도 2025/4/8~4/30",   '2025-04-08', '2025-05-01'),
]
print("\n" + "="*80)
print("■ 장기 윈도우 비교  (버그후 4/8~4/30 vs 전월/전년 동기간)")
print("="*80)
print("[샘플주문 수 / REQUEST_DATE]")
for lb, s, e in WINDOWS_L: agg(lb, SAMPLE_SQL, s, e)
print("\n[결제기준 주문 수 / settle_date]")
for lb, s, e in WINDOWS_L: agg(lb, SETTLE_SQL, s, e)

conn.close()
