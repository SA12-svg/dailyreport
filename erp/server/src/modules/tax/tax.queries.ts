import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type {
  TaxInvoiceListParams,
  VatReturnParams,
  EInvoiceParams,
  SummaryTableParams,
} from './tax.types.js';

const SITE_CODE = 'BK10';

/** 세금계산서 목록 조회 (IX_rpBillHeader 클러스터드: SiteCode + ArApGubun + BillDate + BillNo) */
export async function fetchTaxInvoiceList(params: TaxInvoiceListParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    countReq.input('arApGubun', sql.VarChar, params.arApGubun);
    countWhere += ' AND ArApGubun = @arApGubun';
  }
  if (params.taxCode) {
    countReq.input('taxCode', sql.VarChar, params.taxCode);
    countWhere += ' AND TaxCode = @taxCode';
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

  let dataWhere = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    dataReq.input('arApGubun', sql.VarChar, params.arApGubun);
    dataWhere += ' AND ArApGubun = @arApGubun';
  }
  if (params.taxCode) {
    dataReq.input('taxCode', sql.VarChar, params.taxCode);
    dataWhere += ' AND TaxCode = @taxCode';
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

/** 세금계산서 상세 조회 (헤더 + 항목) */
export async function fetchTaxInvoiceDetail(billNo: string, arApGubun: string) {
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

/** 부가세 신고 자동집계 (분기별 세금코드/AR·AP별 집계) */
export async function fetchVatReturn(params: VatReturnParams) {
  const pool = await getPool('xerp');

  const quarterRanges: Record<string, { from: string; to: string }> = {
    '1': { from: `${params.year}0101`, to: `${params.year}0331` },
    '2': { from: `${params.year}0401`, to: `${params.year}0630` },
    '3': { from: `${params.year}0701`, to: `${params.year}0930` },
    '4': { from: `${params.year}1001`, to: `${params.year}1231` },
  };
  const range = quarterRanges[params.quarter];
  if (!range) {
    return { data: [] };
  }

  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('dateFrom', sql.VarChar, range.from);
  req.input('dateTo', sql.VarChar, range.to);

  let where = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    req.input('arApGubun', sql.VarChar, params.arApGubun);
    where += ' AND ArApGubun = @arApGubun';
  }

  const result = await req.query(`
    SELECT
      TaxCode,
      ArApGubun,
      COUNT(*) AS InvoiceCount,
      SUM(BillAmnt) AS SupplyAmnt,
      SUM(VatAmnt) AS VatAmnt,
      SUM(BillAmnt + VatAmnt) AS TotalAmnt
    FROM rpBillHeader WITH (NOLOCK)
    ${where}
    GROUP BY TaxCode, ArApGubun
    ORDER BY ArApGubun, TaxCode
  `);

  return { data: result.recordset };
}

/** 전자세금계산서 현황 조회 (InvoiceNo 유무 기준) */
export async function fetchEInvoices(params: EInvoiceParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    countReq.input('arApGubun', sql.VarChar, params.arApGubun);
    countWhere += ' AND ArApGubun = @arApGubun';
  }
  if (params.csCode) {
    countReq.input('csCode', sql.VarChar, params.csCode);
    countWhere += ' AND CsCode = @csCode';
  }
  if (params.hasInvoiceNo === 'Y') {
    countWhere += " AND InvoiceNo IS NOT NULL AND InvoiceNo <> ''";
  } else if (params.hasInvoiceNo === 'N') {
    countWhere += " AND (InvoiceNo IS NULL OR InvoiceNo = '')";
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

  let dataWhere = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    dataReq.input('arApGubun', sql.VarChar, params.arApGubun);
    dataWhere += ' AND ArApGubun = @arApGubun';
  }
  if (params.csCode) {
    dataReq.input('csCode', sql.VarChar, params.csCode);
    dataWhere += ' AND CsCode = @csCode';
  }
  if (params.hasInvoiceNo === 'Y') {
    dataWhere += " AND InvoiceNo IS NOT NULL AND InvoiceNo <> ''";
  } else if (params.hasInvoiceNo === 'N') {
    dataWhere += " AND (InvoiceNo IS NULL OR InvoiceNo = '')";
  }

  const dataResult = await dataReq.query(`
    SELECT BillNo, ArApGubun, BillDate, CsCode, TaxCode,
           BillAmnt, VatAmnt, InvoiceNo,
           CASE
             WHEN InvoiceNo IS NOT NULL AND InvoiceNo <> '' THEN '발행완료'
             ELSE '미발행'
           END AS EInvoiceStatus
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

/** 합계표 조회 (거래처별 세금계산서 집계) */
export async function fetchSummaryTable(params: SummaryTableParams) {
  const pool = await getPool('xerp');

  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    countReq.input('arApGubun', sql.VarChar, params.arApGubun);
    countWhere += ' AND ArApGubun = @arApGubun';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(DISTINCT CsCode) AS total
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

  let dataWhere = `WHERE SiteCode = @siteCode AND BillDate BETWEEN @dateFrom AND @dateTo
    AND TaxCode IN ('01', '02', '03', '04', '11', '12')`;
  if (params.arApGubun) {
    dataReq.input('arApGubun', sql.VarChar, params.arApGubun);
    dataWhere += ' AND ArApGubun = @arApGubun';
  }

  const dataResult = await dataReq.query(`
    SELECT
      CsCode,
      COUNT(*) AS InvoiceCount,
      SUM(BillAmnt) AS SupplyAmnt,
      SUM(VatAmnt) AS VatAmnt,
      SUM(BillAmnt + VatAmnt) AS TotalAmnt
    FROM rpBillHeader WITH (NOLOCK)
    ${dataWhere}
    GROUP BY CsCode
    ORDER BY SUM(BillAmnt + VatAmnt) DESC
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

/** 거래처 목록 조회 (필터용 - 세금계산서 발행 거래처) */
export async function fetchTaxCustomers() {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);

  const result = await req.query(`
    SELECT DISTINCT TOP 500 CsCode
    FROM rpBillHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND BillDate >= '20250101'
      AND TaxCode IN ('01', '02', '03', '04', '11', '12')
    ORDER BY CsCode
  `);

  return result.recordset.map((r: any) => r.CsCode.trim());
}
