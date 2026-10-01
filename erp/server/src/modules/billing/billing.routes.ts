import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getBillList,
  getBillDetail,
  getAging,
  getCollections,
  getOutstanding,
  getCustomers,
} from './billing.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 매출매입 API는 인증 필요
router.use(authenticate);

// GET /api/v1/billing/bills - AR/AP 청구 목록
router.get('/bills', asyncHandler(getBillList));

// GET /api/v1/billing/bills/:billNo - 청구 상세
router.get('/bills/:billNo', asyncHandler(getBillDetail));

// GET /api/v1/billing/aging - 채권연령분석
router.get('/aging', asyncHandler(getAging));

// GET /api/v1/billing/collections - 수금현황
router.get('/collections', asyncHandler(getCollections));

// GET /api/v1/billing/outstanding - 미수금 상세
router.get('/outstanding', asyncHandler(getOutstanding));

// GET /api/v1/billing/customers - 거래처 목록
router.get('/customers', asyncHandler(getCustomers));

export default router;
