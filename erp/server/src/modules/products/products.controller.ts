import { Request, Response } from 'express';
import {
  fetchDigitalProducts,
  fetchDigitalProductDetail,
  fetchPhysicalProducts,
  fetchPhysicalProductDetail,
  fetchCardCategories,
} from './products.queries.js';

/** GET /digital - MC시리즈 디지털 상품 목록 */
export async function getDigitalProducts(req: Request, res: Response): Promise<void> {
  const { categoryCode, brandCode, displayYN, keyword, page = '1', pageSize = '20' } = req.query;

  const data = await fetchDigitalProducts({
    categoryCode: categoryCode as string | undefined,
    brandCode: brandCode as string | undefined,
    displayYN: displayYN as string | undefined,
    keyword: keyword as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /digital/:productId - MC시리즈 디지털 상품 상세 */
export async function getDigitalProductDetail(req: Request, res: Response): Promise<void> {
  const productId = parseInt(req.params.productId, 10);

  if (isNaN(productId)) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '유효한 상품 ID가 필요합니다.' } });
    return;
  }

  const data = await fetchDigitalProductDetail(productId);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '상품을 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /physical - 실물 카드 상품 목록 */
export async function getPhysicalProducts(req: Request, res: Response): Promise<void> {
  const { cardBrand, cardDiv, displayYorn, keyword, page = '1', pageSize = '20' } = req.query;

  const data = await fetchPhysicalProducts({
    cardBrand: cardBrand as string | undefined,
    cardDiv: cardDiv as string | undefined,
    displayYorn: displayYorn as string | undefined,
    keyword: keyword as string | undefined,
    page: parseInt(page as string, 10),
    pageSize: parseInt(pageSize as string, 10),
  });

  res.json(data);
}

/** GET /physical/:cardSeq - 실물 카드 상품 상세 */
export async function getPhysicalProductDetail(req: Request, res: Response): Promise<void> {
  const cardSeq = parseInt(req.params.cardSeq, 10);

  if (isNaN(cardSeq)) {
    res.status(400).json({ error: { code: 'INVALID_PARAMS', message: '유효한 카드 순번이 필요합니다.' } });
    return;
  }

  const data = await fetchPhysicalProductDetail(cardSeq);

  if (!data) {
    res.status(404).json({ error: { code: 'NOT_FOUND', message: '카드 상품을 찾을 수 없습니다.' } });
    return;
  }

  res.json(data);
}

/** GET /categories - 카드 카테고리 목록 */
export async function getCardCategories(req: Request, res: Response): Promise<void> {
  const { cardDiv } = req.query;

  const data = await fetchCardCategories({
    cardDiv: cardDiv as string | undefined,
  });

  res.json(data);
}
