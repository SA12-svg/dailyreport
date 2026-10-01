@echo off
REM === Windows 작업 스케줄러에 데일리 대시보드 자동 시작 등록 ===
REM 관리자 권한으로 실행해주세요!

echo 바른손 데일리 리포트 대시보드 - 스케줄러 등록
echo.

REM 기존 작업 삭제 (있으면)
schtasks /delete /tn "BarunsonDailyDashboard" /f 2>NUL

REM 매일 아침 7:55에 서버 시작 (8시 전에 미리 준비)
schtasks /create /tn "BarunsonDailyDashboard" /tr "C:\src\barunson-database-reference\user\start-daily-dashboard.bat" /sc daily /st 07:55 /rl HIGHEST /f

if %ERRORLEVEL%==0 (
    echo.
    echo [성공] 매일 아침 7:55에 대시보드 서버가 자동 시작됩니다.
    echo - 작업 이름: BarunsonDailyDashboard
    echo - 실행 시간: 매일 07:55
    echo - 대시보드 주소: http://localhost:10030
    echo.
    echo 8시에 브라우저를 열면 바로 최신 데이터를 볼 수 있습니다!
) else (
    echo.
    echo [실패] 관리자 권한으로 다시 실행해주세요.
    echo 방법: 이 파일을 마우스 우클릭 - "관리자 권한으로 실행"
)

echo.
pause
