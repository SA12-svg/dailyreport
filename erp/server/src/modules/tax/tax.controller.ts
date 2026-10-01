import { Request, Response } from 'express';
import {
  fetchTaxInvoiceList,
  fetchTaxInvoiceDetail,
  fetchVatReturn,
  fetchEInvoices,
  fetchSummaryTable,
  fetchTaxCustomers,
} from './tax.queries.js';

/** GET /invoices - 세금계산서 목록 */
export async function getTaxInvoiceList(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, arApGubun, taxCode, csCode, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchTaxInvoiceList({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    arApGubun: arApGubun as string | undefined,
    taxCode: taxCode as string | undefined,
    csCode: csCode as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /invoices/:billNo - 세금계산서 상세 */
export async function getTaxInvoiceDetail(req: Request, res: Response): Promise<void> {
  const { billNo } = req.params;
  const { arApGubun } = req.query;

  if (!arApGubun) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: 'AR/AP 구분(arApGubun)은 필수입니다.' } });
    return;
  }

  const data = await fetchTaxInvoiceDetail(billNo, arApGubun as string);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '세금계산서를 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /vat-return - 부가세 신고 자동집계 */
export async function getVatReturn(req: Request, res: Response): Promise<void> {
  const { year, quarter, arApGubun } = req.query;

  if (!year || !quarter) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '연도(year)와 분기(quarter)는 필수입니다.' } });
    return;
  }

  const data = await fetchVatReturn({
    year: year as string,
    quarter: quarter as string,
    arApGubun: arApGubun as string | undefined,
  });

  res.json(data);
}

/** GET /e-invoices - 전자세금계산서 현황 */
export async function getEInvoices(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, arApGubun, csCode, hasInvoiceNo, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchEInvoices({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    arApGubun: arApGubun as string | undefined,
    csCode: csCode as string | undefined,
    hasInvoiceNo: hasInvoiceNo as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /summary-table - 합계표 */
export async function getSummaryTable(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, arApGubun, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchSummaryTable({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    arApGubun: arApGubun as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /customers - 거래처 목록 (필터용) */
export async function getTaxCustomers(_req: Request, res: Response): Promise<void> {
  const data = await fetchTaxCustomers();
  res.json(data);
}
