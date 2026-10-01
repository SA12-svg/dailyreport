# ERP 재고관리 모듈 구현 계획

> 작성일: 2026-03-10

## 개요

XERP MM(자재관리) 모듈 데이터를 조회하는 ERP 재고관리 화면 구현.
회계관리 모듈과 동일한 아키텍처 패턴(Express + React + Ant Design + React Query) 적용.

## 대상 XERP 테이블

| 화면 | 주요 테이블 | 레코드 수 |
|------|-----------|-----------|
| 현재재고 | mmInventory | 76K |
| 입출고내역 | mmInoutHeader + mmInoutItem | 5.5M + 40.1M |
| 재고평가 | C_mmEvaData + C_mmInvMonth | 11.6M |
| 청구요청 | mmRequisitHeader + mmRequisitItem | 216K + 1.9M |
| 월마감 | mmMonthClose | 528 |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/inventory/stock | 현재재고 조회 |
| GET | /api/v1/inventory/inout | 입출고내역 목록 |
| GET | /api/v1/inventory/inout/:inoutNo | 입출고 상세 |
| GET | /api/v1/inventory/valuation | 재고평가 조회 |
| GET | /api/v1/inventory/requisitions | 청구요청 목록 |
| GET | /api/v1/inventory/requisitions/:reqNo | 청구요청 상세 |
| GET | /api/v1/inventory/month-close | 월마감 이력 |
| GET | /api/v1/inventory/warehouses | 창고 목록 (필터용) |

## 클라이언트 페이지

| 파일 | 경로 | 설명 |
|------|------|------|
| StockPage.tsx | /inventory/stock | 현재재고 현황 |
| InoutListPage.tsx | /inventory/inout | 입출고내역 목록 |
| ValuationPage.tsx | /inventory/valuation | 재고평가 |
| RequisitionListPage.tsx | /inventory/requisitions | 청구요청 목록 |
| MonthClosePage.tsx | /inventory/month-close | 월마감 이력 |

## 성능 고려사항

- mmInoutItem(40M건): 반드시 InoutDate 인덱스로 범위 축소
- C_mmInvMonth/C_mmEvaData(11.6M건): SiteCode + InvMonth PK 활용
- mmInoutHeader(5.5M건): IDX_mmInoutHeader_LSM2 (SiteCode + InoutDate) 활용
- 모든 조회에 WITH (NOLOCK) 적용
- 페이지네이션: OFFSET/FETCH NEXT 방식

## 파일 구조

```
server/src/modules/inventory/
  inventory.types.ts    - 타입 정의
  inventory.queries.ts  - DB 쿼리 함수
  inventory.controller.ts - Express 핸들러
  inventory.routes.ts   - 라우터 설정

client/src/api/
  inventory.api.ts      - API 클라이언트

client/src/pages/Inventory/
  StockPage.tsx
  InoutListPage.tsx
  ValuationPage.tsx
  RequisitionListPage.tsx
  MonthClosePage.tsx
```
