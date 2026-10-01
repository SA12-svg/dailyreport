import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getDigitalOrders,
  getDigitalOrderDetail,
  getPhysicalOrders,
  getPhysicalOrderDetail,
  getPrintJobs,
  searchOrders,
  getPaidOrders,
} from './orders.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 주문관리 API는 인증 필요
router.use(authenticate);

// GET /api/v1/orders/digital - 디지털 주문 목록
router.get('/digital', asyncHandler(getDigitalOrders));

// GET /api/v1/orders/digital/:orderId - 디지털 주문 상세
router.get('/digital/:orderId', asyncHandler(getDigitalOrderDetail));

// GET /api/v1/orders/physical - 실물 주문 목록
router.get('/physical', asyncHandler(getPhysicalOrders));

// GET /api/v1/orders/physical/:orderSeq - 실물 주문 상세
router.get('/physical/:orderSeq', asyncHandler(getPhysicalOrderDetail));

// GET /api/v1/orders/paid - 유료 주문 목록
router.get('/paid', asyncHandler(getPaidOrders));

// GET /api/v1/orders/printjobs - 인쇄작업 현황
router.get('/printjobs', asyncHandler(getPrintJobs));

// GET /api/v1/orders/search - 통합 주문 검색
router.get('/search', asyncHandler(searchOrders));

export default router;
