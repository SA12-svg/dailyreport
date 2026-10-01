import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getDeliveryList,
  getDeliveryDetail,
  searchTracking,
} from './delivery.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 배송관리 API는 인증 필요
router.use(authenticate);

// GET /api/v1/delivery/list - 배송 목록
router.get('/list', asyncHandler(getDeliveryList));

// GET /api/v1/delivery/detail/:orderSeq/:deliverySeq - 배송 상세
router.get('/detail/:orderSeq/:deliverySeq', asyncHandler(getDeliveryDetail));

// GET /api/v1/delivery/tracking - 송장번호 검색
router.get('/tracking', asyncHandler(searchTracking));

export default router;
