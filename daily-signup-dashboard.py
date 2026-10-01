#!/usr/bin/env python3
"""오늘의 가입자 현황 대시보드 - 자동 새로고침 웹페이지"""
import os
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import pymssql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PORT = 10010


def get_db_connection():
    return pymssql.connect(
        server=os.getenv("DB_SERVER"),
        port=int(os.getenv("DB_PORT", "1433")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="barunson",
    )


def fetch_today_signups():
    """오늘 가입자 수 조회"""
    conn = get_db_connection()
    cursor = conn.cursor(as_dict=True)
    today = datetime.now().strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # 오늘 총 가입자 수
    cursor.execute(
        "SELECT COUNT(DISTINCT User_ID) as cnt "
        "FROM TB_Invitation "
        "WHERE Regist_DateTime >= %s AND Regist_DateTime < %s",
        (today, tomorrow)
    )
    total = cursor.fetchone()['cnt']

    # 시간대별 가입자 수
    cursor.execute(
        "SELECT DATEPART(HOUR, Regist_DateTime) as hour, COUNT(DISTINCT User_ID) as cnt "
        "FROM TB_Invitation "
        "WHERE Regist_DateTime >= %s AND Regist_DateTime < %s "
        "GROUP BY DATEPART(HOUR, Regist_DateTime) "
        "ORDER BY hour",
        (today, tomorrow)
    )
    hourly = [{'hour': row['hour'], 'cnt': row['cnt']} for row in cursor.fetchall()]

    # 최근 7일 일별 가입자 수
    seven_days_ago = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d')
    cursor.execute(
        "SELECT CAST(Regist_DateTime AS DATE) as reg_date, COUNT(DISTINCT User_ID) as cnt "
        "FROM TB_Invitation "
        "WHERE Regist_DateTime >= %s AND Regist_DateTime < %s "
        "GROUP BY CAST(Regist_DateTime AS DATE) "
        "ORDER BY reg_date",
        (seven_days_ago, tomorrow)
    )
    daily = [{'date': str(row['reg_date']), 'cnt': row['cnt']} for row in cursor.fetchall()]

    conn.close()
    return {
        'today': today,
        'total': total,
        'hourly': hourly,
        'daily': daily,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>바른손 - 오늘의 가입자 현황</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', -apple-system, sans-serif; background: #f0f2f5; color: #333; }
  .header { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; padding: 24px 32px; }
  .header h1 { font-size: 22px; font-weight: 600; }
  .header .date { font-size: 14px; opacity: 0.85; margin-top: 4px; }
  .container { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
  .big-number { background: #fff; border-radius: 12px; padding: 32px; text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }
  .big-number .label { font-size: 14px; color: #666; margin-bottom: 8px; }
  .big-number .value { font-size: 56px; font-weight: 700; color: #1a73e8; }
  .big-number .unit { font-size: 18px; color: #888; margin-left: 4px; }
  .card { background: #fff; border-radius: 12px; padding: 24px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }
  .card h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #333; }
  .bar-chart { display: flex; align-items: flex-end; gap: 4px; height: 160px; padding-top: 8px; }
  .bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
  .bar { width: 100%; min-width: 16px; background: linear-gradient(180deg, #4285f4, #1a73e8);
         border-radius: 4px 4px 0 0; transition: height 0.5s ease; position: relative; }
  .bar:hover { opacity: 0.85; }
  .bar-label { font-size: 11px; color: #888; margin-top: 6px; }
  .bar-value { font-size: 10px; color: #555; margin-bottom: 4px; font-weight: 600; }
  .daily-chart .bar { background: linear-gradient(180deg, #34a853, #1e8e3e); }
  .daily-chart .bar.today { background: linear-gradient(180deg, #4285f4, #1a73e8); }
  .footer { text-align: center; font-size: 12px; color: #999; padding: 16px; }
  .auto-refresh { display: inline-block; background: #e8f0fe; color: #1a73e8;
                  padding: 4px 12px; border-radius: 20px; font-size: 12px; margin-left: 12px; }
  .status-dot { display: inline-block; width: 8px; height: 8px; background: #34a853;
                border-radius: 50%; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
</style>
</head>
<body>
<div class="header">
  <h1>바른손 가입자 현황 <span class="auto-refresh"><span class="status-dot"></span>60초 자동 갱신</span></h1>
  <div class="date" id="headerDate"></div>
</div>
<div class="container">
  <div class="big-number">
    <div class="label">오늘의 신규 가입자</div>
    <div><span class="value" id="totalCount">-</span><span class="unit">명</span></div>
  </div>
  <div class="card">
    <h2>시간대별 가입자</h2>
    <div class="bar-chart" id="hourlyChart"></div>
  </div>
  <div class="card daily-chart">
    <h2>최근 7일 일별 가입자</h2>
    <div class="bar-chart" id="dailyChart"></div>
  </div>
</div>
<div class="footer" id="footer"></div>

<script>
function renderData(data) {
  document.getElementById('headerDate').textContent = data.today + ' 기준';
  document.getElementById('totalCount').textContent = data.total.toLocaleString();
  document.getElementById('footer').textContent = '마지막 갱신: ' + data.updated_at;

  // 시간대별 차트
  const hourlyEl = document.getElementById('hourlyChart');
  hourlyEl.innerHTML = '';
  const allHours = Array.from({length: 24}, (_, i) => i);
  const hourMap = {};
  data.hourly.forEach(h => hourMap[h.hour] = h.cnt);
  const maxHourly = Math.max(1, ...Object.values(hourMap));

  allHours.forEach(h => {
    const cnt = hourMap[h] || 0;
    const pct = (cnt / maxHourly) * 100;
    const col = document.createElement('div');
    col.className = 'bar-col';
    col.innerHTML =
      (cnt > 0 ? '<div class="bar-value">' + cnt + '</div>' : '') +
      '<div class="bar" style="height:' + Math.max(pct, (cnt > 0 ? 3 : 0)) + '%"></div>' +
      '<div class="bar-label">' + h + '</div>';
    hourlyEl.appendChild(col);
  });

  // 일별 차트
  const dailyEl = document.getElementById('dailyChart');
  dailyEl.innerHTML = '';
  const maxDaily = Math.max(1, ...data.daily.map(d => d.cnt));

  data.daily.forEach(d => {
    const pct = (d.cnt / maxDaily) * 100;
    const isToday = d.date === data.today;
    const col = document.createElement('div');
    col.className = 'bar-col';
    const shortDate = d.date.slice(5);
    col.innerHTML =
      '<div class="bar-value">' + d.cnt.toLocaleString() + '</div>' +
      '<div class="bar' + (isToday ? ' today' : '') + '" style="height:' + Math.max(pct, 3) + '%"></div>' +
      '<div class="bar-label">' + shortDate + (isToday ? '(Today)' : '') + '</div>';
    dailyEl.appendChild(col);
  });
}

function fetchData() {
  fetch('/api/data')
    .then(r => r.json())
    .then(renderData)
    .catch(err => console.error('Fetch error:', err));
}

fetchData();
setInterval(fetchData, 60000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/data':
            try:
                data = fetch_today_signups()
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
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))

    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"바른손 가입자 현황 대시보드")
    print(f"http://localhost:{PORT}")
    print(f"60초마다 자동 새로고침됩니다. Ctrl+C로 종료.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
        server.server_close()
