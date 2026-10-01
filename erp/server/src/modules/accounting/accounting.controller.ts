import { Request, Response } from 'express';
import {
  fetchVoucherList,
  fetchVoucherDetail,
  fetchLedger,
  fetchTrialBalance,
  fetchBalanceSheet,
  fetchIncomeStatement,
  fetchCashFlow,
  fetchCumulative,
  fetchAccountList,
} from './accounting.queries.js';

/** GET /vouchers - 전표 목록 */
export async function getVouchers(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo, docType, status, page = '1', pageSize = '20' } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchVoucherList({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
    docType: docType as string | undefined,
    status: status as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /vouchers/:docNo - 전표 상세 */
export async function getVoucherDetail(req: Request, res: Response): Promise<void> {
  const docNo = req.params.docNo as string;
  const data = await fetchVoucherDetail(docNo);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '전표를 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /ledger - 총계정원장 */
export async function getLedger(req: Request, res: Response): Promise<void> {
  const { accCode, dateFrom, dateTo } = req.query;

  if (!accCode || !dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '계정코드(accCode)와 조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchLedger({
    accCode: accCode as string,
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
  });

  res.json(data);
}

/** GET /trial-balance - 시산표 */
export async function getTrialBalance(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchTrialBalance({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
  });

  // 차대 합계
  const totalDebit = data.reduce((s: number, e: any) => s + e.Debit, 0);
  const totalCredit = data.reduce((s: number, e: any) => s + e.Credit, 0);

  res.json({
    data,
    summary: { totalDebit, totalCredit, isBalanced: totalDebit === totalCredit },
  });
}

/** GET /balance-sheet - 재무상태표 */
export async function getBalanceSheet(req: Request, res: Response): Promise<void> {
  const { dateTo } = req.query;

  if (!dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '기준일(dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchBalanceSheet({
    dateFrom: '00000000',
    dateTo: dateTo as string,
  });

  res.json(data);
}

/** GET /income-statement - 손익계산서 */
export async function getIncomeStatement(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchIncomeStatement({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
  });

  res.json(data);
}

/** GET /cash-flow - 현금흐름표 */
export async function getCashFlow(req: Request, res: Response): Promise<void> {
  const { dateFrom, dateTo } = req.query;

  if (!dateFrom || !dateTo) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '조회 기간(dateFrom, dateTo)은 필수입니다.' } });
    return;
  }

  const data = await fetchCashFlow({
    dateFrom: dateFrom as string,
    dateTo: dateTo as string,
  });

  res.json(data);
}

/** GET /cumulative - 누계 조회 */
export async function getCumulative(req: Request, res: Response): Promise<void> {
  const { year, cumType = 'account' } = req.query;

  if (!year) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '회계연도(year)는 필수입니다.' } });
    return;
  }

  const data = await fetchCumulative({
    year: year as string,
    cumType: cumType as 'account' | 'dept' | 'cs',
  });

  res.json(data);
}

/** GET /accounts - 계정과목 목록 */
export async function getAccounts(_req: Request, res: Response): Promise<void> {
  const data = await fetchAccountList();
  res.json(data);
}
