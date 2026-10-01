import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type {
  BillListParams,
  AgingParams,
  CollectionParams,
  OutstandingParams,
} from './billing.types.js';

const SITE_CODE = 'BK10';

/** AR/AP 청구 목록 조회 (IX_rpBillHeader 클러스터드: SiteCode + ArApGubun + BillDate + BillNo) */
export async function fetchBillList(params: BillListParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = 'WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo';
  if (params.arApGubun) {
    countReq.input('arApGubun', sql.VarChar, params.arApGubun);
    countWhere += ' AND ArApGubun = @arApGubun';
  }
  if (params.csCode) {
    countReq.input('csCode', sql.VarChar, params.csCode);
    countWhere += ' AND CsCode = @csCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM rpBillHeader WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo';
  if (params.arApGubun) {
    dataReq.input('arApGubun', sql.VarChar, params.arApGubun);
    dataWhere += ' AND ArApGubun = @arApGubun';
  }
  if (params.csCode) {
    dataReq.input('csCode', sql.VarChar, params.csCode);
    dataWhere += ' AND CsCode = @csCode';
  }

  const dataResult = await dataReq.query(`
    SELECT BillNo, ArApGubun, BillDate, CsCode, TaxCode, CurrCode,
           BillAmnt, VatAmnt, MoneySumAmnt, DeptCode, EmpCode,
           BillDescr, InvoiceNo, C_JumunNo
    FROM rpBillHeader WITH (NOLOCK)
    ${dataWhere}
    ORDER BY BillDate DESC, BillNo DESC
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

/** 청구 상세 조회 (헤더 + 항목) */
export async function fetchBillDetail(billNo: string, arApGubun: string) {
  const pool = await getPool('xerp');

  const headerReq = pool.request();
  headerReq.input('siteCode', sql.VarChar, SITE_CODE);
  headerReq.input('billNo', sql.VarChar, billNo);
  headerReq.input('arApGubun', sql.VarChar, arApGubun);
  const headerResult = await headerReq.query(`
    SELECT BillNo, ArApGubun, BillDate, CsCode, TaxCode, CurrCode,
           BillAmnt, VatAmnt, MoneySumAmnt, DeptCode, EmpCode,
           BillDescr, InvoiceNo, C_JumunNo
    FROM rpBillHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND BillNo = @billNo AND ArApGubun = @arApGubun
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  const itemReq = pool.request();
  itemReq.input('siteCode', sql.VarChar, SITE_CODE);
  itemReq.input('billNo', sql.VarChar, billNo);
  itemReq.input('arApGubun', sql.VarChar, arApGubun);
  const itemResult = await itemReq.query(`
    SELECT BillSerNo, ItemCode, ItemName, ItemSpec, ItemQty,
           UnitCode, ItemPrice, ItemAmnt, ItemVatAmnt, ItemGubun
    FROM rpBillItem WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND BillNo = @billNo AND ArApGubun = @arApGubun
    ORDER BY BillSerNo
  `);

  const items = itemResult.recordset;
  const totalItemAmnt = items.reduce((s: number, i: any) => s + (i.ItemAmnt || 0), 0);
  const totalVatAmnt = items.reduce((s: number, i: any) => s + (i.ItemVatAmnt || 0), 0);

  return {
    ...headerResult.recordset[0],
    items,
    totalItemAmnt,
    totalVatAmnt,
  };
}

/** 채권연령분석 조회 (rpMoneyExpect 기준 - 미수잔액 기준 연령 분석) */
export async function fetchAging(params: AgingParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('baseDate', sql.VarChar, params.baseDate);

  let countWhere = `WHERE SiteCode = @siteCode AND ExpectRemainAmnt > 0
    AND ExpectOrigin IN ('RP', 'AR')`;
  if (params.csCode) {
    countReq.input('csCode', sql.VarChar, params.csCode);
    countWhere += ' AND CsCode = @csCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(DISTINCT CsCode) AS total
    FROM rpMoneyExpect WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('baseDate', sql.VarChar, params.baseDate);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = `WHERE SiteCode = @siteCode AND ExpectRemainAmnt > 0
    AND ExpectOrigin IN ('RP', 'AR')`;
  if (params.csCode) {
    dataReq.input('csCode', sql.VarChar, params.csCode);
    dataWhere += ' AND CsCode = @csCode';
  }

  const dataResult = await dataReq.query(`
    SELECT
      CsCode,
      SUM(CASE WHEN DATEDIFF(DAY, ExpectDate, @baseDate) <= 0 THEN ExpectRemainAmnt ELSE 0 END) AS Current_,
      SUM(CASE WHEN DATEDIFF(DAY, ExpectDate, @baseDate) BETWEEN 1 AND 30 THEN ExpectRemainAmnt ELSE 0 END) AS Days30,
      SUM(CASE WHEN DATEDIFF(DAY, ExpectDate, @baseDate) BETWEEN 31 AND 60 THEN ExpectRemainAmnt ELSE 0 END) AS Days60,
      SUM(CASE WHEN DATEDIFF(DAY, ExpectDate, @baseDate) BETWEEN 61 AND 90 THEN ExpectRemainAmnt ELSE 0 END) AS Days90,
      SUM(CASE WHEN DATEDIFF(DAY, ExpectDate, @baseDate) BETWEEN 91 AND 120 THEN ExpectRemainAmnt ELSE 0 END) AS Days120,
      SUM(CASE WHEN DATEDIFF(DAY, ExpectDate, @baseDate) > 120 THEN ExpectRemainAmnt ELSE 0 END) AS Over120,
      SUM(ExpectRemainAmnt) AS Total
    FROM rpMoneyExpect WITH (NOLOCK)
    ${dataWhere}
    GROUP BY CsCode
    ORDER BY SUM(ExpectRemainAmnt) DESC
    OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY
  `);

  return {
    data: dataResult.recordset.map((r: any) => ({
      ...r,
      Current: r.Current_,
    })),
    pagination: {
      page: params.page,
      pageSize: params.pageSize,
      total,
      totalPages: Math.ceil(total / params.pageSize),
    },
  };
}

/** 수금현황 조회 (rpExpectMoneyAlloc 기준) */
export async function fetchCollections(params: CollectionParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = `WHERE a.SiteCode = @siteCode AND a.AllocDate BETWEEN @dateFrom AND @dateTo
    AND a.ArApGubun = 'AR'`;
  if (params.csCode) {
    countReq.input('csCode', sql.VarChar, params.csCode);
    countWhere += ' AND e.CsCode = @csCode';
  }
  if (params.payCode) {
    countReq.input('payCode', sql.VarChar, params.payCode);
    countWhere += ' AND a.PayCode = @payCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM rpExpectMoneyAlloc a WITH (NOLOCK)
    INNER JOIN rpMoneyExpect e WITH (NOLOCK)
      ON e.SiteCode = a.SiteCode AND e.OriginNo = a.OriginNo AND e.OriginSerNo = a.OriginSerNo
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = `WHERE a.SiteCode = @siteCode AND a.AllocDate BETWEEN @dateFrom AND @dateTo
    AND a.ArApGubun = 'AR'`;
  if (params.csCode) {
    dataReq.input('csCode', sql.VarChar, params.csCode);
    dataWhere += ' AND e.CsCode = @csCode';
  }
  if (params.payCode) {
    dataReq.input('payCode', sql.VarChar, params.payCode);
    dataWhere += ' AND a.PayCode = @payCode';
  }

  const dataResult = await dataReq.query(`
    SELECT a.AllocDate, a.OriginNo, e.CsCode, a.PayCode,
           a.AllocAmnt, a.C_JumunNo
    FROM rpExpectMoneyAlloc a WITH (NOLOCK)
    INNER JOIN rpMoneyExpect e WITH (NOLOCK)
      ON e.SiteCode = a.SiteCode AND e.OriginNo = a.OriginNo AND e.OriginSerNo = a.OriginSerNo
    ${dataWhere}
    ORDER BY a.AllocDate DESC, a.OriginNo DESC
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

/** 미수금 상세 조회 (rpMoneyExpect 잔액 > 0) */
export async function fetchOutstanding(params: OutstandingParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);

  let countWhere = `WHERE SiteCode = @siteCode AND ExpectRemainAmnt > 0
    AND ExpectOrigin IN ('RP', 'AR')`;
  if (params.csCode) {
    countReq.input('csCode', sql.VarChar, params.csCode);
    countWhere += ' AND CsCode = @csCode';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM rpMoneyExpect WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = `WHERE SiteCode = @siteCode AND ExpectRemainAmnt > 0
    AND ExpectOrigin IN ('RP', 'AR')`;
  if (params.csCode) {
    dataReq.input('csCode', sql.VarChar, params.csCode);
    dataWhere += ' AND CsCode = @csCode';
  }

  const dataResult = await dataReq.query(`
    SELECT OriginNo, CsCode, ExpectDate, ExpectAmnt,
           ExpectRemainAmnt, ArApAcc, C_JumunNo
    FROM rpMoneyExpect WITH (NOLOCK)
    ${dataWhere}
    ORDER BY ExpectRemainAmnt DESC
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

/** 거래처 목록 조회 (필터용 - rpBillHeader에서 추출) */
export async function fetchCustomers() {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);

  const result = await req.query(`
    SELECT DISTINCT TOP 500 CsCode
    FROM rpBillHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND BillDate >= '20250101'
    ORDER BY CsCode
  `);

  return result.recordset.map((r: any) => r.CsCode.trim());
}
