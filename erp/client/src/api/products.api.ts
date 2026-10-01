import apiClient from './client';

export interface DigitalProductListParams {
  categoryCode?: string;
  brandCode?: string;
  displayYN?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
}

export interface PhysicalProductListParams {
  cardBrand?: string;
  cardDiv?: string;
  displayYorn?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
}

export interface CardCategoryParams {
  cardDiv?: string;
}

export interface CardKindInfo {
  CardKind_Seq: number;
  CardKind_Name: string;
  card_count: number;
  cardCount?: number;
}

// --- Types ---

export interface PhysicalProduct {
  Card_Seq: number;
  CardBrand: string;
  Card_Code: string;
  Card_Div: string;
  Card_Name: string;
  CardSet_Price: number;
  Card_Price: number;
  Unit_Min: number;
  Unit_Max: number;
  DISPLAY_YORN: string;
  FPRINT_YORN: string;
}

export interface PhysicalProductDetail {
  Card_Code: string;
  Card_ERPCode: string;
  CardBrand: string;
  Card_Div: string;
  Card_Name: string;
  CardSet_Price: number;
  Card_Price: number;
  SamplePrice: number;
  Unit_Min: number;
  Unit_Max: number;
  DISPLAY_YORN: string;
  FPRINT_YORN: string;
  Video_URL?: string;
  RelatedCards?: string;
  Explain?: string;
  categories?: Array<{ CardKind_Seq: number; CardKind_Name: string }>;
}

// --- Constants ---

export const BRAND_MAP: Record<string, string> = {
  BS: '바른손',
  BK: '바른손카드',
  MC: 'MC시리즈',
  PR: '프리미엄',
};

export const CARD_DIV_MAP: Record<string, string> = {
  '01': '청첩장',
  '02': '감사장',
  '03': '돌잔치',
  '04': '연하장',
  '05': '기타',
};

export function getBrandLabel(code: string): string {
  return BRAND_MAP[code?.trim()] || code?.trim() || '';
}

export function getCardDivLabel(code: string): string {
  return CARD_DIV_MAP[code?.trim()] || code?.trim() || '';
}

export const productsApi = {
  // MC시리즈 디지털 상품 목록
  getDigitalProducts(params: DigitalProductListParams) {
    return apiClient.get('/products/digital', { params }).then((r) => r.data);
  },

  // MC시리즈 디지털 상품 상세
  getDigitalProductDetail(productId: number) {
    return apiClient.get(`/products/digital/${productId}`).then((r) => r.data);
  },

  // 실물 카드 상품 목록
  getPhysicalProducts(params: PhysicalProductListParams) {
    return apiClient.get('/products/physical', { params }).then((r) => r.data);
  },

  // 실물 카드 상품 상세
  getPhysicalProductDetail(cardCode: string | number) {
    return apiClient.get(`/products/physical/${cardCode}`).then((r) => r.data);
  },

  // 카드 카테고리 목록
  getCardCategories(params?: CardCategoryParams) {
    return apiClient.get('/products/categories', { params }).then((r) => r.data);
  },

  // getCategories alias
  getCategories(params?: CardCategoryParams) {
    return this.getCardCategories(params);
  },
};
