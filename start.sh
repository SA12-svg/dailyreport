#!/bin/sh
# 컨테이너 엔트리포인트: 스테이셔너리(Flask, 내부 127.0.0.1:10050)를 백그라운드로 띄우고
# 데일리 리포트(외부 노출 포트 $PORT)를 포그라운드로 실행. 스테이셔너리가 죽으면 5초 후 재시작.
(
  cd /app/stationery
  while true; do
    SKU_OPEN_BROWSER=0 DECO_REF_DIR=/app/stationery/ref python app.py
    echo "[start.sh] stationery 종료 — 5초 후 재시작"
    sleep 5
  done
) &
exec python daily-report-dashboard.py
