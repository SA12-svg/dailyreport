import apiClient from './client';

export interface VoucherListParams {
  dateFrom: string;
  dateTo: string;
  docType?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export const accountingApi = {
  // 전표 목록
  getVouchers(params: VoucherListParams) {
    return apiClient.get('/accounting/vouchers', { params }).then((r) => r.data);
  },

  // 전표 상세
  getVoucherDetail(docNo: string) {
    return apiClient.get(`/accounting/vouchers/${docNo}`).then((r) => r.data);
  },

  // 총계정원장
  getLedger(params: { accCode: string; dateFrom: string; dateTo: string }) {
    return apiClient.get('/accounting/ledger', { params }).then((r) => r.data);
  },

  // 시산표
  getTrialBalance(params: { dateFrom: string; dateTo: string }) {
    return apiClient.get('/accounting/trial-balance', { params }).then((r) => r.data);
  },

  // 재무상태표
  getBalanceSheet(params: { dateTo: string }) {
    return apiClient.get('/accounting/balance-sheet', { params }).then((r) => r.data);
  },

  // 손익계산서
  getIncomeStatement(params: { dateFrom: string; dateTo: string }) {
    return apiClient.get('/accounting/income-statement', { params }).then((r) => r.data);
  },

  // 현금흐름표
  getCashFlow(params: { dateFrom: string; dateTo: string }) {
    return apiClient.get('/accounting/cash-flow', { params }).then((r) => r.data);
  },

  // 누계 조회
  getCumulative(params: { year: string; cumType?: string }) {
    return apiClient.get('/accounting/cumulative', { params }).then((r) => r.data);
  },

  // 계정과목 목록
  getAccounts() {
    return apiClient.get('/accounting/accounts').then((r) => r.data);
  },
};
