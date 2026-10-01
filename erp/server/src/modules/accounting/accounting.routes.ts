import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getVouchers,
  getVoucherDetail,
  getLedger,
  getTrialBalance,
  getBalanceSheet,
  getIncomeStatement,
  getCashFlow,
  getCumulative,
  getAccounts,
} from './accounting.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 회계 API는 인증 필요
router.use(authenticate);

// GET /api/v1/accounting/vouchers - 전표 목록
router.get('/vouchers', asyncHandler(getVouchers));

// GET /api/v1/accounting/vouchers/:docNo - 전표 상세
router.get('/vouchers/:docNo', asyncHandler(getVoucherDetail));

// GET /api/v1/accounting/ledger - 총계정원장
router.get('/ledger', asyncHandler(getLedger));

// GET /api/v1/accounting/trial-balance - 시산표
router.get('/trial-balance', asyncHandler(getTrialBalance));

// GET /api/v1/accounting/balance-sheet - 재무상태표
router.get('/balance-sheet', asyncHandler(getBalanceSheet));

// GET /api/v1/accounting/income-statement - 손익계산서
router.get('/income-statement', asyncHandler(getIncomeStatement));

// GET /api/v1/accounting/cash-flow - 현금흐름표
router.get('/cash-flow', asyncHandler(getCashFlow));

// GET /api/v1/accounting/cumulative - 누계 조회
router.get('/cumulative', asyncHandler(getCumulative));

// GET /api/v1/accounting/accounts - 계정과목 목록
router.get('/accounts', asyncHandler(getAccounts));

export default router;
