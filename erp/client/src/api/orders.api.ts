import apiClient from './client';

export interface DigitalOrderListParams {
  dateFrom: string;
  dateTo: string;
  orderStatusCode?: string;
  paymentStatusCode?: string;
  page?: number;
  pageSize?: number;
}

export interface PhysicalOrderListParams {
  dateFrom: string;
  dateTo: string;
  statusSeq?: number;
  orderType?: string;
  page?: number;
  pageSize?: number;
}

export interface PrintJobParams {
  dateFrom: string;
  dateTo: string;
  ptype?: string;
  view?: 'detail' | 'summary';
  page?: number;
  pageSize?: number;
}

export interface PaidOrderListParams {
  dateFrom: string;
  dateTo: string;
  paymentStatusCode?: string;
  page?: number;
  pageSize?: number;
}

export interface OrderSearchParams {
  keyword: string;
  source?: 'digital' | 'physical' | 'all';
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export const ordersApi = {
  // 디지털 주문 목록
  getDigitalOrders(params: DigitalOrderListParams) {
    return apiClient.get('/orders/digital', { params }).then((r) => r.data);
  },

  // 디지털 주문 상세
  getDigitalOrderDetail(orderId: number) {
    return apiClient.get(`/orders/digital/${orderId}`).then((r) => r.data);
  },

  // 실물 주문 목록
  getPhysicalOrders(params: PhysicalOrderListParams) {
    return apiClient.get('/orders/physical', { params }).then((r) => r.data);
  },

  // 실물 주문 상세
  getPhysicalOrderDetail(orderSeq: number) {
    return apiClient.get(`/orders/physical/${orderSeq}`).then((r) => r.data);
  },

  // 인쇄작업 현황
  getPrintJobs(params: PrintJobParams) {
    return apiClient.get('/orders/printjobs', { params }).then((r) => r.data);
  },

  // 유료 주문 목록
  getPaidOrders(params: PaidOrderListParams) {
    return apiClient.get('/orders/paid', { params }).then((r) => r.data);
  },

  // 통합 주문 검색
  searchOrders(params: OrderSearchParams) {
    return apiClient.get('/orders/search', { params }).then((r) => r.data);
  },
};
