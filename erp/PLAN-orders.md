# ERP 주문관리 모듈 구현 계획

> 작성일: 2026-03-10

## 개요

바른손 주문 데이터를 조회하는 ERP 주문관리 화면 구현.
디지털 주문(barunson TB_Order)과 실물 주문(bar_shop1 custom_order), 인쇄작업현황을 통합 관리.
기존 모듈과 동일한 아키텍처 패턴(Express + React + Ant Design + React Query) 적용.

## 대상 테이블

| 화면 | DB | 주요 테이블 | 레코드 수 |
|------|-----|-----------|-----------|
| 디지털주문조회 | barunson | TB_Order + TB_Order_Product | ~5M |
| 실물주문조회 | bar_shop1 | custom_order + custom_order_item | 1.9M + 7.9M |
| 인쇄작업현황 | bar_shop1 | custom_order_printjob + custom_order_plist | 3.3M + 7.0M |
| 통합주문검색 | barunson + bar_shop1 | TB_Order + custom_order | 복합 |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/orders/digital | 디지털(모바일초대장) 주문 목록 |
| GET | /api/v1/orders/digital/:orderId | 디지털 주문 상세 |
| GET | /api/v1/orders/physical | 실물(카드) 주문 목록 |
| GET | /api/v1/orders/physical/:orderSeq | 실물 주문 상세 |
| GET | /api/v1/orders/printjobs | 인쇄작업 현황 |
| GET | /api/v1/orders/search | 통합 주문 검색 |

## 클라이언트 페이지

| 파일 | 경로 | 설명 |
|------|------|------|
| DigitalOrdersPage.tsx | /orders/digital | 디지털 주문 목록 |
| PhysicalOrdersPage.tsx | /orders/physical | 실물 주문 목록 |
| PrintJobStatusPage.tsx | /orders/printjobs | 인쇄작업 현황 |
| OrderSearchPage.tsx | /orders/search | 통합 주문 검색 |

## 성능 고려사항

- TB_Order: IX_TB_Order_Order_DateTime 인덱스 활용, Order_DateTime 기반 조회
- custom_order(1.9M건): order_seq PK 클러스터드 인덱스 활용
- custom_order_item(7.9M건): order_seq FK 인덱스 활용
- custom_order_printjob(3.3M건): pdate 범위 축소 후 PK(cdate, cseq, pid) 순 정렬
- 모든 조회에 WITH (NOLOCK) 적용
- 페이지네이션: OFFSET/FETCH NEXT 방식
- PII 마스킹: 이름/이메일/전화번호 서버 사이드 마스킹

## 파일 구조

```
server/src/modules/orders/
  orders.types.ts    - 타입 정의
  orders.queries.ts  - DB 쿼리 함수
  orders.controller.ts - Express 핸들러
  orders.routes.ts   - 라우터 설정

client/src/api/
  orders.api.ts      - API 클라이언트

client/src/pages/Orders/
  DigitalOrdersPage.tsx
  PhysicalOrdersPage.tsx
  PrintJobStatusPage.tsx
  OrderSearchPage.tsx
```
