import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type { DeliveryListParams, TrackingSearchParams } from './delivery.types.js';

/** PII 마스킹 유틸리티 */
function maskName(name: string | null): string {
  if (!name) return '';
  const trimmed = name.trim();
  if (trimmed.length <= 1) return '*';
  if (trimmed.length === 2) return trimmed[0] + '*';
  return trimmed[0] + '*'.repeat(trimmed.length - 2) + trimmed[trimmed.length - 1];
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

function maskAddress(addr: string | null): string {
  if (!addr) return '';
  const trimmed = addr.trim();
  // 시/구까지만 표시
  const match = trimmed.match(/^(.+?[시도])\s*(.+?[구군시])/);
  if (match) {
    return match[1] + ' ' + match[2] + ' ***';
  }
  if (trimmed.length > 6) {
    return trimmed.substring(0, 6) + ' ***';
  }
  return trimmed;
}

function applyDeliveryMask(row: any): any {
  return {
    ...row,
    NAME: maskName(row.NAME),
    PHONE: maskPhone(row.PHONE),
    HPHONE: maskPhone(row.HPHONE),
    ADDR: maskAddress(row.ADDR),
    ADDR_DETAIL: row.ADDR_DETAIL ? '***' : '',
    EMAIL: row.EMAIL ? maskEmail(row.EMAIL) : '',
  };
}

function maskEmail(email: string | null): string {
  if (!email) return '';
  const trimmed = email.trim();
  const atIdx = trimmed.indexOf('@');
  if (atIdx <= 0) return '****@****.com';
  const prefix = trimmed.substring(0, Math.min(3, atIdx));
  return prefix + '****@****.com';
}

/** 배송 목록 조회 (bar_shop1 DELIVERY_INFO) */
export async function fetchDeliveryList(params: DeliveryListParams) {
  const pool = await getPool('barShop1');

  const countReq = pool.request();
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = `WHERE d.DELIVERY_DATE BETWEEN @dateFrom AND @dateTo + ' 23:59:59'`;
  if (params.orderSeq != null) {
    countReq.input('orderSeq', sql.Int, params.orderSeq);
    countWhere += ' AND d.ORDER_SEQ = @orderSeq';
  }
  if (params.keyword) {
    countReq.input('keyword', sql.NVarChar, params.keyword + '%');
    countWhere += ' AND d.NAME LIKE @keyword';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM DELIVERY_INFO d WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = `WHERE d.DELIVERY_DATE BETWEEN @dateFrom AND @dateTo + ' 23:59:59'`;
  if (params.orderSeq != null) {
    dataReq.input('orderSeq', sql.Int, params.orderSeq);
    dataWhere += ' AND d.ORDER_SEQ = @orderSeq';
  }
  if (params.keyword) {
    dataReq.input('keyword', sql.NVarChar, params.keyword + '%');
    dataWhere += ' AND d.NAME LIKE @keyword';
  }

  const dataResult = await dataReq.query(`
    SELECT d.ORDER_SEQ, d.DELIVERY_SEQ, d.NAME, d.PHONE, d.HPHONE,
           d.ADDR, d.ZIPCODE, d.DELIVERY_DATE, d.EMAIL
    FROM DELIVERY_INFO d WITH (NOLOCK)
    ${dataWhere}
    ORDER BY d.DELIVERY_DATE DESC, d.ORDER_SEQ DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset.map(applyDeliveryMask),
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** 배송 상세 조회 (DELIVERY_INFO + DELIVERY_INFO_DETAIL + DELIVERY_INFO_DELCODE) */
export async function fetchDeliveryDetail(orderSeq: number, deliverySeq: number) {
  const pool = await getPool('barShop1');

  // 마스터 정보
  const headerReq = pool.request();
  headerReq.input('orderSeq', sql.Int, orderSeq);
  headerReq.input('deliverySeq', sql.Int, deliverySeq);
  const headerResult = await headerReq.query(`
    SELECT ORDER_SEQ, DELIVERY_SEQ, NAME, PHONE, HPHONE,
           ADDR, ADDR_DETAIL, ZIPCODE, DELIVERY_DATE, EMAIL
    FROM DELIVERY_INFO WITH (NOLOCK)
    WHERE ORDER_SEQ = @orderSeq AND DELIVERY_SEQ = @deliverySeq
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  // 배송 상세 항목
  const detailReq = pool.request();
  detailReq.input('orderSeq', sql.Int, orderSeq);
  detailReq.input('deliverySeq', sql.Int, deliverySeq);
  const detailResult = await detailReq.query(`
    SELECT dd.delivery_id, dd.item_type, dd.item_title, dd.item_count
    FROM DELIVERY_INFO_DETAIL dd WITH (NOLOCK)
    INNER JOIN DELIVERY_INFO d WITH (NOLOCK)
      ON dd.delivery_id = d.DELIVERY_SEQ
    WHERE d.ORDER_SEQ = @orderSeq AND d.DELIVERY_SEQ = @deliverySeq
    ORDER BY dd.delivery_id
  `);

  // 송장 정보
  const trackReq = pool.request();
  trackReq.input('orderSeq', sql.Int, orderSeq);
  trackReq.input('deliverySeq', sql.Int, deliverySeq);
  const trackResult = await trackReq.query(`
    SELECT dc.delivery_id, dc.delivery_code_num, dc.delivery_com, dc.reg_date
    FROM DELIVERY_INFO_DELCODE dc WITH (NOLOCK)
    INNER JOIN DELIVERY_INFO d WITH (NOLOCK)
      ON dc.delivery_id = d.DELIVERY_SEQ
    WHERE d.ORDER_SEQ = @orderSeq AND d.DELIVERY_SEQ = @deliverySeq
    ORDER BY dc.reg_date DESC
  `);

  const header = applyDeliveryMask(headerResult.recordset[0]);
  return {
    ...header,
    details: detailResult.recordset,
    trackings: trackResult.recordset,
  };
}

/** 송장번호 검색 (DELIVERY_INFO_DELCODE → DELIVERY_INFO) */
export async function fetchTrackingSearch(params: TrackingSearchParams) {
  const pool = await getPool('barShop1');

  const countReq = pool.request();
  countReq.input('trackingNo', sql.VarChar, params.trackingNo);

  let countWhere = 'WHERE dc.delivery_code_num = @trackingNo';
  if (params.deliveryCom) {
    countReq.input('deliveryCom', sql.VarChar, params.deliveryCom);
    countWhere += ' AND dc.delivery_com = @deliveryCom';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM DELIVERY_INFO_DELCODE dc WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('trackingNo', sql.VarChar, params.trackingNo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE dc.delivery_code_num = @trackingNo';
  if (params.deliveryCom) {
    dataReq.input('deliveryCom', sql.VarChar, params.deliveryCom);
    dataWhere += ' AND dc.delivery_com = @deliveryCom';
  }

  const dataResult = await dataReq.query(`
    SELECT dc.delivery_id, dc.delivery_code_num, dc.delivery_com, dc.reg_date,
           d.ORDER_SEQ, d.DELIVERY_SEQ, d.NAME, d.PHONE, d.ADDR, d.DELIVERY_DATE
    FROM DELIVERY_INFO_DELCODE dc WITH (NOLOCK)
    INNER JOIN DELIVERY_INFO d WITH (NOLOCK)
      ON dc.delivery_id = d.DELIVERY_SEQ
    ${dataWhere}
    ORDER BY dc.reg_date DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset.map(applyDeliveryMask),
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}
