import apiClient from './client';

export interface TaxInvoiceListParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  taxCode?: string;
  csCode?: string;
  page?: number;
  pageSize?: number;
}

export interface VatReturnParams {
  year: string;
  quarter: string;
  arApGubun?: string;
}

export interface EInvoiceParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  csCode?: string;
  hasInvoiceNo?: string;
  page?: number;
  pageSize?: number;
}

export interface SummaryTableParams {
  dateFrom: string;
  dateTo: string;
  arApGubun?: string;
  page?: number;
  pageSize?: number;
}

export const taxApi = {
  // 세금계산서 목록
  getInvoices(params: TaxInvoiceListParams) {
    return apiClient.get('/tax/invoices', { params }).then((r) => r.data);
  },

  // 세금계산서 상세
  getInvoiceDetail(billNo: string, arApGubun: string) {
    return apiClient.get(`/tax/invoices/${billNo}`, { params: { arApGubun } }).then((r) => r.data);
  },

  // 부가세 신고 자동집계
  getVatReturn(params: VatReturnParams) {
    return apiClient.get('/tax/vat-return', { params }).then((r) => r.data);
  },

  // 전자세금계산서 현황
  getEInvoices(params: EInvoiceParams) {
    return apiClient.get('/tax/e-invoices', { params }).then((r) => r.data);
  },

  // 합계표
  getSummaryTable(params: SummaryTableParams) {
    return apiClient.get('/tax/summary-table', { params }).then((r) => r.data);
  },

  // 거래처 목록 (필터용)
  getCustomers() {
    return apiClient.get('/tax/customers').then((r) => r.data);
  },
};
