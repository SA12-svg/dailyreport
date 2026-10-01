// MC시리즈 디지털 상품 (barunson TB_Product)
export interface DigitalProduct {
  Product_ID: number;
  Product_Code: string;
  Product_Name: string;
  Product_Category_Code: string;
  Product_Brand_Code: string;
  Template_ID: number;
  Price: number;
  Discount_Rate: number;
  Discount_Price: number;
  Display_YN: string;
  Regist_DateTime: string;
}

// 디지털 상품 상세 (TB_Product + TB_Product_Image)
export interface DigitalProductDetail extends DigitalProduct {
  images: ProductImage[];
}

// 상품 이미지 (TB_Product_Image)
export interface ProductImage {
  Image_ID: number;
  Image_URL: string;
  Image_Type_Code: string;
  Sort_Order: number;
}

// 실물 카드 상품 (bar_shop1 S2_Card)
export interface PhysicalProduct {
  Card_Seq: number;
  CardBrand: string;
  Card_Code: string;
  Card_Div: string;
  Card_Name: string;
  Card_Price: number;
  CardSet_Price: number;
  DISPLAY_YORN: string;
  Unit_Min: number;
  Unit_Max: number;
  Card_ERPCode: string;
  Cost_Price: number;
  RegDate: string;
}

// 실물 카드 상세 (S2_Card + S2_CardKind + S2_CardKindInfo)
export interface PhysicalProductDetail extends PhysicalProduct {
  kinds: CardKindInfo[];
}

// 카드 종류 정보 (S2_CardKindInfo)
export interface CardKindInfo {
  CardKind_Seq: number;
  CardKind_Name: string;
}

// 카드 카테고리 (S2_CardKindInfo)
export interface CardCategory {
  CardKind_Seq: number;
  CardKind_Name: string;
  card_count: number;
}

// 디지털 상품 목록 쿼리 파라미터
export interface DigitalProductListParams {
  categoryCode?: string;
  brandCode?: string;
  displayYN?: string;
  keyword?: string;
  page: number;
  pageSize: number;
}

// 실물 카드 목록 쿼리 파라미터
export interface PhysicalProductListParams {
  cardBrand?: string;
  cardDiv?: string;
  displayYorn?: string;
  keyword?: string;
  page: number;
  pageSize: number;
}

// 카드 카테고리 목록 쿼리 파라미터
export interface CardCategoryParams {
  cardDiv?: string;
}
