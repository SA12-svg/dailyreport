import apiClient from './client';

export interface BillListParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  csCode?: string;
  page?: number;
  pageSize?: number;
}

export interface AgingParams {
  baseDate: string;
  csCode?: string;
  page?: number;
  pageSize?: number;
}

export interface CollectionParams {
  dateFrom: string;
  dateTo: string;
  csCode?: string;
  payCode?: string;
  page?: number;
  pageSize?: number;
}

export interface OutstandingParams {
  csCode?: string;
  page?: number;
  pageSize?: number;
}

// --- Types ---

export interface BillHeaderRow {
  BillNo: string;
  BillDate: string;
  CsCode: string;
  SysCase: string;
  TaxCode: string;
  BillAmnt: number;
  VatAmnt: number;
  MoneySumAmnt: number;
  InvoiceNo: string;
  BillDescr: string;
}

export interface CollectionRow {
  OriginNo: string;
  CsCode: string;
  ExpectAmnt: number;
  AllocatedAmnt: number;
  RemainAmnt: number;
  ExpectDate: string;
  collectionRate: number;
}

export interface CollectionSummary {
  totalExpect: number;
  totalCollected: number;
  totalRemain: number;
  overallRate: number;
}

export interface ReceivableRow {
  OriginNo: string;
  OriginSerNo: number;
  CsCode: string;
  ExpectAmnt: number;
  ExpectRemainAmnt: number;
  ExpectDate: string;
  ExpectPayCode: string;
  overdueDays: number;
}

// --- Constants ---

export const TAX_CODE_MAP: Record<string, string> = {
  '01': '과세',
  '02': '영세',
  '03': '면세',
  '04': '비과세',
};

const SYS_CASE_MAP: Record<string, string> = {
  '01': '일반',
  '02': '반품',
  '03': '할인',
  '04': '기타',
};

export function getTaxCodeLabel(code: string): string {
  return TAX_CODE_MAP[code?.trim()] || code?.trim() || '';
}

export function getSysCaseLabel(code: string): string {
  return SYS_CASE_MAP[code?.trim()] || code?.trim() || '';
}

// --- Standalone fetch functions ---

export async function fetchApList(params: {
  startDate: string;
  endDate: string;
  csCode?: string;
  taxCode?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: BillHeaderRow[]; pagination: { page: number; pageSize: number; total: number }; summary?: Record<string, number> }> {
  const res = await apiClient.get('/billing/bills', {
    params: { dateFrom: params.startDate, dateTo: params.endDate, arApGubun: 'AP', csCode: params.csCode, taxCode: params.taxCode, page: params.page, pageSize: params.pageSize },
  });
  return res.data;
}

export async function fetchArList(params: {
  startDate: string;
  endDate: string;
  csCode?: string;
  taxCode?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: BillHeaderRow[]; pagination: { page: number; pageSize: number; total: number }; summary?: Record<string, number> }> {
  const res = await apiClient.get('/billing/bills', {
    params: { dateFrom: params.startDate, dateTo: params.endDate, arApGubun: 'AR', csCode: params.csCode, taxCode: params.taxCode, page: params.page, pageSize: params.pageSize },
  });
  return res.data;
}

export async function fetchCollection(params: {
  startDate: string;
  endDate: string;
  csCode?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: CollectionRow[]; pagination: { page: number; pageSize: number; total: number }; summary: CollectionSummary }> {
  const res = await apiClient.get('/billing/collections', {
    params: { dateFrom: params.startDate, dateTo: params.endDate, csCode: params.csCode, page: params.page, pageSize: params.pageSize },
  });
  return res.data;
}

export async function fetchReceivables(params: {
  csCode?: string;
  page: number;
  pageSize: number;
}): Promise<{ data: ReceivableRow[]; pagination: { page: number; pageSize: number; total: number }; summary?: Record<string, number> }> {
  const res = await apiClient.get('/billing/outstanding', {
    params: { csCode: params.csCode, page: params.page, pageSize: params.pageSize },
  });
  return res.data;
}

export const billingApi = {
  // AR/AP 청구 목록
  getBills(params: BillListParams) {
    return apiClient.get('/billing/bills', { params }).then((r) => r.data);
  },

  // 청구 상세
  getBillDetail(billNo: string, arApGubun: string) {
    return apiClient.get(`/billing/bills/${billNo}`, { params: { arApGubun } }).then((r) => r.data);
  },

  // 채권연령분석
  getAging(params: AgingParams) {
    return apiClient.get('/billing/aging', { params }).then((r) => r.data);
  },

  // 수금현황
  getCollections(params: CollectionParams) {
    return apiClient.get('/billing/collections', { params }).then((r) => r.data);
  },

  // 미수금 상세
  getOutstanding(params: OutstandingParams) {
    return apiClient.get('/billing/outstanding', { params }).then((r) => r.data);
  },

  // 거래처 목록
  getCustomers() {
    return apiClient.get('/billing/customers').then((r) => r.data);
  },
};
