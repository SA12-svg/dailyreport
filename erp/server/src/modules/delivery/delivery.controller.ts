import { Request, Response } from 'express';
import {
  fetchDeliveryList,
  fetchDeliveryDetail,
  fetchTrackingSearch,
} from './delivery.queries.js';

/** GET /list - 배송 목록 */
export async function getDeliveryList(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, orderSeq, keyword, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchDeliveryList({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    orderSeq: orderSeq ? parseInt(orderSeq as string, 10) : undefined,
    keyword: keyword as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /detail/:orderSeq/:deliverySeq - 배송 상세 */
export async function getDeliveryDetail(req: Request, res: Response): Promise<void> {
  const orderSeq = parseInt(req.params.orderSeq, 10);
  const deliverySeq = parseInt(req.params.deliverySeq, 10);

  if (isNaN(orderSeq) || isNaN(deliverySeq)) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '유효한 주문순번과 배송순번이 필요합니다.' } });
    return;
  }

  const data = await fetchDeliveryDetail(orderSeq, deliverySeq);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '배송 정보를 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /tracking - 송장번호 검색 */
export async function searchTracking(req: Request, res: Response): Promise<void> {
  const { trackingNo, deliveryCom, page = '1', pageSize = '20' } = req.query;

  if (!trackingNo || (trackingNo as string).trim().length === 0) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '송장번호는 필수입니다.' } });
    return;
  }

  const data = await fetchTrackingSearch({
    trackingNo: trackingNo as string,
    deliveryCom: deliveryCom as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}
