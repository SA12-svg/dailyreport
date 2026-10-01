import { Request, Response } from 'express';
import {
  fetchDigitalOrders,
  fetchDigitalOrderDetail,
  fetchPhysicalOrders,
  fetchPhysicalOrderDetail,
  fetchPrintJobs,
  fetchPrintJobSummary,
  fetchOrderSearch,
  fetchPaidOrders,
} from './orders.queries.js';

/** GET /digital - 디지털 주문 목록 */
export async function getDigitalOrders(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, orderStatusCode, paymentStatusCode, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchDigitalOrders({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    orderStatusCode: orderStatusCode as string | undefined,
    paymentStatusCode: paymentStatusCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /digital/:orderId - 디지털 주문 상세 */
export async function getDigitalOrderDetail(req: Request, res: Response): Promise<void> {
  const orderId = parseInt(req.params.orderId, 10);

  if (isNaN(orderId)) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '유효한 주문 ID가 필요합니다.' } });
    return;
  }

  const data = await fetchDigitalOrderDetail(orderId);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '주문을 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /physical - 실물 주문 목록 */
export async function getPhysicalOrders(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, statusSeq, orderType, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchPhysicalOrders({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    statusSeq: statusSeq ? parseInt(statusSeq as string, 10) : undefined,
    orderType: orderType as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /physical/:orderSeq - 실물 주문 상세 */
export async function getPhysicalOrderDetail(req: Request, res: Response): Promise<void> {
  const orderSeq = parseInt(req.params.orderSeq, 10);

  if (isNaN(orderSeq)) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '유효한 주문 순번이 필요합니다.' } });
    return;
  }

  const data = await fetchPhysicalOrderDetail(orderSeq);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '주문을 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /printjobs - 인쇄작업 현황 */
export async function getPrintJobs(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, ptype, page = '1', pageSize = '20', view } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  if (view === 'summary') {
    const data = await fetchPrintJobSummary(dateFrom as string, dateTo as string);
    res.json({ data });
    return;
  }

  const data = await fetchPrintJobs({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    ptype: ptype as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /paid - 유료 주문 목록 */
export async function getPaidOrders(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, paymentStatusCode, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchPaidOrders({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    paymentStatusCode: paymentStatusCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /search - 통합 주문 검색 */
export async function searchOrders(req: Request, res: Response): Promise<void> {
  const { keyword, source, dateFrom, dateTo, page = '1', pageSize = '20' } = req.query;

  if (!keyword || (keyword as string).trim().length === 0) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '검색 키워드는 필수입니다.' } });
    return;
  }

  const data = await fetchOrderSearch({
    keyword: keyword as string,
    source: (source as 'digital' | 'physical' | 'all') || 'all',
    dateFrom: dateFrom as string | undefined,
    dateTo: dateTo as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}
