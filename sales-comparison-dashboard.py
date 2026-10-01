#!/usr/bin/env python3
"""바른손카드/바른손몰 매출 비교 대시보드 (YOY/MOM/WOW)"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import pymssql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PORT = 10020

BRAND_MAP = {
    'SB': '바른손몰',
    'B': '바른손카드',
}

ORDER_TYPE_MAP = {
    '1': 'sample',
    '6': 'original',
    '7': 'oneclick',
}


def get_conn():
    return pymssql.connect(
        server=os.getenv("DB_SERVER"),
        port=int(os.getenv("DB_PORT", "1433")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="bar_shop1",
    )


def get_barunson_conn():
    return pymssql.connect(
        server=os.getenv("DB_SERVER"),
        port=int(os.getenv("DB_PORT", "1433")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="barunson",
    )


def fetch_day_metrics(conn, target_date):
    """하루치 bar_shop1 주문 메트릭 조회"""
    cursor = conn.cursor(as_dict=True)
    d = target_date.strftime('%Y-%m-%d')
    d_next = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT
            o.sales_Gubun,
            o.order_type,
            CASE WHEN o.member_id IS NOT NULL AND o.member_id <> '' THEN 'member' ELSE 'guest' END as user_type,
            COUNT(DISTINCT o.order_seq) as order_count,
            ISNULL(CAST(SUM(oi.item_sale_price * oi.item_count) AS INT), 0) as revenue
        FROM custom_order o
        LEFT JOIN custom_order_item oi ON o.order_seq = oi.order_seq
        WHERE o.order_date >= %s AND o.order_date < %s
          AND o.status_seq >= 1
          AND o.sales_Gubun IN ('SB', 'B')
        GROUP BY o.sales_Gubun, o.order_type,
            CASE WHEN o.member_id IS NOT NULL AND o.member_id <> '' THEN 'member' ELSE 'guest' END
    """, (d, d_next))

    rows = cursor.fetchall()
    return rows


def fetch_mc_metrics(conn, target_date):
    """하루치 MC 시리즈 (디지털) 메트릭 조회"""
    cursor = conn.cursor(as_dict=True)
    d_str = target_date.strftime('%Y%m%d')

    cursor.execute("""
        SELECT *
        FROM TB_Sales_Statistic_Day
        WHERE Date = %s
    """, (d_str,))

    row = cursor.fetchone()
    return row


