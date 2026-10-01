import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getDigitalProducts,
  getDigitalProductDetail,
  getPhysicalProducts,
  getPhysicalProductDetail,
  getCardCategories,
} from './products.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 상품관리 API는 인증 필요
router.use(authenticate);

// GET /api/v1/products/digital - MC시리즈 디지털 상품 목록
router.get('/digital', asyncHandler(getDigitalProducts));

// GET /api/v1/products/digital/:productId - MC시리즈 디지털 상품 상세
router.get('/digital/:productId', asyncHandler(getDigitalProductDetail));

// GET /api/v1/products/physical - 실물 카드 상품 목록
router.get('/physical', asyncHandler(getPhysicalProducts));

// GET /api/v1/products/physical/:cardSeq - 실물 카드 상품 상세
router.get('/physical/:cardSeq', asyncHandler(getPhysicalProductDetail));

// GET /api/v1/products/categories - 카드 카테고리 목록
router.get('/categories', asyncHandler(getCardCategories));

export default router;
