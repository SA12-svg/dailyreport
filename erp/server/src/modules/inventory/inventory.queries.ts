import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type {
  StockParams,
  InoutListParams,
  ValuationParams,
  RequisitionListParams,
  MonthlyTrendParams,
} from './inventory.types.js';

const SITE_CODE = 'BK10';

/** 현재재고 조회 (mmInventory PK: SiteCode + WhCode + InvStatus + ItemCode) */
export async function fetchStock(params: StockParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);

  let where = 'WHERE SiteCode = @siteCode AND OhQty > 0';
  if (params.whCode) {
    countReq.input('whCode', sql.VarChar, params.whCode);
    where += ' AND WhCode = @whCode';
  }
  if (params.invStatus) {
    countReq.input('invStatus', sql.VarChar, params.invStatus);
    where += ' AND InvStatus = @invStatus';
  }
  if (params.itemCode) {
    countReq.input('itemCode', sql.VarChar, params.itemCode + '%');
    where += ' AND ItemCode LIKE @itemCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM mmInventory WITH (NOLOCK)
    ${where}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE SiteCode = @siteCode AND OhQty > 0';
  if (params.whCode) {
    dataReq.input('whCode', sql.VarChar, params.whCode);
    dataWhere += ' AND WhCode = @whCode';
  }
  if (params.invStatus) {
    dataReq.input('invStatus', sql.VarChar, params.invStatus);
    dataWhere += ' AND InvStatus = @invStatus';
  }
  if (params.itemCode) {
    dataReq.input('itemCode', sql.VarChar, params.itemCode + '%');
    dataWhere += ' AND ItemCode LIKE @itemCode';
  }

  const dataResult = await dataReq.query(`
    SELECT WhCode, InvStatus, ItemCode, OhQty, OhAmnt
    FROM mmInventory WITH (NOLOCK)
    ${dataWhere}
    ORDER BY WhCode, ItemCode
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

/** 입출고내역 목록 조회 (IDX_mmInoutHeader_LSM2: SiteCode + InoutDate) */
export async function fetchInoutList(params: InoutListParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = 'WHERE SiteCode = @siteCode AND InoutDate BETWEEN @dateFrom AND @dateTo';
  if (params.inoutGubun) {
    countReq.input('inoutGubun', sql.VarChar, params.inoutGubun);
    countWhere += ' AND InoutGubun = @inoutGubun';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM mmInoutHeader WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE SiteCode = @siteCode AND InoutDate BETWEEN @dateFrom AND @dateTo';
  if (params.inoutGubun) {
    dataReq.input('inoutGubun', sql.VarChar, params.inoutGubun);
    dataWhere += ' AND InoutGubun = @inoutGubun';
  }

  const dataResult = await dataReq.query(`
    SELECT InoutNo, InoutGubun, InoutDate, SysCase, CaseCode,
           InoutPlace, InoutDescr, C_JumunNo
    FROM mmInoutHeader WITH (NOLOCK)
    ${dataWhere}
    ORDER BY InoutDate DESC, InoutNo DESC
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

/** 입출고 상세 조회 (헤더 + 항목 JOIN) */
export async function fetchInoutDetail(inoutNo: string, inoutGubun: string) {
  const pool = await getPool('xerp');

  const headerReq = pool.request();
  headerReq.input('siteCode', sql.VarChar, SITE_CODE);
  headerReq.input('inoutNo', sql.VarChar, inoutNo);
  headerReq.input('inoutGubun', sql.VarChar, inoutGubun);
  const headerResult = await headerReq.query(`
    SELECT InoutNo, InoutGubun, InoutDate, SysCase, CaseCode,
           InoutPlace, InoutDescr, C_JumunNo
    FROM mmInoutHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND InoutNo = @inoutNo AND InoutGubun = @inoutGubun
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  const itemReq = pool.request();
  itemReq.input('siteCode', sql.VarChar, SITE_CODE);
  itemReq.input('inoutNo', sql.VarChar, inoutNo);
  itemReq.input('inoutGubun', sql.VarChar, inoutGubun);
  const itemResult = await itemReq.query(`
    SELECT InoutSerNo, WhCode, ItemCode, ItemName, ItemSpec,
           InvStatus, InoutQty, UnitCode, InoutPrice, InoutAmnt, LotNo
    FROM mmInoutItem WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND InoutNo = @inoutNo AND InoutGubun = @inoutGubun
    ORDER BY InoutSerNo
  `);

  const items = itemResult.recordset;
  const totalQty = items.reduce((s: number, i: any) => s + (i.InoutQty || 0), 0);
  const totalAmnt = items.reduce((s: number, i: any) => s + (i.InoutAmnt || 0), 0);

  return {
    ...headerResult.recordset[0],
    items,
    totalQty,
    totalAmnt,
  };
}

/** 재고평가 조회 (C_mmEvaData + C_mmInvMonth JOIN) */
export async function fetchValuation(params: ValuationParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('invMonth', sql.VarChar, params.invMonth);

  let countWhere = 'WHERE e.SiteCode = @siteCode AND e.InvMonth = @invMonth AND (e.SQty > 0 OR e.InQty > 0)';
  if (params.invStatus) {
    countReq.input('invStatus', sql.VarChar, params.invStatus);
    countWhere += ' AND e.InvStatus = @invStatus';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM C_mmEvaData e WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('invMonth', sql.VarChar, params.invMonth);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE e.SiteCode = @siteCode AND e.InvMonth = @invMonth AND (e.SQty > 0 OR e.InQty > 0)';
  if (params.invStatus) {
    dataReq.input('invStatus', sql.VarChar, params.invStatus);
    dataWhere += ' AND e.InvStatus = @invStatus';
  }

  const dataResult = await dataReq.query(`
    SELECT
      e.ItemCode, e.InvStatus,
      e.SQty, e.SAmnt, e.InQty, e.InAmnt, e.StdPrice,
      ISNULL(m.OhQty, 0) AS OhQty, ISNULL(m.OhAmnt, 0) AS OhAmnt
    FROM C_mmEvaData e WITH (NOLOCK)
    LEFT JOIN C_mmInvMonth m WITH (NOLOCK)
      ON e.SiteCode = m.SiteCode AND e.InvMonth = m.InvMonth
      AND e.ItemCode = m.ItemCode AND e.InvStatus = m.InvStatus
    ${dataWhere}
    ORDER BY e.SAmnt DESC
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

/** 청구요청 목록 조회 */
export async function fetchRequisitionList(params: RequisitionListParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = 'WHERE SiteCode = @siteCode AND ReqDate BETWEEN @dateFrom AND @dateTo';
  if (params.reqStatus) {
    countReq.input('reqStatus', sql.VarChar, params.reqStatus);
    countWhere += ' AND ReqStatus = @reqStatus';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM mmRequisitHeader WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE h.SiteCode = @siteCode AND h.ReqDate BETWEEN @dateFrom AND @dateTo';
  if (params.reqStatus) {
    dataReq.input('reqStatus', sql.VarChar, params.reqStatus);
    dataWhere += ' AND h.ReqStatus = @reqStatus';
  }

  const dataResult = await dataReq.query(`
    SELECT h.ReqNo, h.SysCase, h.CaseCode, h.ReqDate, h.ExpectDate,
           h.ReqDept, h.ReqEmp, h.ReqStatus, h.ReqDescr,
           ISNULL(ic.itemCount, 0) AS itemCount
    FROM mmRequisitHeader h WITH (NOLOCK)
    LEFT JOIN (
      SELECT SiteCode, ReqNo, COUNT(*) AS itemCount
      FROM mmRequisitItem WITH (NOLOCK)
      WHERE SiteCode = @siteCode
      GROUP BY SiteCode, ReqNo
    ) ic ON h.SiteCode = ic.SiteCode AND h.ReqNo = ic.ReqNo
    ${dataWhere}
    ORDER BY h.ReqDate DESC, h.ReqNo DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  // 상태별 건수 (badges)
  const badgeReq = pool.request();
  badgeReq.input('siteCode', sql.VarChar, SITE_CODE);
  badgeReq.input('dateFrom', sql.VarChar, params.dateFrom);
  badgeReq.input('dateTo', sql.VarChar, params.dateTo);
  const badgeResult = await badgeReq.query(`
    SELECT ReqStatus, COUNT(*) AS cnt
    FROM mmRequisitHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND ReqDate BETWEEN @dateFrom AND @dateTo
    GROUP BY ReqStatus
  `);
  const badges: Record<string, number> = {};
  for (const row of badgeResult.recordset) {
    badges[row.ReqStatus?.trim()] = row.cnt;
  }

  return {
    data: dataResult.recordset,
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
    badges,
  };
}

/** 청구요청 상세 조회 (헤더 + 항목) */
export async function fetchRequisitionDetail(reqNo: string) {
  const pool = await getPool('xerp');

  const headerReq = pool.request();
  headerReq.input('siteCode', sql.VarChar, SITE_CODE);
  headerReq.input('reqNo', sql.VarChar, reqNo);
  const headerResult = await headerReq.query(`
    SELECT ReqNo, SysCase, CaseCode, ReqDate, ExpectDate,
           ReqDept, ReqEmp, ReqStatus, ReqDescr
    FROM mmRequisitHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND ReqNo = @reqNo
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  const itemReq = pool.request();
  itemReq.input('siteCode', sql.VarChar, SITE_CODE);
  itemReq.input('reqNo', sql.VarChar, reqNo);
  const itemResult = await itemReq.query(`
    SELECT ReqSerNo, WhCode, WhCodeIn, ItemCode, ReqQty, OutQty, ReqItemStatus
    FROM mmRequisitItem WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND ReqNo = @reqNo
    ORDER BY ReqSerNo
  `);

  const items = itemResult.recordset;
  const totalReqQty = items.reduce((s: number, i: any) => s + (i.ReqQty || 0), 0);
  const totalOutQty = items.reduce((s: number, i: any) => s + (i.OutQty || 0), 0);

  return {
    ...headerResult.recordset[0],
    items,
    totalReqQty,
    totalOutQty,
  };
}

/** 월마감 이력 조회 */
export async function fetchMonthClose() {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);

  const result = await req.query(`
    SELECT ModuleGubun, CloseMonth, CloseTime
    FROM mmMonthClose WITH (NOLOCK)
    WHERE SiteCode = @siteCode
    ORDER BY CloseMonth DESC
  `);

  return result.recordset;
}

/** 월별 재고 추이 조회 (C_mmInvMonth 월별 집계) */
export async function fetchMonthlyTrend(params: MonthlyTrendParams) {
  const pool = await getPool('xerp');

  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('startMonth', sql.VarChar, params.startMonth);
  req.input('endMonth', sql.VarChar, params.endMonth);

  let where = 'WHERE SiteCode = @siteCode AND InvMonth BETWEEN @startMonth AND @endMonth AND OhQty > 0';
  if (params.invStatus) {
    req.input('invStatus', sql.VarChar, params.invStatus);
    where += ' AND InvStatus = @invStatus';
  }

  const result = await req.query(`
    SELECT InvMonth,
           COUNT(DISTINCT ItemCode) AS itemCount,
           SUM(OhQty) AS totalQty,
           SUM(OhAmnt) AS totalAmnt
    FROM C_mmInvMonth WITH (NOLOCK)
    ${where}
    GROUP BY InvMonth
    ORDER BY InvMonth
  `);

  return result.recordset;
}

/** 창고 목록 조회 (필터용 - mmInventory에서 추출) */
export async function fetchWarehouses() {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);

  const result = await req.query(`
    SELECT DISTINCT WhCode
    FROM mmInventory WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND OhQty > 0
    ORDER BY WhCode
  `);

  return result.recordset.map((r: any) => r.WhCode.trim());
}
