import { Router } from 'express';
import { authenticate } from '../../middleware/auth.js';
import {
  getTaxInvoiceList,
  getTaxInvoiceDetail,
  getVatReturn,
  getEInvoices,
  getSummaryTable,
  getTaxCustomers,
} from './tax.controller.js';

const router = Router();

function asyncHandler(fn: Function) {
  return (req: any, res: any, next: any) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 모든 세무관리 API는 인증 필요
router.use(authenticate);

// GET /api/v1/tax/invoices - 세금계산서 목록
router.get('/invoices', asyncHandler(getTaxInvoiceList));

// GET /api/v1/tax/invoices/:billNo - 세금계산서 상세
router.get('/invoices/:billNo', asyncHandler(getTaxInvoiceDetail));

// GET /api/v1/tax/vat-return - 부가세 신고 자동집계
router.get('/vat-return', asyncHandler(getVatReturn));

// GET /api/v1/tax/e-invoices - 전자세금계산서 현황
router.get('/e-invoices', asyncHandler(getEInvoices));

// GET /api/v1/tax/summary-table - 합계표
router.get('/summary-table', asyncHandler(getSummaryTable));

// GET /api/v1/tax/customers - 거래처 목록 (필터용)
router.get('/customers', asyncHandler(getTaxCustomers));

export default router;
