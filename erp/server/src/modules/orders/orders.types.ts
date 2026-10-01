// 디지털 주문 (barunson TB_Order)
export interface DigitalOrder {
  Order_ID: number;
  Order_Code: string;
  Name: string;          // PII 마스킹 적용
  Email: string;         // PII 마스킹 적용
  CellPhone_Number: string; // PII 마스킹 적용
  Order_Price: number;
  Payment_Price: number;
  Payment_Method_Code: string;
  Payment_Status_Code: string;
  Payment_DateTime: string;
  Order_Status_Code: string;
  Order_Path: string;
  Order_DateTime: string;
  Regist_DateTime: string;
}

// 디지털 주문 상세 (주문 + 상품)
export interface DigitalOrderDetail extends DigitalOrder {
  MemberId: string;
  User_ID: string;
  products: DigitalOrderProduct[];
}

// 디지털 주문 상품 (TB_Order_Product)
export interface DigitalOrderProduct {
  Product_ID: number;
  Product_Type_Code: string;
  Item_Count: number;
  Item_Price: number;
  Total_Price: number;
}

// 실물 주문 (bar_shop1 custom_order)
export interface PhysicalOrder {
  order_seq: number;
  order_type: string;
  sales_Gubun: string;
  site_gubun: string;
  pay_Type: string;
  print_type: string;
  status_seq: number;
  order_name: string;      // PII 마스킹 적용
  order_email: string;     // PII 마스킹 적용
  order_phone: string;     // PII 마스킹 적용
  order_hphone: string;    // PII 마스킹 적용
  last_total_price: number;
  settle_price: number;
  order_date: string;
  src_send_date: string;
}

// 실물 주문 상세 (주문 + 항목)
export interface PhysicalOrderDetail extends PhysicalOrder {
  items: PhysicalOrderItem[];
  totalItemCount: number;
  totalItemPrice: number;
}

// 실물 주문 항목 (custom_order_item)
export interface PhysicalOrderItem {
  id: number;
  card_seq: number;
  item_type: string;
  item_count: number;
  item_price: number;
  item_sale_price: number;
  discount_rate: number;
}

// 인쇄작업 현황 (custom_order_printjob)
export interface PrintJobEntry {
  pdate: string;
  cdate: string;
  cseq: number;
  pid: number;
  pcount: number;
  ptype: string;
  printer_id: string;
  card_code: string;
  card_name: string;
}

// 인쇄작업 일별 요약
export interface PrintJobSummary {
  pdate: string;
  total_jobs: number;
  total_quantity: number;
  card_types: number;
  envelope_types: number;
}

// 통합 검색 결과
export interface UnifiedSearchResult {
  source: 'digital' | 'physical';
  order_id: string;
  order_date: string;
  customer_name: string;   // PII 마스킹 적용
  amount: number;
  status: string;
}

// 디지털 주문 목록 쿼리 파라미터
export interface DigitalOrderListParams {
  dateFrom: string;
  dateTo: string;
  orderStatusCode?: string;
  paymentStatusCode?: string;
  page: number;
  pageSize: number;
}

// 실물 주문 목록 쿼리 파라미터
export interface PhysicalOrderListParams {
  dateFrom: string;
  dateTo: string;
  statusSeq?: number;
  orderType?: string;
  page: number;
  pageSize: number;
}

// 인쇄작업 쿼리 파라미터
export interface PrintJobParams {
  dateFrom: string;
  dateTo: string;
  ptype?: string;
  page: number;
  pageSize: number;
}

// 유료 주문 (barunson TB_Order, Payment_Price > 0)
export interface PaidOrder {
  Order_ID: number;
  Order_Code: string;
  Name: string;
  Email: string;
  CellPhone_Number: string;
  Order_Price: number;
  Payment_Price: number;
  Payment_Method_Code: string;
  Payment_Status_Code: string;
  Payment_DateTime: string;
  Order_Status_Code: string;
  Order_Path: string;
  Order_DateTime: string;
}

// 유료 주문 목록 쿼리 파라미터
export interface PaidOrderListParams {
  dateFrom: string;
  dateTo: string;
  paymentStatusCode?: string;
  page: number;
  pageSize: number;
}

// 통합 검색 쿼리 파라미터
export interface OrderSearchParams {
  keyword: string;
  source?: 'digital' | 'physical' | 'all';
  dateFrom?: string;
  dateTo?: string;
  page: number;
  pageSize: number;
}
