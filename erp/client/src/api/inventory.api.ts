import apiClient from './client';

export interface StockParams {
  whCode?: string;
  invStatus?: string;
  itemCode?: string;
  page?: number;
  pageSize?: number;
}

export interface InoutListParams {
  dateFrom: string;
  dateTo: string;
  inoutGubun?: string;
  whCode?: string;
  page?: number;
  pageSize?: number;
}

export interface ValuationParams {
  invMonth: string;
  invStatus?: string;
  page?: number;
  pageSize?: number;
}

export interface RequisitionListParams {
  dateFrom: string;
  dateTo: string;
  reqStatus?: string;
  page?: number;
  pageSize?: number;
}

// --- Types ---

export interface ClosingRow {
  ModuleGubun: string;
  CloseMonth: string;
  CloseTime: string;
}

export interface EvaluationRow {
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

export interface InoutHeaderRow {
  InoutNo: string;
  InoutGubun: string;
  InoutDate: string;
  SysCase: string;
  CaseCode: string;
  InoutPlace: string;
  C_JumunNo: string;
  InoutDescr: string;
}

export interface InoutItemRow {
  InoutSerNo: number;
  WhCode: string;
  ItemCode: string;
  ItemName: string;
  ItemSpec: string;
  InvStatus: string;
  InoutQty: number;
  InoutPrice: number;
  InoutAmnt: number;
  UnitCode: string;
}

export interface InventoryRow {
  WhCode: string;
  InvStatus: string;
  ItemCode: string;
  OhQty: number;
  OhAmnt: number;
}

export interface MonthlyTrendRow {
  InvMonth: string;
  itemCount: number;
  totalQty: number;
  totalAmnt: number;
}

export interface RequisitionRow {
  ReqNo: string;
  ReqDate: string;
  ExpectDate: string;
  ReqStatus: string;
  ReqDept: string;
  ReqEmp: string;
  itemCount: number;
  ReqDescr: string;
}

// --- Constants ---

export const WH_CODE_MAP: Record<string, string> = {
  WH01: '본사창고',
  WH02: '공장창고',
  WH03: '외부창고',
  WH04: '불량창고',
};

export const REQ_STATUS_MAP: Record<string, string> = {
  A: '진행중',
  B: '보류',
  C: '완료',
};

const INOUT_GUBUN_MAP: Record<string, string> = {
  IN: '입고',
  OUT: '출고',
  RET: '반품',
  ADJ: '조정',
};

export function getWhCodeLabel(code: string): string {
  return WH_CODE_MAP[code?.trim()] || code?.trim() || '';
}

export function getInoutGubunLabel(code: string): string {
  return INOUT_GUBUN_MAP[code?.trim()] || code?.trim() || '';
}

// --- Standalone fetch functions ---

export async function fetchClosing(): Promise<ClosingRow[]> {
  const res = await apiClient.get('/inventory/month-close');
  return res.data;
}

export async function fetchEvaluation(params: {
  invMonth: string;
  invStatus?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: EvaluationRow[]; pagination: { page: number; pageSize: number; total: number } }> {
  const res = await apiClient.get('/inventory/valuation', { params });
  return res.data;
}

export async function fetchInoutDetail(
  inoutNo: string,
  inoutGubun?: string,
): Promise<{ header: InoutHeaderRow & { CurrCode?: string; DocNo?: string; OriginNo?: string }; items: InoutItemRow[] }> {
  const res = await apiClient.get(`/inventory/inout/${inoutNo}`, { params: { inoutGubun } });
  return res.data;
}

export async function fetchCurrentInventory(params: {
  whCode?: string;
  invStatus?: string;
  itemCode?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: InventoryRow[]; pagination: { page: number; pageSize: number; total: number }; summary?: Record<string, number> }> {
  const res = await apiClient.get('/inventory/stock', { params });
  return res.data;
}

export async function fetchMonthlyTrend(params: {
  startMonth: string;
  endMonth: string;
  invStatus?: string;
}): Promise<MonthlyTrendRow[]> {
  const res = await apiClient.get('/inventory/monthly-trend', { params });
  return res.data;
}

export async function fetchRequisitions(params: {
  reqStatus?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: RequisitionRow[]; pagination: { page: number; pageSize: number; total: number }; badges?: Record<string, number> }> {
  const res = await apiClient.get('/inventory/requisitions', { params });
  return res.data;
}

export const inventoryApi = {
  // 현재재고
  getStock(params: StockParams) {
    return apiClient.get('/inventory/stock', { params }).then((r) => r.data);
  },

  // 입출고내역 목록
  getInoutList(params: InoutListParams) {
    return apiClient.get('/inventory/inout', { params }).then((r) => r.data);
  },

  // 입출고 상세
  getInoutDetail(inoutNo: string, inoutGubun: string) {
    return apiClient.get(`/inventory/inout/${inoutNo}`, { params: { inoutGubun } }).then((r) => r.data);
  },

  // 재고평가
  getValuation(params: ValuationParams) {
    return apiClient.get('/inventory/valuation', { params }).then((r) => r.data);
  },

  // 청구요청 목록
  getRequisitions(params: RequisitionListParams) {
    return apiClient.get('/inventory/requisitions', { params }).then((r) => r.data);
  },

  // 청구요청 상세
  getRequisitionDetail(reqNo: string) {
    return apiClient.get(`/inventory/requisitions/${reqNo}`).then((r) => r.data);
  },

  // 월마감 이력
  getMonthClose() {
    return apiClient.get('/inventory/month-close').then((r) => r.data);
  },

  // 창고 목록
  getWarehouses() {
    return apiClient.get('/inventory/warehouses').then((r) => r.data);
  },
};
