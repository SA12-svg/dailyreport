// 청구서 헤더 (rpBillHeader)
export interface BillHeader {
  BillNo: string;
  ArApGubun: string;
  BillDate: string;
  CsCode: string;
  TaxCode: string;
  CurrCode: string;
  BillAmnt: number;
  VatAmnt: number;
  MoneySumAmnt: number;
  DeptCode: string;
  EmpCode: string;
  BillDescr: string;
  InvoiceNo: string;
  C_JumunNo: string;
}

// 청구서 상세 항목 (rpBillItem)
export interface BillItem {
  BillSerNo: number;
  ItemCode: string;
  ItemName: string;
  ItemSpec: string;
  ItemQty: number;
  UnitCode: string;
  ItemPrice: number;
  ItemAmnt: number;
  ItemVatAmnt: number;
  ItemGubun: string;
}

// 청구서 상세 (헤더 + 항목)
export interface BillDetail extends BillHeader {
  items: BillItem[];
  totalItemAmnt: number;
  totalVatAmnt: number;
}

// 채권연령분석 항목
export interface AgingEntry {
  CsCode: string;
  Current: number;
  Days30: number;
  Days60: number;
  Days90: number;
  Days120: number;
  Over120: number;
  Total: number;
}

// 수금현황 항목
export interface CollectionEntry {
  AllocDate: string;
  OriginNo: string;
  CsCode: string;
  PayCode: string;
  AllocAmnt: number;
  C_JumunNo: string;
}

// 미수금 상세 항목
export interface OutstandingEntry {
  OriginNo: string;
  CsCode: string;
  ExpectDate: string;
  ExpectAmnt: number;
  ExpectRemainAmnt: number;
  ArApAcc: string;
  C_JumunNo: string;
}

// 청구 목록 쿼리 파라미터
export interface BillListParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  csCode?: string;
  page: number;
  pageSize: number;
}

// 채권연령분석 쿼리 파라미터
export interface AgingParams {
  baseDate: string;
  csCode?: string;
  page: number;
  pageSize: number;
}

// 수금현황 쿼리 파라미터
export interface CollectionParams {
  dateFrom: string;
  dateTo: string;
  csCode?: string;
  payCode?: string;
  page: number;
  pageSize: number;
}

// 미수금 상세 쿼리 파라미터
export interface OutstandingParams {
  csCode?: string;
  page: number;
  pageSize: number;
}
