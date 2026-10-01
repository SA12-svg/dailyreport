import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type {
  DigitalProductListParams,
  PhysicalProductListParams,
  CardCategoryParams,
} from './products.types.js';

/** MC시리즈 디지털 상품 목록 조회 (barunson TB_Product - PK 활용) */
export async function fetchDigitalProducts(params: DigitalProductListParams) {
  const pool = await getPool('barunson');

  const countReq = pool.request();
  let countWhere = 'WHERE 1=1';

  if (params.categoryCode) {
    countReq.input('categoryCode', sql.VarChar, params.categoryCode);
    countWhere += ' AND Product_Category_Code = @categoryCode';
  }
  if (params.brandCode) {
    countReq.input('brandCode', sql.VarChar, params.brandCode);
    countWhere += ' AND Product_Brand_Code = @brandCode';
  }
  if (params.displayYN) {
    countReq.input('displayYN', sql.VarChar, params.displayYN);
    countWhere += ' AND Display_YN = @displayYN';
  }
  if (params.keyword) {
    countReq.input('keyword', sql.NVarChar, params.keyword + '%');
    countWhere += ' AND (Product_Name LIKE @keyword OR Product_Code LIKE @keyword)';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM TB_Product WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE 1=1';
  if (params.categoryCode) {
    dataReq.input('categoryCode', sql.VarChar, params.categoryCode);
    dataWhere += ' AND Product_Category_Code = @categoryCode';
  }
  if (params.brandCode) {
    dataReq.input('brandCode', sql.VarChar, params.brandCode);
    dataWhere += ' AND Product_Brand_Code = @brandCode';
  }
  if (params.displayYN) {
    dataReq.input('displayYN', sql.VarChar, params.displayYN);
    dataWhere += ' AND Display_YN = @displayYN';
  }
  if (params.keyword) {
    dataReq.input('keyword', sql.NVarChar, params.keyword + '%');
    dataWhere += ' AND (Product_Name LIKE @keyword OR Product_Code LIKE @keyword)';
  }

  const dataResult = await dataReq.query(`
    SELECT Product_ID, Product_Code, Product_Name,
           Product_Category_Code, Product_Brand_Code,
           Template_ID, Price, Discount_Rate, Discount_Price,
           Display_YN, Regist_DateTime
    FROM TB_Product WITH (NOLOCK)
    ${dataWhere}
    ORDER BY Product_ID DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset,
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** MC시리즈 디지털 상품 상세 조회 (TB_Product + TB_Product_Image) */
export async function fetchDigitalProductDetail(productId: number) {
  const pool = await getPool('barunson');

  const prodReq = pool.request();
  prodReq.input('productId', sql.Int, productId);
  const prodResult = await prodReq.query(`
    SELECT Product_ID, Product_Code, Product_Name,
           Product_Category_Code, Product_Brand_Code,
           Template_ID, Price, Discount_Rate, Discount_Price,
           Display_YN, Regist_DateTime
    FROM TB_Product WITH (NOLOCK)
    WHERE Product_ID = @productId
  `);

  if (prodResult.recordset.length === 0) {
    return null;
  }

  const imgReq = pool.request();
  imgReq.input('productId', sql.Int, productId);
  const imgResult = await imgReq.query(`
    SELECT Image_ID, Image_URL, Image_Type_Code, Sort_Order
    FROM TB_Product_Image WITH (NOLOCK)
    WHERE Product_ID = @productId
    ORDER BY Sort_Order
  `);

  return {
    ...prodResult.recordset[0],
    images: imgResult.recordset,
  };
}

/** 실물 카드 상품 목록 조회 (bar_shop1 S2_Card - PK Card_Seq 활용) */
export async function fetchPhysicalProducts(params: PhysicalProductListParams) {
  const pool = await getPool('barShop1');

  const countReq = pool.request();
  let countWhere = 'WHERE 1=1';

  if (params.cardBrand) {
    countReq.input('cardBrand', sql.Char, params.cardBrand);
    countWhere += ' AND CardBrand = @cardBrand';
  }
  if (params.cardDiv) {
    countReq.input('cardDiv', sql.Char, params.cardDiv);
    countWhere += ' AND Card_Div = @cardDiv';
  }
  if (params.displayYorn) {
    countReq.input('displayYorn', sql.Char, params.displayYorn);
    countWhere += ' AND DISPLAY_YORN = @displayYorn';
  }
  if (params.keyword) {
    countReq.input('keyword', sql.VarChar, params.keyword + '%');
    countWhere += ' AND (Card_Name LIKE @keyword OR Card_Code LIKE @keyword)';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM S2_Card WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE 1=1';
  if (params.cardBrand) {
    dataReq.input('cardBrand', sql.Char, params.cardBrand);
    dataWhere += ' AND CardBrand = @cardBrand';
  }
  if (params.cardDiv) {
    dataReq.input('cardDiv', sql.Char, params.cardDiv);
    dataWhere += ' AND Card_Div = @cardDiv';
  }
  if (params.displayYorn) {
    dataReq.input('displayYorn', sql.Char, params.displayYorn);
    dataWhere += ' AND DISPLAY_YORN = @displayYorn';
  }
  if (params.keyword) {
    dataReq.input('keyword', sql.VarChar, params.keyword + '%');
    dataWhere += ' AND (Card_Name LIKE @keyword OR Card_Code LIKE @keyword)';
  }

  const dataResult = await dataReq.query(`
    SELECT Card_Seq, CardBrand, Card_Code, Card_Div, Card_Name,
           Card_Price, CardSet_Price, DISPLAY_YORN,
           Unit_Min, Unit_Max, Card_ERPCode, Cost_Price, RegDate
    FROM S2_Card WITH (NOLOCK)
    ${dataWhere}
    ORDER BY Card_Seq DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset,
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** 실물 카드 상품 상세 조회 (S2_Card + S2_CardKind + S2_CardKindInfo) */
export async function fetchPhysicalProductDetail(cardSeq: number) {
  const pool = await getPool('barShop1');

  const cardReq = pool.request();
  cardReq.input('cardSeq', sql.Int, cardSeq);
  const cardResult = await cardReq.query(`
    SELECT Card_Seq, CardBrand, Card_Code, Card_Div, Card_Name,
           Card_Price, CardSet_Price, DISPLAY_YORN,
           Unit_Min, Unit_Max, Card_ERPCode, Cost_Price, RegDate
    FROM S2_Card WITH (NOLOCK)
    WHERE Card_Seq = @cardSeq
  `);

  if (cardResult.recordset.length === 0) {
    return null;
  }

  const kindReq = pool.request();
  kindReq.input('cardSeq', sql.Int, cardSeq);
  const kindResult = await kindReq.query(`
    SELECT ki.CardKind_Seq, ki.CardKind AS CardKind_Name
    FROM S2_CardKind ck WITH (NOLOCK)
    INNER JOIN S2_CardKindInfo ki WITH (NOLOCK) ON ck.CardKind_Seq = ki.CardKind_Seq
    WHERE ck.Card_Seq = @cardSeq
    ORDER BY ki.CardKind_Seq
  `);

  return {
    ...cardResult.recordset[0],
    kinds: kindResult.recordset,
  };
}

/** 카드 카테고리 목록 조회 (S2_CardKindInfo + 카드 수 집계) */
export async function fetchCardCategories(params: CardCategoryParams) {
  const pool = await getPool('barShop1');

  const req = pool.request();
  let where = '';
  if (params.cardDiv) {
    req.input('cardDiv', sql.Char, params.cardDiv);
    where = `WHERE c.Card_Div = @cardDiv`;
  }

  const result = await req.query(`
    SELECT ki.CardKind_Seq, ki.CardKind AS CardKind_Name,
           COUNT(DISTINCT ck.Card_Seq) AS card_count
    FROM S2_CardKindInfo ki WITH (NOLOCK)
    INNER JOIN S2_CardKind ck WITH (NOLOCK) ON ki.CardKind_Seq = ck.CardKind_Seq
    INNER JOIN S2_Card c WITH (NOLOCK) ON ck.Card_Seq = c.Card_Seq
    ${where}
    GROUP BY ki.CardKind_Seq, ki.CardKind
    ORDER BY ki.CardKind_Seq
  `);

  return { data: result.recordset };
}
