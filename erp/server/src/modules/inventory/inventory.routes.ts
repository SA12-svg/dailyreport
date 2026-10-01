import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getStock,
  getInoutList,
  getInoutDetail,
  getValuation,
  getRequisitions,
  getRequisitionDetail,
  getMonthClose,
  getWarehouses,
  getMonthlyTrend,
} from './inventory.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 재고관리 API는 인증 필요
router.use(authenticate);

// GET /api/v1/inventory/stock - 현재재고
router.get('/stock', asyncHandler(getStock));

// GET /api/v1/inventory/inout - 입출고내역 목록
router.get('/inout', asyncHandler(getInoutList));

// GET /api/v1/inventory/inout/:inoutNo - 입출고 상세
router.get('/inout/:inoutNo', asyncHandler(getInoutDetail));

// GET /api/v1/inventory/valuation - 재고평가
router.get('/valuation', asyncHandler(getValuation));

// GET /api/v1/inventory/requisitions - 청구요청 목록
router.get('/requisitions', asyncHandler(getRequisitions));

// GET /api/v1/inventory/requisitions/:reqNo - 청구요청 상세
router.get('/requisitions/:reqNo', asyncHandler(getRequisitionDetail));

// GET /api/v1/inventory/monthly-trend - 월별 재고 추이
router.get('/monthly-trend', asyncHandler(getMonthlyTrend));

// GET /api/v1/inventory/month-close - 월마감 이력
router.get('/month-close', asyncHandler(getMonthClose));

// GET /api/v1/inventory/warehouses - 창고 목록
router.get('/warehouses', asyncHandler(getWarehouses));

export default router;
