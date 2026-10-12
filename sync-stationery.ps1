# 스테이셔너리(기념굿즈 대시보드, 로컬 10050) 코드를 배포 저장소 stationery/ 로 복사한다.
# 원본은 로컬 폴더가 기준(단일 진실원)이며, 이 폴더는 Docker 배포용 사본이다.
#   - C:\Users\LG\deco-dashboard\app.py, analytics.py            → stationery\
#   - C:\Users\LG\barunson-dashboard\build_sku_daily.py + json    → stationery\ref\
# 10050 화면을 고친 뒤 배포본에도 반영하려면: 이 스크립트 실행 → git commit/push → Actions 빌드 → 재배포
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$deco = 'C:\Users\LG\deco-dashboard'
$ref  = 'C:\Users\LG\barunson-dashboard'

New-Item -ItemType Directory -Force "$repo\stationery\ref\data" | Out-Null
Copy-Item "$deco\app.py", "$deco\analytics.py" "$repo\stationery\" -Force
Copy-Item "$ref\build_sku_daily.py", "$ref\categories.json", "$ref\products.json", "$ref\custom_codes.json" "$repo\stationery\ref\" -Force
if (Test-Path "$ref\data\sync_status.json") { Copy-Item "$ref\data\sync_status.json" "$repo\stationery\ref\data\" -Force }
Write-Host "stationery 동기화 완료 (products.json 기준일: $((Get-Item "$ref\products.json").LastWriteTime))"
