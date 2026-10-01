# ERP 배송관리 모듈 구현 계획

> 작성일: 2026-03-10

## 개요

바른손 배송 데이터를 조회하는 ERP 배송관리 화면 구현.
bar_shop1의 DELIVERY_INFO, DELIVERY_INFO_DETAIL, DELIVERY_INFO_DELCODE 테이블 기반.
기존 모듈과 동일한 아키텍처 패턴(Express + React + Ant Design + React Query) 적용.

## 대상 테이블

| 화면 | DB | 주요 테이블 | 레코드 수 |
|------|-----|-----------|-----------|
| 배송목록 | bar_shop1 | DELIVERY_INFO | 1.4M |
| 배송상세 | bar_shop1 | DELIVERY_INFO + DELIVERY_INFO_DETAIL + DELIVERY_INFO_DELCODE | 1.4M + 4.5M + 3.3M |
| 송장조회 | bar_shop1 | DELIVERY_INFO_DELCODE + DELIVERY_INFO | 3.3M + 1.4M |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/delivery/list | 배송 목록 (기간/주문번호/수령인 필터) |
| GET | /api/v1/delivery/detail/:orderSeq/:deliverySeq | 배송 상세 (기본정보 + 항목 + 송장) |
| GET | /api/v1/delivery/tracking | 송장번호 검색 |

## 클라이언트 페이지

| 파일 | 경로 | 설명 |
|------|------|------|
| DeliveryListPage.tsx | /delivery/list | 배송 목록 |
| DeliveryDetailPage.tsx | /delivery/detail/:orderSeq/:deliverySeq | 배송 상세 |
| TrackingSearchPage.tsx | /delivery/tracking | 송장번호 조회 |

## PII 마스킹

| 필드 | 원본 예시 | 마스킹 결과 |
|------|----------|------------|
| NAME (수령인) | 홍길동 | 홍*동 |
| PHONE / HPHONE | 010-1234-5678 | 010-****-5678 |
| ADDR (주소) | 서울시 강남구 역삼동 123 | 서울시 강남구 *** |
| ADDR_DETAIL | 101동 201호 | *** |
| EMAIL | user@gmail.com | use****@****.com |

## 성능 고려사항

- DELIVERY_INFO(1.4M건): DELIVERY_DATE 범위 축소 후 ORDER_SEQ DESC 정렬
- DELIVERY_INFO_DELCODE(3.3M건): delivery_code_num 완전 일치 검색
- 모든 조회에 WITH (NOLOCK) 적용
- 페이지네이션: OFFSET/FETCH NEXT 방식
- 2단계 쿼리: COUNT (전체건수) → DATA (페이지네이션)

## 파일 구조

```
server/src/modules/delivery/
  delivery.types.ts    - 타입 정의
  delivery.queries.ts  - DB 쿼리 함수 (PII 마스킹 포함)
  delivery.controller.ts - Express 핸들러
  delivery.routes.ts   - 라우터 설정

client/src/api/
  delivery.api.ts      - API 클라이언트

client/src/pages/Delivery/
  DeliveryListPage.tsx     - 배송 목록
  DeliveryDetailPage.tsx   - 배송 상세
  TrackingSearchPage.tsx   - 송장번호 조회
```
