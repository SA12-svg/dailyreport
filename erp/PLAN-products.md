# ERP 상품관리 모듈 구현 계획

> 작성일: 2026-03-10

## 개요

바른손 상품 데이터를 조회하는 ERP 상품관리 화면 구현.
MC시리즈 디지털 상품(barunson TB_Product)과 실물 카드 상품(bar_shop1 S2_Card), 카드 카테고리(S2_CardKindInfo)를 통합 관리.
기존 모듈과 동일한 아키텍처 패턴(Express + React + Ant Design + React Query) 적용.

## 대상 테이블

| 화면 | DB | 주요 테이블 | 레코드 수 |
|------|-----|-----------|-----------|
| MC시리즈 디지털 상품 | barunson | TB_Product + TB_Product_Image | 소규모 |
| 실물 카드 상품 목록 | bar_shop1 | S2_Card | 8,458 |
| 실물 카드 상품 상세 | bar_shop1 | S2_Card + S2_CardKind + S2_CardKindInfo | 8,458 |
| 카드 카테고리 | bar_shop1 | S2_CardKindInfo + S2_CardKind + S2_Card | 16종 |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/products/digital | MC시리즈 디지털 상품 목록 |
| GET | /api/v1/products/digital/:productId | MC시리즈 디지털 상품 상세 |
| GET | /api/v1/products/physical | 실물 카드 상품 목록 |
| GET | /api/v1/products/physical/:cardSeq | 실물 카드 상품 상세 |
| GET | /api/v1/products/categories | 카드 카테고리 목록 |

## 클라이언트 페이지

| 파일 | 경로 | 설명 |
|------|------|------|
| DigitalProductsPage.tsx | /products/digital | MC시리즈 디지털 상품 |
| PhysicalProductsPage.tsx | /products/physical | 실물 카드 상품 목록 |
| CardCategoriesPage.tsx | /products/categories | 카드 카테고리 |

## 성능 고려사항

- TB_Product: PK(Product_ID) 클러스터드 인덱스 활용, 소규모 테이블
- S2_Card(8,458건): PK(Card_Seq) 클러스터드 인덱스 활용, Card_Code 접두어 매칭
- S2_CardKind: M:N 관계 테이블, Card_Seq 기반 조인
- 모든 조회에 WITH (NOLOCK) 적용
- 페이지네이션: OFFSET/FETCH NEXT 방식
- 브랜드 18종(CardBrand), 카테고리 6종(Card_Div), 카드 종류 16종(S2_CardKindInfo) 코드 매핑

## 스키마 주의사항

- S2_Card.Company_Seq → 존재하지 않음
- S2_Card.isDisplay → 실제 컬럼명 DISPLAY_YORN (char(1))
- S2_Card.Card_Code는 varchar(30)
- S2_CardKind는 M:N 관계 (Card_Seq ↔ CardKind_Seq)

## 파일 구조

```
server/src/modules/products/
  products.types.ts    - 타입 정의
  products.queries.ts  - DB 쿼리 함수
  products.controller.ts - Express 핸들러
  products.routes.ts   - 라우터 설정

client/src/api/
  products.api.ts      - API 클라이언트

client/src/pages/Products/
  DigitalProductsPage.tsx
  PhysicalProductsPage.tsx
  CardCategoriesPage.tsx
```
