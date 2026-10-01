import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type {
  DigitalOrderListParams,
  PhysicalOrderListParams,
  PrintJobParams,
  OrderSearchParams,
  PaidOrderListParams,
} from './orders.types.js';

/** PII 마스킹 유틸리티 */
function maskName(name: string | null): string {
  if (!name) return '';
  const trimmed = name.trim();
  if (trimmed.length <= 1) return '*';
  if (trimmed.length === 2) return trimmed[0] + '*';
  return trimmed[0] + '*'.repeat(trimmed.length - 2) + trimmed[trimmed.length - 1];
}

function maskEmail(email: string | null): string {
  if (!email) return '';
  const trimmed = email.trim();
  const atIdx = trimmed.indexOf('@');
  if (atIdx <= 0) return '****@****.com';
  const prefix = trimmed.substring(0, Math.min(3, atIdx));
  return prefix + '****@****.com';
}

function maskPhone(phone: string | null): string {
  if (!phone) return '';
  const trimmed = phone.trim().replace(/[^0-9-]/g, '');
  const parts = trimmed.split('-');
  if (parts.length === 3) {
    return parts[0] + '-****-' + parts[2];
  }
  if (trimmed.length >= 8) {
    return trimmed.substring(0, 3) + '-****-' + trimmed.substring(trimmed.length - 4);
  }
  return '***-****-****';
}

function applyDigitalMask(row: any): any {
  return {
    ...row,
    Name: maskName(row.Name),
    Email: maskEmail(row.Email),
    CellPhone_Number: maskPhone(row.CellPhone_Number),
  };
}

function applyPhysicalMask(row: any): any {
  return {
    ...row,
    order_name: maskName(row.order_name),
    order_email: maskEmail(row.order_email),
    order_phone: maskPhone(row.order_phone),
    order_hphone: maskPhone(row.order_hphone),
  };
}