def aggregate_metrics(raw_rows, mc_row):
    """raw 데이터를 브랜드별로 집계"""
    result = {}

    for brand_code, brand_name in BRAND_MAP.items():
        brand_data = {
            'brand': brand_name,
            'brand_code': brand_code,
            'sample_member': 0,
            'sample_guest': 0,
            'sample_total': 0,
            'original_orders': 0,
            'original_revenue': 0,
            'oneclick_orders': 0,
            'oneclick_revenue': 0,
            'total_orders': 0,
            'total_revenue': 0,
            'member_orders': 0,
            'guest_orders': 0,
        }

        for row in raw_rows:
            if row['sales_Gubun'] != brand_code:
                continue
            otype = ORDER_TYPE_MAP.get(str(row['order_type']).strip(), 'other')
            cnt = row['order_count']
            rev = row['revenue']

            if otype == 'sample':
                if row['user_type'] == 'member':
                    brand_data['sample_member'] += cnt
                else:
                    brand_data['sample_guest'] += cnt
                brand_data['sample_total'] += cnt
            elif otype == 'original':
                brand_data['original_orders'] += cnt
                brand_data['original_revenue'] += rev
            elif otype == 'oneclick':
                brand_data['oneclick_orders'] += cnt
                brand_data['oneclick_revenue'] += rev

            brand_data['total_orders'] += cnt
            brand_data['total_revenue'] += rev
            if row['user_type'] == 'member':
                brand_data['member_orders'] += cnt
            else:
                brand_data['guest_orders'] += cnt

        # AOV 계산
        real_orders = brand_data['original_orders'] + brand_data['oneclick_orders']
        real_revenue = brand_data['original_revenue'] + brand_data['oneclick_revenue']
        brand_data['real_orders'] = real_orders
        brand_data['real_revenue'] = real_revenue
        brand_data['aov'] = round(real_revenue / real_orders) if real_orders > 0 else 0

        total = brand_data['member_orders'] + brand_data['guest_orders']
        brand_data['member_ratio'] = round(brand_data['member_orders'] / total * 100, 1) if total > 0 else 0
        brand_data['guest_ratio'] = round(brand_data['guest_orders'] / total * 100, 1) if total > 0 else 0

        result[brand_code] = brand_data

    # MC 시리즈 (디지털 청첩장)
    mc_data = {
        'brand': 'MC시리즈(디지털)',
        'brand_code': 'MC',
        'total_sales': mc_row['Total_Sales_Price'] if mc_row else 0,
        'free_orders': mc_row['Total_Free_Order_Count'] if mc_row else 0,
        'charge_orders': mc_row['Total_Charge_Order_Count'] if mc_row else 0,
        'barunn_sales': mc_row['Barunn_Sales_Price'] if mc_row else 0,
        'bhands_sales': mc_row['Bhands_Sales_Price'] if mc_row else 0,
        'thecard_sales': mc_row['Thecard_Sales_Price'] if mc_row else 0,
        'premier_sales': mc_row['Premier_Sales_Price'] if mc_row else 0,
    }
    if mc_row:
        total_mc = mc_data['free_orders'] + mc_data['charge_orders']
        mc_data['total_orders'] = total_mc
        mc_data['charge_ratio'] = round(mc_data['charge_orders'] / total_mc * 100, 1) if total_mc > 0 else 0
        mc_data['aov'] = round(mc_data['total_sales'] / mc_data['charge_orders']) if mc_data['charge_orders'] > 0 else 0
    else:
        mc_data['total_orders'] = 0
        mc_data['charge_ratio'] = 0
        mc_data['aov'] = 0

    result['MC'] = mc_data
    return result


