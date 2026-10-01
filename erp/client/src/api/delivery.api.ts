import apiClient from './client';

export interface DeliveryListParams {
  dateFrom: string;
  dateTo: string;
  orderSeq?: number;
  keyword?: string;
  page?: number;
  pageSize?: number;
}

export interface TrackingSearchParams {
  trackingNo: string;
  deliveryCom?: string;
  page?: number;
  pageSize?: number;
}

export const deliveryApi = {
  // 배송 목록
  getDeliveryList(params: DeliveryListParams) {
    return apiClient.get('/delivery/list', { params }).then((r) => r.data);
  },

  // 배송 상세
  getDeliveryDetail(orderSeq: number, deliverySeq: number) {
    return apiClient.get(`/delivery/detail/${orderSeq}/${deliverySeq}`).then((r) => r.data);
  },

  // 송장번호 검색
  searchTracking(params: TrackingSearchParams) {
    return apiClient.get('/delivery/tracking', { params }).then((r) => r.data);
  },
};