/** 디지털 주문 목록 조회 (barunson TB_Order - IX_TB_Order_Order_DateTime 활용) */
export async function fetchDigitalOrders(params: DigitalOrderListParams) {
  const pool = await getPool('barunson');

  const countReq = pool.request();
  countReq.input('dateFrom', sql.VarChar, params.dateFrom + ' 00:00:00');
  countReq.input('dateTo', sql.VarChar, params.dateTo + ' 23:59:59');

  let countWhere = 'WHERE Order_DateTime BETWEEN @dateFrom AND @dateTo';
  if (params.orderStatusCode) {
    countReq.input('orderStatusCode', sql.VarChar, params.orderStatusCode);
    countWhere += ' AND Order_Status_Code = @orderStatusCode';
  }
  if (params.paymentStatusCode) {
    countReq.input('paymentStatusCode', sql.VarChar, params.paymentStatusCode);
    countWhere += ' AND Payment_Status_Code = @paymentStatusCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM TB_Order WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom + ' 00:00:00');
  dataReq.input('dateTo', sql.VarChar, params.dateTo + ' 23:59:59');
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE Order_DateTime BETWEEN @dateFrom AND @dateTo';
  if (params.orderStatusCode) {
    dataReq.input('orderStatusCode', sql.VarChar, params.orderStatusCode);
    dataWhere += ' AND Order_Status_Code = @orderStatusCode';
  }
  if (params.paymentStatusCode) {
    dataReq.input('paymentStatusCode', sql.VarChar, params.paymentStatusCode);
    dataWhere += ' AND Payment_Status_Code = @paymentStatusCode';
  }

  const dataResult = await dataReq.query(`
    SELECT Order_ID, Order_Code, Name, Email, CellPhone_Number,
           Order_Price, Payment_Price, Payment_Method_Code, Payment_Status_Code,
           Payment_DateTime, Order_Status_Code, Order_Path,
           Order_DateTime, Regist_DateTime
    FROM TB_Order WITH (NOLOCK)
    ${dataWhere}
    ORDER BY Order_DateTime DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset.map(applyDigitalMask),
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** 디지털 주문 상세 조회 (TB_Order + TB_Order_Product) */
export async function fetchDigitalOrderDetail(orderId: number) {
  const pool = await getPool('barunson');

  const headerReq = pool.request();
  headerReq.input('orderId', sql.Int, orderId);
  const headerResult = await headerReq.query(`
    SELECT Order_ID, Order_Code, Name, Email, CellPhone_Number,
           Order_Price, Payment_Price, Payment_Method_Code, Payment_Status_Code,
           Payment_DateTime, Order_Status_Code, Order_Path,
           Order_DateTime, Regist_DateTime, MemberId, User_ID
    FROM TB_Order WITH (NOLOCK)
    WHERE Order_ID = @orderId
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  const prodReq = pool.request();
  prodReq.input('orderId', sql.Int, orderId);
  const prodResult = await prodReq.query(`
    SELECT Product_ID, Product_Type_Code,
           Item_Count, Item_Price, Total_Price
    FROM TB_Order_Product WITH (NOLOCK)
    WHERE Order_ID = @orderId
  `);

  const header = applyDigitalMask(headerResult.recordset[0]);
  return {
    ...header,
    products: prodResult.recordset,
  };
}

/** 실물 주문 목록 조회 (bar_shop1 custom_order - status_seq >= 1 유효 주문) */
export async function fetchPhysicalOrders(params: PhysicalOrderListParams) {
  const pool = await getPool('barShop1');

  const countReq = pool.request();
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = `WHERE order_date BETWEEN @dateFrom AND @dateTo + ' 23:59:59'
    AND status_seq >= 1`;
  if (params.statusSeq != null) {
    countReq.input('statusSeq', sql.Int, params.statusSeq);
    countWhere += ' AND status_seq = @statusSeq';
  }
  if (params.orderType) {
    countReq.input('orderType', sql.VarChar, params.orderType);
    countWhere += ' AND order_type = @orderType';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM custom_order WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = `WHERE order_date BETWEEN @dateFrom AND @dateTo + ' 23:59:59'
    AND status_seq >= 1`;
  if (params.statusSeq != null) {
    dataReq.input('statusSeq', sql.Int, params.statusSeq);
    dataWhere += ' AND status_seq = @statusSeq';
  }
  if (params.orderType) {
    dataReq.input('orderType', sql.VarChar, params.orderType);
    dataWhere += ' AND order_type = @orderType';
  }

  const dataResult = await dataReq.query(`
    SELECT order_seq, order_type, sales_Gubun, site_gubun, pay_Type,
           print_type, status_seq, order_name, order_email, order_phone, order_hphone,
           last_total_price, settle_price, order_date, src_send_date
    FROM custom_order WITH (NOLOCK)
    ${dataWhere}
    ORDER BY order_seq DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset.map(applyPhysicalMask),
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** 실물 주문 상세 조회 (custom_order + custom_order_item) */
export async function fetchPhysicalOrderDetail(orderSeq: number) {
  const pool = await getPool('barShop1');

  const headerReq = pool.request();
  headerReq.input('orderSeq', sql.Int, orderSeq);
  const headerResult = await headerReq.query(`
    SELECT order_seq, order_type, sales_Gubun, site_gubun, pay_Type,
           print_type, status_seq, order_name, order_email, order_phone, order_hphone,
           last_total_price, settle_price, order_date, src_send_date
    FROM custom_order WITH (NOLOCK)
    WHERE order_seq = @orderSeq
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  const itemReq = pool.request();
  itemReq.input('orderSeq', sql.Int, orderSeq);
  const itemResult = await itemReq.query(`
    SELECT id, card_seq, item_type, item_count, item_price,
           item_sale_price, discount_rate
    FROM custom_order_item WITH (NOLOCK)
    WHERE order_seq = @orderSeq
    ORDER BY id
  `);

  const items = itemResult.recordset;
  const totalItemCount = items.reduce((s: number, i: any) => s + (i.item_count || 0), 0);
  const totalItemPrice = items.reduce((s: number, i: any) => s + (i.item_price || 0) * (i.item_count || 0), 0);

  const header = applyPhysicalMask(headerResult.recordset[0]);
  return {
    ...header,
    items,
    totalItemCount,
    totalItemPrice,
  };
}

/** 인쇄작업 현황 조회 (pdate 범위 축소 → PK 순 정렬) */
export async function fetchPrintJobs(params: PrintJobParams) {
  const pool = await getPool('barShop1');

  const countReq = pool.request();
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = 'WHERE pj.pdate BETWEEN @dateFrom AND @dateTo';
  if (params.ptype) {
    countReq.input('ptype', sql.Char, params.ptype);
    countWhere += ' AND pj.ptype = @ptype';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM custom_order_printjob pj WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE pj.pdate BETWEEN @dateFrom AND @dateTo';
  if (params.ptype) {
    dataReq.input('ptype', sql.Char, params.ptype);
    dataWhere += ' AND pj.ptype = @ptype';
  }

  const dataResult = await dataReq.query(`
    SELECT pj.pdate, pj.cdate, pj.cseq, pj.pid, pj.pcount, pj.ptype,
           pj.printer_id, c.Card_Code AS card_code, c.Card_Name AS card_name
    FROM custom_order_printjob pj WITH (NOLOCK)
    INNER JOIN custom_order_plist pl WITH (NOLOCK) ON pj.pid = pl.id
    INNER JOIN S2_Card c WITH (NOLOCK) ON pl.card_seq = c.Card_Seq
    ${dataWhere}
    ORDER BY pj.pdate DESC, pj.cdate DESC, pj.cseq DESC, pj.pid DESC
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

/** 인쇄작업 일별 요약 조회 */
export async function fetchPrintJobSummary(dateFrom: string, dateTo: string) {
  const pool = await getPool('barShop1');

  const req = pool.request();
  req.input('dateFrom', sql.VarChar, dateFrom);
  req.input('dateTo', sql.VarChar, dateTo);

  const result = await req.query(`
    SELECT pdate,
           COUNT(*) AS total_jobs,
           SUM(pcount) AS total_quantity,
           SUM(CASE WHEN ptype = 'C' THEN 1 ELSE 0 END) AS card_types,
           SUM(CASE WHEN ptype = 'E' THEN 1 ELSE 0 END) AS envelope_types
    FROM custom_order_printjob WITH (NOLOCK)
    WHERE pdate BETWEEN @dateFrom AND @dateTo
    GROUP BY pdate
    ORDER BY pdate DESC
  `);

  return result.recordset;
}

/** 유료 주문 목록 조회 (barunson TB_Order - Payment_Price > 0, IX_TB_Order_Payment_DateTime 활용) */
export async function fetchPaidOrders(params: PaidOrderListParams) {
  const pool = await getPool('barunson');

  const countReq = pool.request();
  countReq.input('dateFrom', sql.VarChar, params.dateFrom + ' 00:00:00');
  countReq.input('dateTo', sql.VarChar, params.dateTo + ' 23:59:59');

  let countWhere = 'WHERE Payment_DateTime BETWEEN @dateFrom AND @dateTo AND Payment_Price > 0';
  if (params.paymentStatusCode) {
    countReq.input('paymentStatusCode', sql.VarChar, params.paymentStatusCode);
    countWhere += ' AND Payment_Status_Code = @paymentStatusCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM TB_Order WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom + ' 00:00:00');
  dataReq.input('dateTo', sql.VarChar, params.dateTo + ' 23:59:59');
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE Payment_DateTime BETWEEN @dateFrom AND @dateTo AND Payment_Price > 0';
  if (params.paymentStatusCode) {
    dataReq.input('paymentStatusCode', sql.VarChar, params.paymentStatusCode);
    dataWhere += ' AND Payment_Status_Code = @paymentStatusCode';
  }

  const dataResult = await dataReq.query(`
    SELECT Order_ID, Order_Code, Name, Email, CellPhone_Number,
           Order_Price, Payment_Price, Payment_Method_Code, Payment_Status_Code,
           Payment_DateTime, Order_Status_Code, Order_Path, Order_DateTime
    FROM TB_Order WITH (NOLOCK)
    ${dataWhere}
    ORDER BY Payment_DateTime DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset.map(applyDigitalMask),
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** 통합 주문 검색 (키워드로 주문코드/주문번호 검색) */
export async function fetchOrderSearch(params: OrderSearchParams) {
  const results: any[] = [];
  const keyword = params.keyword.trim();

  if (params.source === 'all' || params.source === 'digital' || !params.source) {
    const pool = await getPool('barunson');
    const req = pool.request();
    req.input('keyword', sql.VarChar, keyword + '%');
    req.input('pageSize', sql.Int, params.pageSize);

    let where = `WHERE (Order_Code LIKE @keyword OR CAST(Order_ID AS VARCHAR) LIKE @keyword)`;
    if (params.dateFrom) {
      req.input('dateFrom', sql.VarChar, params.dateFrom + ' 00:00:00');
      where += ' AND Order_DateTime >= @dateFrom';
    }
    if (params.dateTo) {
      req.input('dateTo', sql.VarChar, params.dateTo + ' 23:59:59');
      where += ' AND Order_DateTime <= @dateTo';
    }

    const digitalResult = await req.query(`
      SELECT TOP (@pageSize)
        'digital' AS source,
        CAST(Order_ID AS VARCHAR) AS order_id,
        CONVERT(VARCHAR, Order_DateTime, 23) AS order_date,
        Name AS customer_name,
        Payment_Price AS amount,
        Order_Status_Code AS status
      FROM TB_Order WITH (NOLOCK)
      ${where}
      ORDER BY Order_DateTime DESC
    `);

    results.push(...digitalResult.recordset.map((r: any) => ({
      ...r,
      customer_name: maskName(r.customer_name),
    })));
  }

  if (params.source === 'all' || params.source === 'physical' || !params.source) {
    const pool = await getPool('barShop1');
    const req = pool.request();
    req.input('keyword', sql.VarChar, keyword + '%');
    req.input('pageSize', sql.Int, params.pageSize);

    let where = `WHERE (CAST(order_seq AS VARCHAR) LIKE @keyword) AND status_seq >= 1`;
    if (params.dateFrom) {
      req.input('dateFrom', sql.VarChar, params.dateFrom);
      where += ' AND order_date >= @dateFrom';
    }
    if (params.dateTo) {
      req.input('dateTo', sql.VarChar, params.dateTo + ' 23:59:59');
      where += ' AND order_date <= @dateTo';
    }

    const physicalResult = await req.query(`
      SELECT TOP (@pageSize)
        'physical' AS source,
        CAST(order_seq AS VARCHAR) AS order_id,
        CONVERT(VARCHAR, order_date, 23) AS order_date,
        order_name AS customer_name,
        settle_price AS amount,
        CAST(status_seq AS VARCHAR) AS status
      FROM custom_order WITH (NOLOCK)
      ${where}
      ORDER BY order_seq DESC
    `);

    results.push(...physicalResult.recordset.map((r: any) => ({
      ...r,
      customer_name: maskName(r.customer_name),
    })));
  }

  return {
    data: results.slice(0, params.pageSize),
    total: results.length,
  };
}