def fetch_all_periods(base_date=None):
    """4개 시점 데이터 조회 (base_date 기준)"""
    if base_date is None:
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        base = datetime.strptime(base_date, '%Y-%m-%d')

    periods = {
        'base': base,
        'wow': base - timedelta(days=7),
        'mom': base - timedelta(days=30),
        'yoy': base.replace(year=base.year - 1),
    }

    conn = get_conn()
    mc_conn = get_barunson_conn()

    results = {}
    for key, dt in periods.items():
        raw = fetch_day_metrics(conn, dt)
        mc = fetch_mc_metrics(mc_conn, dt)
        results[key] = {
            'date': dt.strftime('%Y-%m-%d'),
            'label': {
                'base': '기준일',
                'wow': '1주일 전',
                'mom': '1개월 전',
                'yoy': '1년 전',
            }[key],
            'metrics': aggregate_metrics(raw, mc),
        }

    conn.close()
    mc_conn.close()

    return {
        'base_date': base.strftime('%Y-%m-%d'),
        'periods': results,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>바른손 매출 비교 대시보드</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',-apple-system,sans-serif;background:#f0f2f5;color:#333;font-size:14px}
.header{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:20px 32px}
.header h1{font-size:20px;font-weight:600}
.header .sub{font-size:13px;opacity:.8;margin-top:4px}
.container{max-width:1400px;margin:0 auto;padding:20px 16px}

/* Date picker bar */
.date-bar{display:flex;align-items:center;gap:10px;margin-bottom:20px;background:#fff;padding:12px 16px;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);flex-wrap:wrap}
.date-bar label{font-weight:600;font-size:13px;color:#555}
.date-bar input[type=date]{padding:6px 12px;border:2px solid #e0e0e0;border-radius:6px;font-size:14px;font-family:inherit;cursor:pointer}
.date-bar input[type=date]:focus{border-color:#1a237e;outline:none}
.date-nav{display:flex;gap:4px}
.date-nav button{padding:6px 14px;border:2px solid #e0e0e0;border-radius:6px;background:#fff;cursor:pointer;font-size:13px;font-weight:500;transition:all .15s}
.date-nav button:hover{border-color:#1a237e;background:#e8eaf6}
.date-nav button.today-btn{border-color:#1a237e;color:#1a237e;font-weight:600}
.date-info{font-size:12px;color:#888;margin-left:auto}

/* Tabs */
.tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:10px 20px;background:#fff;border:2px solid #e0e0e0;border-radius:8px;cursor:pointer;font-weight:500;transition:all .2s}
.tab.active{border-color:#1a237e;background:#1a237e;color:#fff}
.tab:hover:not(.active){border-color:#9fa8da}

/* Section */
.section{margin-bottom:28px}
.section-title{font-size:16px;font-weight:700;margin-bottom:14px;padding-left:4px;border-left:4px solid #1a237e;padding-left:12px}

/* Comparison Table */
.comp-table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.comp-table th{background:#f5f5f5;padding:10px 14px;text-align:center;font-size:12px;color:#666;white-space:nowrap;border-bottom:2px solid #e0e0e0}
.comp-table td{padding:10px 14px;text-align:center;border-bottom:1px solid #f0f0f0;white-space:nowrap}
.comp-table tr:hover td{background:#fafafa}
.comp-table .row-label{text-align:left;font-weight:600;color:#333;background:#fafafa}
.comp-table .num{font-variant-numeric:tabular-nums;font-weight:500}

/* Change indicators */
.chg{font-size:11px;display:block;margin-top:2px;font-weight:600}
.chg.up{color:#d32f2f}
.chg.down{color:#1565c0}
.chg.flat{color:#9e9e9e}

/* Summary cards */
.summary-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.summary-card{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08);text-align:center}
.summary-card .label{font-size:11px;color:#888;margin-bottom:4px}
.summary-card .val{font-size:28px;font-weight:700;color:#1a237e}
.summary-card .unit{font-size:13px;color:#999}
.summary-card .sub{font-size:11px;color:#666;margin-top:4px}

/* Ratio bar */
.ratio-bar{display:flex;height:24px;border-radius:12px;overflow:hidden;margin:6px 0}
.ratio-bar .member{background:#42a5f5}
.ratio-bar .guest{background:#ef9a9a}
.ratio-legend{display:flex;gap:16px;font-size:11px;justify-content:center}
.ratio-legend span::before{content:'';display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:middle}
.ratio-legend .m::before{background:#42a5f5}
.ratio-legend .g::before{background:#ef9a9a}

.footer{text-align:center;font-size:11px;color:#aaa;padding:16px}
.loading{text-align:center;padding:60px;font-size:16px;color:#888}

/* MC sub-brand */
.mc-sub{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.mc-sub-card{background:#f5f5f5;border-radius:8px;padding:10px;text-align:center}
.mc-sub-card .name{font-size:11px;color:#888}
.mc-sub-card .val{font-size:16px;font-weight:700;color:#333}
</style>
</head>
<body>
<div class="header">
  <h1>바른손 매출 비교 대시보드</h1>
  <div class="sub" id="headerSub">로딩 중...</div>
</div>
<div class="container">
  <div class="date-bar">
    <label>기준일</label>
    <div class="date-nav">
      <button onclick="moveDate(-1)" title="이전 날">&larr;</button>
      <input type="date" id="datePicker" onchange="onDateChange()">
      <button onclick="moveDate(1)" title="다음 날">&rarr;</button>
    </div>
    <div class="date-nav">
      <button class="today-btn" onclick="goToday()">오늘</button>
      <button onclick="moveDate(-7)">-1주</button>
      <button onclick="moveDate(-30)">-1개월</button>
    </div>
    <div class="date-info" id="dateInfo"></div>
  </div>
  <div class="tabs" id="tabs">
    <div class="tab active" data-brand="SB">바른손몰</div>
    <div class="tab" data-brand="B">바른손카드</div>
    <div class="tab" data-brand="MC">MC시리즈(디지털)</div>
    <div class="tab" data-brand="ALL">전체 합산</div>
  </div>
  <div id="content"><div class="loading">데이터를 불러오는 중...</div></div>
</div>
<div class="footer" id="footer"></div>

<script>
let DATA = null;
let currentBrand = 'SB';

function fmt(n) { return n == null ? '-' : n.toLocaleString('ko-KR'); }
function fmtWon(n) { return n == null ? '-' : n.toLocaleString('ko-KR') + '원'; }
function pctChange(now, prev) {
  if (prev === 0 && now === 0) return {txt: '-', cls: 'flat'};
  if (prev === 0) return {txt: 'NEW', cls: 'up'};
  const p = ((now - prev) / prev * 100).toFixed(1);
  if (p > 0) return {txt: '+' + p + '%', cls: 'up'};
  if (p < 0) return {txt: p + '%', cls: 'down'};
  return {txt: '0%', cls: 'flat'};
}

function renderChange(now, prev) {
  const c = pctChange(now, prev);
  return `<span class="chg ${c.cls}">${c.txt}</span>`;
}

function cell(val, formatter, baseVal) {
  let html = `<span class="num">${formatter(val)}</span>`;
  if (baseVal !== undefined) html += renderChange(val, baseVal);
  return html;
}

function renderPhysicalBrand(brand) {
  const periods = DATA.periods;
  const t = periods.base.metrics[brand];
  const w = periods.wow.metrics[brand];
  const m = periods.mom.metrics[brand];
  const y = periods.yoy.metrics[brand];

  let html = '';

  // Summary cards
  html += `<div class="summary-row">
    <div class="summary-card">
      <div class="label">본주문 (원주문+원클릭)</div>
      <div class="val">${fmt(t.real_orders)}<span class="unit">건</span></div>
      <div class="sub">원주문 ${fmt(t.original_orders)} + 원클릭 ${fmt(t.oneclick_orders)}</div>
    </div>
    <div class="summary-card">
      <div class="label">매출</div>
      <div class="val">${fmt(Math.round(t.real_revenue/10000))}<span class="unit">만원</span></div>
      <div class="sub">${fmtWon(t.real_revenue)}</div>
    </div>
    <div class="summary-card">
      <div class="label">객단가 (AOV)</div>
      <div class="val">${fmt(t.aov)}<span class="unit">원</span></div>
    </div>
    <div class="summary-card">
      <div class="label">샘플주문</div>
      <div class="val">${fmt(t.sample_total)}<span class="unit">건</span></div>
      <div class="sub">회원 ${fmt(t.sample_member)} / 비회원 ${fmt(t.sample_guest)}</div>
    </div>
  </div>`;

  // 회원/비회원 비율
  html += `<div class="section"><div class="section-title">회원 / 비회원 비율</div>
    <div style="background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
      <div class="ratio-bar">
        <div class="member" style="width:${t.member_ratio}%"></div>
        <div class="guest" style="width:${t.guest_ratio}%"></div>
      </div>
      <div class="ratio-legend">
        <span class="m">회원 ${t.member_ratio}% (${fmt(t.member_orders)}건)</span>
        <span class="g">비회원 ${t.guest_ratio}% (${fmt(t.guest_orders)}건)</span>
      </div>
    </div></div>`;

  // 비교 테이블
  const rows = [
    ['샘플주문 (회원)', 'sample_member', fmt],
    ['샘플주문 (비회원)', 'sample_guest', fmt],
    ['샘플주문 합계', 'sample_total', fmt],
    ['원주문수', 'original_orders', fmt],
    ['원클릭수', 'oneclick_orders', fmt],
    ['본주문 합계', 'real_orders', fmt],
    ['매출', 'real_revenue', fmtWon],
    ['객단가 (AOV)', 'aov', fmtWon],
    ['회원비율', 'member_ratio', v => v + '%'],
    ['비회원비율', 'guest_ratio', v => v + '%'],
  ];

  html += `<div class="section"><div class="section-title">기간별 비교 (YOY / MOM / WOW)</div>
    <table class="comp-table">
    <thead><tr>
      <th>지표</th>
      <th>기준일<br><small>${periods.base.date}</small></th>
      <th>1주전 (WOW)<br><small>${periods.wow.date}</small></th>
      <th>WOW 변화</th>
      <th>1개월전 (MOM)<br><small>${periods.mom.date}</small></th>
      <th>MOM 변화</th>
      <th>1년전 (YOY)<br><small>${periods.yoy.date}</small></th>
      <th>YOY 변화</th>
    </tr></thead><tbody>`;

  rows.forEach(([label, key, formatter]) => {
    const tv = t[key], wv = w[key], mv = m[key], yv = y[key];
    html += `<tr>
      <td class="row-label">${label}</td>
      <td>${cell(tv, formatter)}</td>
      <td>${cell(wv, formatter)}</td>
      <td>${renderChange(tv, wv)}</td>
      <td>${cell(mv, formatter)}</td>
      <td>${renderChange(tv, mv)}</td>
      <td>${cell(yv, formatter)}</td>
      <td>${renderChange(tv, yv)}</td>
    </tr>`;
  });

  html += '</tbody></table></div>';
  return html;
}

function renderMC() {
  const periods = DATA.periods;
  const t = periods.base.metrics.MC;
  const w = periods.wow.metrics.MC;
  const m = periods.mom.metrics.MC;
  const y = periods.yoy.metrics.MC;

  let html = '';

  html += `<div class="summary-row">
    <div class="summary-card">
      <div class="label">총 주문수</div>
      <div class="val">${fmt(t.total_orders)}<span class="unit">건</span></div>
      <div class="sub">무료 ${fmt(t.free_orders)} / 유료 ${fmt(t.charge_orders)}</div>
    </div>
    <div class="summary-card">
      <div class="label">매출</div>
      <div class="val">${fmt(Math.round(t.total_sales/10000))}<span class="unit">만원</span></div>
      <div class="sub">${fmtWon(t.total_sales)}</div>
    </div>
    <div class="summary-card">
      <div class="label">유료 전환율</div>
      <div class="val">${t.charge_ratio}<span class="unit">%</span></div>
    </div>
    <div class="summary-card">
      <div class="label">유료 객단가</div>
      <div class="val">${fmt(t.aov)}<span class="unit">원</span></div>
    </div>
  </div>`;

  // MC 서브 브랜드
  html += `<div class="section"><div class="section-title">브랜드별 매출</div>
    <div class="mc-sub">
      <div class="mc-sub-card"><div class="name">바른</div><div class="val">${fmtWon(t.barunn_sales)}</div></div>
      <div class="mc-sub-card"><div class="name">비핸즈</div><div class="val">${fmtWon(t.bhands_sales)}</div></div>
      <div class="mc-sub-card"><div class="name">더카드</div><div class="val">${fmtWon(t.thecard_sales)}</div></div>
      <div class="mc-sub-card"><div class="name">프리미어</div><div class="val">${fmtWon(t.premier_sales)}</div></div>
    </div></div>`;

  // 비교 테이블
  const rows = [
    ['총 주문수', 'total_orders', fmt],
    ['무료 주문수', 'free_orders', fmt],
    ['유료 주문수', 'charge_orders', fmt],
    ['매출', 'total_sales', fmtWon],
    ['유료 전환율', 'charge_ratio', v => v + '%'],
    ['유료 객단가', 'aov', fmtWon],
  ];

  html += `<div class="section"><div class="section-title">기간별 비교 (YOY / MOM / WOW)</div>
    <table class="comp-table">
    <thead><tr>
      <th>지표</th>
      <th>기준일<br><small>${periods.base.date}</small></th>
      <th>1주전 (WOW)<br><small>${periods.wow.date}</small></th>
      <th>WOW 변화</th>
      <th>1개월전 (MOM)<br><small>${periods.mom.date}</small></th>
      <th>MOM 변화</th>
      <th>1년전 (YOY)<br><small>${periods.yoy.date}</small></th>
      <th>YOY 변화</th>
    </tr></thead><tbody>`;

  rows.forEach(([label, key, formatter]) => {
    const tv = t[key], wv = w[key], mv = m[key], yv = y[key];
    html += `<tr>
      <td class="row-label">${label}</td>
      <td>${cell(tv, formatter)}</td>
      <td>${cell(wv, formatter)}</td>
      <td>${renderChange(tv, wv)}</td>
      <td>${cell(mv, formatter)}</td>
      <td>${renderChange(tv, mv)}</td>
      <td>${cell(yv, formatter)}</td>
      <td>${renderChange(tv, yv)}</td>
    </tr>`;
  });

  html += '</tbody></table></div>';
  return html;
}

function renderAll() {
  const periods = DATA.periods;
  // 바른손몰 + 바른손카드 합산
  function sum(period, key) {
    const sb = periods[period].metrics['SB'];
    const b = periods[period].metrics['B'];
    return (sb[key] || 0) + (b[key] || 0);
  }
  function sumMC(period, key) {
    return periods[period].metrics['MC'][key] || 0;
  }

  let html = '<div class="section"><div class="section-title">실물(바른손몰+바른손카드) 합산</div>';
  const physRows = [
    ['샘플주문 (회원)', 'sample_member'],
    ['샘플주문 (비회원)', 'sample_guest'],
    ['샘플주문 합계', 'sample_total'],
    ['본주문 합계', 'real_orders'],
    ['매출', 'real_revenue'],
    ['객단가', 'aov'],
  ];

  html += `<table class="comp-table"><thead><tr>
    <th>지표</th><th>기준일</th><th>1주전</th><th>WOW</th><th>1개월전</th><th>MOM</th><th>1년전</th><th>YOY</th>
  </tr></thead><tbody>`;

  physRows.forEach(([label, key]) => {
    const isWon = key === 'real_revenue' || key === 'aov';
    const f = isWon ? fmtWon : fmt;
    let tv, wv, mv, yv;
    if (key === 'aov') {
      const tRev = sum('today','real_revenue'), tOrd = sum('today','real_orders');
      const wRev = sum('wow','real_revenue'), wOrd = sum('wow','real_orders');
      const mRev = sum('mom','real_revenue'), mOrd = sum('mom','real_orders');
      const yRev = sum('yoy','real_revenue'), yOrd = sum('yoy','real_orders');
      tv = tOrd ? Math.round(tRev/tOrd) : 0;
      wv = wOrd ? Math.round(wRev/wOrd) : 0;
      mv = mOrd ? Math.round(mRev/mOrd) : 0;
      yv = yOrd ? Math.round(yRev/yOrd) : 0;
    } else {
      tv = sum('today', key);
      wv = sum('wow', key);
      mv = sum('mom', key);
      yv = sum('yoy', key);
    }
    html += `<tr><td class="row-label">${label}</td>
      <td>${cell(tv,f)}</td><td>${cell(wv,f)}</td><td>${renderChange(tv,wv)}</td>
      <td>${cell(mv,f)}</td><td>${renderChange(tv,mv)}</td>
      <td>${cell(yv,f)}</td><td>${renderChange(tv,yv)}</td></tr>`;
  });
  html += '</tbody></table></div>';

  // MC 합산
  html += '<div class="section"><div class="section-title">MC시리즈(디지털) 합산</div>';
  const mcRows = [
    ['총 주문수', 'total_orders'],
    ['매출', 'total_sales'],
    ['유료 객단가', 'aov'],
  ];
  html += `<table class="comp-table"><thead><tr>
    <th>지표</th><th>기준일</th><th>1주전</th><th>WOW</th><th>1개월전</th><th>MOM</th><th>1년전</th><th>YOY</th>
  </tr></thead><tbody>`;
  mcRows.forEach(([label, key]) => {
    const isWon = key === 'total_sales' || key === 'aov';
    const f = isWon ? fmtWon : fmt;
    const tv = sumMC('today',key), wv = sumMC('wow',key), mv = sumMC('mom',key), yv = sumMC('yoy',key);
    html += `<tr><td class="row-label">${label}</td>
      <td>${cell(tv,f)}</td><td>${cell(wv,f)}</td><td>${renderChange(tv,wv)}</td>
      <td>${cell(mv,f)}</td><td>${renderChange(tv,mv)}</td>
      <td>${cell(yv,f)}</td><td>${renderChange(tv,yv)}</td></tr>`;
  });
  html += '</tbody></table></div>';

  return html;
}

function render() {
  if (!DATA) return;
  const el = document.getElementById('content');
  if (currentBrand === 'MC') {
    el.innerHTML = renderMC();
  } else if (currentBrand === 'ALL') {
    el.innerHTML = renderAll();
  } else {
    el.innerHTML = renderPhysicalBrand(currentBrand);
  }
}

document.getElementById('tabs').addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (!tab) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  currentBrand = tab.dataset.brand;
  render();
});

// Date navigation
let selectedDate = new Date().toISOString().slice(0, 10);

function initDatePicker() {
  const picker = document.getElementById('datePicker');
  picker.value = selectedDate;
  picker.max = new Date().toISOString().slice(0, 10);
}

function onDateChange() {
  selectedDate = document.getElementById('datePicker').value;
  fetchData();
}

function moveDate(days) {
  const d = new Date(selectedDate);
  d.setDate(d.getDate() + days);
  const today = new Date();
  today.setHours(0,0,0,0);
  if (d > today) return;
  selectedDate = d.toISOString().slice(0, 10);
  document.getElementById('datePicker').value = selectedDate;
  fetchData();
}

function goToday() {
  selectedDate = new Date().toISOString().slice(0, 10);
  document.getElementById('datePicker').value = selectedDate;
  fetchData();
}

function getDayName(dateStr) {
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  return days[new Date(dateStr).getDay()];
}

function fetchData() {
  const el = document.getElementById('content');
  el.innerHTML = '<div class="loading">데이터를 불러오는 중...</div>';
  fetch('/api/data?date=' + selectedDate)
    .then(r => r.json())
    .then(d => {
      DATA = d;
      const base = d.periods.base.date;
      const dayName = getDayName(base);
      const isToday = base === new Date().toISOString().slice(0, 10);
      document.getElementById('headerSub').textContent =
        `${base} (${dayName})${isToday ? ' - 오늘' : ''} vs WOW(${d.periods.wow.date}) vs MOM(${d.periods.mom.date}) vs YOY(${d.periods.yoy.date})`;
      document.getElementById('dateInfo').textContent =
        `비교: WOW ${d.periods.wow.date} / MOM ${d.periods.mom.date} / YOY ${d.periods.yoy.date}`;
      document.getElementById('footer').textContent = '마지막 갱신: ' + d.updated_at;
      render();
    })
    .catch(err => {
      el.innerHTML = '<div class="loading">오류: ' + err.message + '</div>';
    });
}

initDatePicker();
fetchData();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/data':
            try:
                qs = parse_qs(parsed.query)
                base_date = qs.get('date', [None])[0]
                data = fetch_all_periods(base_date)
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
            self.wfile.write(HTML_PAGE.encode('utf-8'))

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"바른손 매출 비교 대시보드")
    print(f"http://localhost:{PORT}")
    print(f"Ctrl+C로 종료")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        server.server_close()
