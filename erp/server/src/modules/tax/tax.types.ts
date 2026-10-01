// 세금계산서 헤더 (rpBillHeader 기반)
export interface TaxInvoice {
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

// 세금계산서 상세 항목 (rpBillItem)
export interface TaxInvoiceItem {
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

// 세금계산서 상세 (헤더 + 항목)
export interface TaxInvoiceDetail extends TaxInvoice {
  items: TaxInvoiceItem[];
  totalItemAmnt: number;
  totalVatAmnt: number;
}

// 부가세 신고 집계 항목
export interface VatReturnEntry {
  TaxCode: string;
  ArApGubun: string;
  InvoiceCount: number;
  SupplyAmnt: number;
  VatAmnt: number;
  TotalAmnt: number;
}

// 전자세금계산서 현황 항목
export interface EInvoiceEntry {
  BillNo: string;
  ArApGubun: string;
  BillDate: string;
  CsCode: string;
  TaxCode: string;
  BillAmnt: number;
  VatAmnt: number;
  InvoiceNo: string;
  EInvoiceStatus: string;
}

// 합계표 항목 (거래처별 집계)
export interface SummaryTableEntry {
  CsCode: string;
  InvoiceCount: number;
  SupplyAmnt: number;
  VatAmnt: number;
  TotalAmnt: number;
}

// 세금계산서 목록 쿼리 파라미터
export interface TaxInvoiceListParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  taxCode?: string;
  csCode?: string;
  page: number;
  pageSize: number;
}

// 부가세 신고 집계 쿼리 파라미터
export interface VatReturnParams {
  year: string;
  quarter: string;
  arApGubun?: string;
}

// 전자세금계산서 현황 쿼리 파라미터
export interface EInvoiceParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  csCode?: string;
  hasInvoiceNo?: string;
  page: number;
  pageSize: number;
}

// 합계표 쿼리 파라미터
export interface SummaryTableParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  page: number;
  pageSize: number;
}
