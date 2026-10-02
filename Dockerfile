FROM python:3.12-slim

WORKDIR /app

# pymssql은 플랫폼에 따라 프리빌드 휠이 없을 수 있어 소스 빌드 대비 freetds 개발 헤더 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    freetds-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 로컬 실행(python daily-report-dashboard.py)은 기본 10030 유지.
# 컨테이너 배포 플랫폼이 보통 3000번을 기본으로 기대하므로 컨테이너 안에서만 3000으로 오버라이드.
# 플랫폼이 자체 PORT를 주입하면 그 값이 우선됨(docker run -e PORT=... 가 ENV보다 우선).
ENV PORT=3000
EXPOSE 3000

# DB_SERVER / DB_PORT / DB_USER / DB_PASSWORD, DASHBOARD_USER / DASHBOARD_PASSWORD는
# 런타임에 환경변수(시크릿)로 주입 — 이미지에는 절대 포함하지 않음
CMD ["python", "daily-report-dashboard.py"]
