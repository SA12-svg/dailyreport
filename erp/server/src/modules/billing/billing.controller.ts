import { Request, Response } from 'express';
import {
  fetchBillList,
  fetchBillDetail,
  fetchAging,
  fetchCollections,
  fetchOutstanding,
  fetchCustomers,
} from './billing.queries.js';

/** GET /bills - AR/AP 청구 목록 */
export async function getBillList(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, arApGubun, csCode, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchBillList({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    arApGubun: arApGubun as string | undefined,
    csCode: csCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /bills/:billNo - 청구 상세 */
export async function getBillDetail(req: Request, res: Response): Promise<void> {
  const { billNo } = req.params;
  const { arApGubun } = req.query;

  if (!arApGubun) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: 'AR/AP 구분(arApGubun)은 필수입니다.' } });
    return;
  }

  const data = await fetchBillDetail(billNo, arApGubun as string);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '청구서를 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /aging - 채권연령분석 */
export async function getAging(req: Request, res: Response): Promise<void> {
  const { baseDate, csCode, page = '1', pageSize = '20' } = req.query;

  if (!baseDate) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '기준일(baseDate)은 필수입니다.' } });
    return;
  }

  const data = await fetchAging({
    baseDate: baseDate as string,
    csCode: csCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /collections - 수금현황 */
export async function getCollections(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, csCode, payCode, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchCollections({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    csCode: csCode as string | undefined,
    payCode: payCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /outstanding - 미수금 상세 */
export async function getOutstanding(req: Request, res: Response): Promise<void> {
  const { csCode, page = '1', pageSize = '20' } = req.query;

  const data = await fetchOutstanding({
    csCode: csCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /customers - 거래처 목록 */
export async function getCustomers(_req: Request, res: Response): Promise<void> {
  const data = await fetchCustomers();
  res.json(data);
}
