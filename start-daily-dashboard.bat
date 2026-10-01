@echo off
REM === 바른손 데일리 리포트 대시보드 자동 시작 ===
REM 이 파일을 Windows 작업 스케줄러에 등록하면 매일 아침 자동 실행됩니다.

cd /d "C:\src\barunson-database-reference\user"

REM 이미 실행 중인 프로세스 확인
tasklist /FI "WINDOWTITLE eq daily-report-dashboard" 2>NUL | find /I "python" >NUL
if %ERRORLEVEL%==0 (
    echo [%date% %time%] 이미 실행 중입니다.
) else (
    REM 서버 시작 (백그라운드)
    start "daily-report-dashboard" /MIN python daily-report-dashboard.py
    echo [%date% %time%] 대시보드 서버 시작됨 (http://localhost:10030)
    REM DB 로딩 대기 후 브라우저 오픈 (127.0.0.1 사용 - localhost는 IPv6 타임아웃 가능)
    timeout /t 4 /nobreak >NUL
)

start "" "http://127.0.0.1:10030/"
