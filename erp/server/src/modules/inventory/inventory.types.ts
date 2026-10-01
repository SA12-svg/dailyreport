// 현재재고 항목
export interface StockEntry {
  WhCode: string;
  InvStatus: string;
  ItemCode: string;
  OhQty: number;
  OhAmnt: number;
}

// 입출고 헤더
export interface InoutHeader {
  InoutNo: string;
  InoutGubun: string;
  InoutDate: string;
  SysCase: string;
  CaseCode: string;
  InoutPlace: string;
  InoutDescr: string;
  C_JumunNo: string;
}

// 입출고 상세 항목
export interface InoutItem {
  InoutSerNo: number;
  WhCode: string;
  ItemCode: string;
  ItemName: string;
  ItemSpec: string;
  InvStatus: string;
  InoutQty: number;
  UnitCode: string;
  InoutPrice: number;
  InoutAmnt: number;
  LotNo: string;
}

// 입출고 상세 (헤더 + 항목)
export interface InoutDetail extends InoutHeader {
  items: InoutItem[];
  totalQty: number;
  totalAmnt: number;
}

// 재고평가 항목
export interface ValuationEntry {
  ItemCode: string;
  InvStatus: string;
  SQty: number;
  SAmnt: number;
  InQty: number;
  InAmnt: number;
  StdPrice: number;
  OhQty: number;
  OhAmnt: number;
}

// 청구요청 헤더
export interface RequisitionHeader {
  ReqNo: string;
  SysCase: string;
  CaseCode: string;
  ReqDate: string;
  ExpectDate: string;
  ReqDept: string;
  ReqEmp: string;
  ReqStatus: string;
  ReqDescr: string;
}

// 청구요청 상세 항목
export interface RequisitionItem {
  ReqSerNo: number;
  WhCode: string;
  WhCodeIn: string;
  ItemCode: string;
  ReqQty: number;
  OutQty: number;
  ReqItemStatus: string;
}

// 청구요청 상세 (헤더 + 항목)
export interface RequisitionDetail extends RequisitionHeader {
  items: RequisitionItem[];
  totalReqQty: number;
  totalOutQty: number;
}

// 월마감 항목
export interface MonthCloseEntry {
  ModuleGubun: string;
  CloseMonth: string;
  CloseTime: string;
}

// 현재재고 쿼리 파라미터
export interface StockParams {
  whCode?: string;
  invStatus?: string;
  itemCode?: string;
  page: number;
  pageSize: number;
}

// 입출고내역 쿼리 파라미터
export interface InoutListParams {
  dateFrom: string;
  dateTo: string;
  inoutGubun?: string;
  whCode?: string;
  page: number;
  pageSize: number;
}

// 재고평가 쿼리 파라미터
export interface ValuationParams {
  invMonth: string;
  invStatus?: string;
  page: number;
  pageSize: number;
}

// 월별 추이 쿼리 파라미터
export interface MonthlyTrendParams {
  startMonth: string;
  endMonth: string;
  invStatus?: string;
}

// 청구요청 쿼리 파라미터
export interface RequisitionListParams {
  dateFrom: string;
  dateTo: string;
  reqStatus?: string;
  page: number;
  pageSize: number;
}
