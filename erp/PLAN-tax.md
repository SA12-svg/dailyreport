# ERP 세무관리 모듈 구현 계획

> 작성일: 2026-03-10

## 개요

XERP RP(매출매입) 모듈의 세금계산서/부가세 관련 데이터를 조회하는 ERP 세무관리 화면 구현.
회계관리/매출매입관리 모듈과 동일한 아키텍처 패턴(Express + React + Ant Design + React Query) 적용.

## 대상 XERP 테이블

| 화면 | 주요 테이블 | 레코드 수 |
|------|-----------|-----------|
| 세금계산서 조회 | rpBillHeader + rpBillItem | 4.0M + 25.8M |
| 부가세 신고 자동집계 | rpBillHeader | 4.0M |
| 전자세금계산서 현황 | rpBillHeader | 4.0M |
| 합계표 | rpBillHeader | 4.0M |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/tax/invoices | 세금계산서 목록 |
| GET | /api/v1/tax/invoices/:billNo | 세금계산서 상세 |
| GET | /api/v1/tax/vat-return | 부가세 신고 자동집계 |
| GET | /api/v1/tax/e-invoices | 전자세금계산서 현황 |
| GET | /api/v1/tax/summary-table | 합계표 (거래처별 집계) |
| GET | /api/v1/tax/customers | 거래처 목록 (필터용) |

## 클라이언트 페이지

| 파일 | 경로 | 설명 |
|------|------|------|
| TaxInvoiceListPage.tsx | /tax/invoices | 세금계산서 조회 |
| VatReturnPage.tsx | /tax/vat-return | 부가세 신고 자동집계 |
| EInvoiceStatusPage.tsx | /tax/e-invoices | 전자세금계산서 현황 |
| SummaryTablePage.tsx | /tax/summary-table | 합계표 |

## 성능 고려사항

- rpBillHeader(4M건): IX_rpBillHeader 클러스터드 인덱스 (SiteCode + ArApGubun + BillDate + BillNo) 활용
- rpBillItem(25.8M건): PK 클러스터드 인덱스 (SiteCode + BillNo + ArApGubun + BillSerNo) 활용
- TaxCode 필터로 세금계산서만 추출 (과세/면세/영세 구분)
- 부가세 집계: 분기별 GROUP BY로 서버에서 집계
- 모든 조회에 WITH (NOLOCK) 적용
- 페이지네이션: OFFSET/FETCH NEXT 방식

## 파일 구조

```
server/src/modules/tax/
  tax.types.ts       - 타입 정의
  tax.queries.ts     - DB 쿼리 함수
  tax.controller.ts  - Express 핸들러
  tax.routes.ts      - 라우터 설정

client/src/api/
  tax.api.ts         - API 클라이언트

client/src/pages/Tax/
  TaxInvoiceListPage.tsx
  VatReturnPage.tsx
  EInvoiceStatusPage.tsx
  SummaryTablePage.tsx
```
