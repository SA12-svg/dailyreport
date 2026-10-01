import { Request, Response } from 'express';
import {
  fetchStock,
  fetchInoutList,
  fetchInoutDetail,
  fetchValuation,
  fetchRequisitionList,
  fetchRequisitionDetail,
  fetchMonthClose,
  fetchWarehouses,
  fetchMonthlyTrend,
} from './inventory.queries.js';

/** GET /stock - 현재재고 */
export async function getStock(req: Request, res: Response): Promise<void> {
  const { whCode, invStatus, itemCode, page = '1', pageSize = '20' } = req.query;

  const data = await fetchStock({
    whCode: whCode as string | undefined,
    invStatus: invStatus as string | undefined,
    itemCode: itemCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /inout - 입출고내역 목록 */
export async function getInoutList(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, inoutGubun, whCode, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchInoutList({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    inoutGubun: inoutGubun as string | undefined,
    whCode: whCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /inout/:inoutNo - 입출고 상세 */
export async function getInoutDetail(req: Request, res: Response): Promise<void> {
  const { inoutNo } = req.params;
  const { inoutGubun } = req.query;

  if (!inoutGubun) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '입출고 구분(inoutGubun)은 필수입니다.' } });
    return;
  }

  const data = await fetchInoutDetail(inoutNo, inoutGubun as string);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '입출고 전표를 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /valuation - 재고평가 */
export async function getValuation(req: Request, res: Response): Promise<void> {
  const { invMonth, invStatus, page = '1', pageSize = '20' } = req.query;

  if (!invMonth) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '평가 월(invMonth)은 필수입니다.' } });
    return;
  }

  const data = await fetchValuation({
    invMonth: invMonth as string,
    invStatus: invStatus as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /requisitions - 청구요청 목록 */
export async function getRequisitions(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, reqStatus, page = '1', pageSize = '20' } = req.query;

  // dateFrom/dateTo가 없으면 최근 6개월 기본값 사용
  const now = new Date();
  const defaultDateTo = now.toISOString().slice(0, 10).replace(/-/g, '');
  const sixMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
  const defaultDateFrom = sixMonthsAgo.toISOString().slice(0, 10).replace(/-/g, '');

  const data = await fetchRequisitionList({
    dateFrom: (dateFrom as string) || defaultDateFrom,
    dateTo: (dateTo as string) || defaultDateTo,
    reqStatus: reqStatus as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /requisitions/:reqNo - 청구요청 상세 */
export async function getRequisitionDetail(req: Request, res: Response): Promise<void> {
  const { reqNo } = req.params;
  const data = await fetchRequisitionDetail(reqNo);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '청구요청을 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /monthly-trend - 월별 재고 추이 */
export async function getMonthlyTrend(req: Request, res: Response): Promise<void> {
  const { startMonth, endMonth, invStatus } = req.query;

  if (!startMonth || !endMonth) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(startMonth, endMonth)은 필수입니다.' } });
    return;
  }

  const data = await fetchMonthlyTrend({
    startMonth: startMonth as string,
    endMonth: endMonth as string,
    invStatus: invStatus as string | undefined,
  });

  res.json(data);
}

/** GET /month-close - 월마감 이력 */
export async function getMonthClose(_req: Request, res: Response): Promise<void> {
  const data = await fetchMonthClose();
  res.json(data);
}

/** GET /warehouses - 창고 목록 */
export async function getWarehouses(_req: Request, res: Response): Promise<void> {
  const data = await fetchWarehouses();
  res.json(data);
}
