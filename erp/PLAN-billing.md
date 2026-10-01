# ERP 매출매입관리 모듈 구현 계획

> 작성일: 2026-03-10

## 개요

XERP RP(매출매입) 모듈 데이터를 조회하는 ERP 매출매입관리 화면 구현.
회계관리/재고관리 모듈과 동일한 아키텍처 패턴(Express + React + Ant Design + React Query) 적용.

## 대상 XERP 테이블

| 화면 | 주요 테이블 | 레코드 수 |
|------|-----------|-----------|
| AR/AP 목록 | rpBillHeader | 4.0M |
| AR/AP 상세 | rpBillHeader + rpBillItem | 4.0M + 25.8M |
| 채권연령분석 | rpMoneyExpect | 2.6M |
| 수금현황 | rpExpectMoneyAlloc | 3.7M |
| 미수금상세 | rpMoneyExpect | 2.6M |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/billing/bills | AR/AP 청구 목록 |
| GET | /api/v1/billing/bills/:billNo | 청구 상세 (헤더 + 항목) |
| GET | /api/v1/billing/aging | 채권연령분석 |
| GET | /api/v1/billing/collections | 수금현황 |
| GET | /api/v1/billing/outstanding | 미수금 상세 |
| GET | /api/v1/billing/customers | 거래처 목록 (필터용) |

## 클라이언트 페이지

| 파일 | 경로 | 설명 |
|------|------|------|
| BillListPage.tsx | /billing/bills | AR/AP 청구 목록 |
| BillDetailPage.tsx | /billing/bills/:billNo | 청구 상세 |
| AgingAnalysisPage.tsx | /billing/aging | 채권연령분석 |
| CollectionStatusPage.tsx | /billing/collections | 수금현황 |
| OutstandingDetailPage.tsx | /billing/outstanding | 미수금 상세 |

## 성능 고려사항

- rpBillHeader(4M건): IX_rpBillHeader 클러스터드 인덱스 (SiteCode + ArApGubun + BillDate + BillNo) 활용
- rpBillItem(25.8M건): PK 클러스터드 인덱스 (SiteCode + BillNo + ArApGubun + BillSerNo) 활용
- rpMoneyExpect(2.6M건): SiteCode + OriginNo 기반 조회
- rpExpectMoneyAlloc(3.7M건): SiteCode + OriginNo 기반 조회
- 모든 조회에 WITH (NOLOCK) 적용
- 페이지네이션: OFFSET/FETCH NEXT 방식
- AR/AP 분리 조회로 인덱스 효율 극대화

## 파일 구조

```
server/src/modules/billing/
  billing.types.ts    - 타입 정의
  billing.queries.ts  - DB 쿼리 함수
  billing.controller.ts - Express 핸들러
  billing.routes.ts   - 라우터 설정

client/src/api/
  billing.api.ts      - API 클라이언트

client/src/pages/Billing/
  BillListPage.tsx
  BillDetailPage.tsx
  AgingAnalysisPage.tsx
  CollectionStatusPage.tsx
  OutstandingDetailPage.tsx
```
