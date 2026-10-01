// 배송 정보 (bar_shop1 DELIVERY_INFO)
export interface DeliveryInfo {
  ORDER_SEQ: number;
  DELIVERY_SEQ: number;
  NAME: string;           // PII 마스킹 적용
  PHONE: string;          // PII 마스킹 적용
  HPHONE: string;         // PII 마스킹 적용
  ADDR: string;           // PII 마스킹 적용
  ADDR_DETAIL: string;    // PII 마스킹 적용
  EMAIL: string;          // PII 마스킹 적용
  DELIVERY_DATE: string;
  DELIVERY_SEQ_NAME: string;
  ZIPCODE: string;
}

// 배송 상세 항목 (DELIVERY_INFO_DETAIL)
export interface DeliveryInfoDetail {
  delivery_id: number;
  item_type: string;
  item_title: string;
  item_count: number;
}

// 배송 추적 (DELIVERY_INFO_DELCODE)
export interface DeliveryTracking {
  delivery_id: number;
  delivery_code_num: string;
  delivery_com: string;
  reg_date: string;
}

// 배송 상세 응답 (마스터 + 상세 + 송장)
export interface DeliveryDetail extends DeliveryInfo {
  details: DeliveryInfoDetail[];
  trackings: DeliveryTracking[];
}

// 배송 목록 쿼리 파라미터
export interface DeliveryListParams {
  dateFrom: string;
  dateTo: string;
  orderSeq?: number;
  keyword?: string;
  page: number;
  pageSize: number;
}

// 송장번호 검색 파라미터
export interface TrackingSearchParams {
  trackingNo: string;
  deliveryCom?: string;
  page: number;
  pageSize: number;
}
