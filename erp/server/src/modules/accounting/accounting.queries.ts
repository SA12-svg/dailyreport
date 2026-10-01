import sql from 'mssql';
import { getPool } from '../../config/database.js';
import type {
  VoucherListParams,
  LedgerParams,
  FinancialParams,
  CumulativeParams,
} from './accounting.types.js';

const SITE_CODE = 'BK10';
const COA_CODE = 'COA1';

/** 전표 목록 조회 (glDocHeader 클러스터드 인덱스 활용: SiteCode + RelDate) */
export async function fetchVoucherList(params: VoucherListParams) {
  const pool = await getPool('xerp');

  // 카운트 쿼리
  const countReq = pool.request();
  countReq.input('siteCode', sql.VarChar, SITE_CODE);
  countReq.input('dateFrom', sql.VarChar, params.dateFrom);
  countReq.input('dateTo', sql.VarChar, params.dateTo);

  let countWhere = 'WHERE SiteCode = @siteCode AND RelDate BETWEEN @dateFrom AND @dateTo';
  if (params.docType) {
    countReq.input('docType', sql.VarChar, params.docType);
    countWhere += ' AND DocType = @docType';
  }
  if (params.status) {
    countReq.input('status', sql.VarChar, params.status);
    countWhere += ' AND DocGubun = @status';
  }

  const countResult = await countReq.query(`
    SELECT COUNT(*) AS total
    FROM glDocHeader WITH (NOLOCK)
    ${countWhere}
  `);
  const total = countResult.recordset[0]?.total ?? 0;

  // 데이터 쿼리 (TotalAmt는 glDocItem에서 차변 합계로 계산)
  const dataReq = pool.request();
  dataReq.input('siteCode', sql.VarChar, SITE_CODE);
  dataReq.input('dateFrom', sql.VarChar, params.dateFrom);
  dataReq.input('dateTo', sql.VarChar, params.dateTo);
  dataReq.input('offset', sql.Int, (params.page - 1) * params.pageSize);
  dataReq.input('pageSize', sql.Int, params.pageSize);

  let dataWhere = 'WHERE h.SiteCode = @siteCode AND h.RelDate BETWEEN @dateFrom AND @dateTo';
  if (params.docType) {
    dataReq.input('docType', sql.VarChar, params.docType);
    dataWhere += ' AND h.DocType = @docType';
  }
  if (params.status) {
    dataReq.input('status', sql.VarChar, params.status);
    dataWhere += ' AND h.DocGubun = @status';
  }

  const dataResult = await dataReq.query(`
    SELECT h.DocNo, h.DocType, h.RelDate, h.DocDescr AS Remark,
           ISNULL(t.TotalAmt, 0) AS TotalAmt,
           h.DocGubun AS Status, h.EmpCode AS RegUser, h.SystemDate AS RegDate
    FROM glDocHeader h WITH (NOLOCK)
    LEFT JOIN (
      SELECT SiteCode, DocNo, SUM(CASE WHEN DrCr = 'D' THEN DocAmnt ELSE 0 END) AS TotalAmt
      FROM glDocItem WITH (NOLOCK)
      WHERE SiteCode = @siteCode
      GROUP BY SiteCode, DocNo
    ) t ON h.SiteCode = t.SiteCode AND h.DocNo = t.DocNo
    ${dataWhere}
    ORDER BY h.RelDate DESC, h.DocNo DESC
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

/** 전표 상세 조회 (헤더 + 항목 JOIN) */
export async function fetchVoucherDetail(docNo: string) {
  const pool = await getPool('xerp');

  // 헤더
  const headerReq = pool.request();
  headerReq.input('siteCode', sql.VarChar, SITE_CODE);
  headerReq.input('docNo', sql.VarChar, docNo);
  const headerResult = await headerReq.query(`
    SELECT DocNo, DocType, RelDate, DocDescr AS Remark,
           DocGubun AS Status, EmpCode AS RegUser, SystemDate AS RegDate
    FROM glDocHeader WITH (NOLOCK)
    WHERE SiteCode = @siteCode AND DocNo = @docNo
  `);

  if (headerResult.recordset.length === 0) {
    return null;
  }

  // 항목
  const itemReq = pool.request();
  itemReq.input('siteCode', sql.VarChar, SITE_CODE);
  itemReq.input('docNo', sql.VarChar, docNo);
  itemReq.input('coaCode', sql.VarChar, COA_CODE);
  const itemResult = await itemReq.query(`
    SELECT
      i.DocSerNo AS ItemSeq, i.AccCode, ISNULL(a.AccName, i.AccCode) AS AccName,
      i.DrCr, i.DocAmnt AS Amount, i.DocDescr AS Remark, i.CsCode AS CustCode
    FROM glDocItem i WITH (NOLOCK)
    LEFT JOIN AccMaster a WITH (NOLOCK) ON a.CoaCode = @coaCode AND a.AccCode = i.AccCode
    WHERE i.SiteCode = @siteCode AND i.DocNo = @docNo
    ORDER BY i.DocSerNo
  `);

  const items = itemResult.recordset;
  const totalDebit = items.filter((i: any) => i.DrCr?.trim() === 'D').reduce((s: number, i: any) => s + (i.Amount || 0), 0);
  const totalCredit = items.filter((i: any) => i.DrCr?.trim() === 'C').reduce((s: number, i: any) => s + (i.Amount || 0), 0);

  return {
    ...headerResult.recordset[0],
    TotalAmt: totalDebit,
    items,
    totalDebit,
    totalCredit,
    isBalanced: Math.abs(totalDebit - totalCredit) < 0.01,
  };
}

/** 총계정원장 조회 */
export async function fetchLedger(params: LedgerParams) {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('accCode', sql.VarChar, params.accCode);
  req.input('dateFrom', sql.VarChar, params.dateFrom);
  req.input('dateTo', sql.VarChar, params.dateTo);

  const result = await req.query(`
    SELECT
      h.RelDate, h.DocNo, h.DocType, i.DocDescr AS Remark,
      CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END AS Debit,
      CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END AS Credit
    FROM glDocItem i WITH (NOLOCK)
    INNER JOIN glDocHeader h WITH (NOLOCK)
      ON h.SiteCode = i.SiteCode AND h.DocNo = i.DocNo
    WHERE i.SiteCode = @siteCode
      AND i.AccCode = @accCode
      AND h.RelDate BETWEEN @dateFrom AND @dateTo
    ORDER BY h.RelDate, h.DocNo, i.DocSerNo
  `);

  // 잔액 누계 계산
  let balance = 0;
  const entries = result.recordset.map((row: any) => {
    balance += (row.Debit || 0) - (row.Credit || 0);
    return { ...row, Balance: balance };
  });

  return entries;
}

/** 시산표 조회 (계정별 차변/대변 합계) */
export async function fetchTrialBalance(params: FinancialParams) {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('dateFrom', sql.VarChar, params.dateFrom);
  req.input('dateTo', sql.VarChar, params.dateTo);
  req.input('coaCode', sql.VarChar, COA_CODE);

  const result = await req.query(`
    SELECT
      i.AccCode,
      ISNULL(a.AccName, i.AccCode) AS AccName,
      SUM(CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END) AS Debit,
      SUM(CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END) AS Credit
    FROM glDocItem i WITH (NOLOCK)
    INNER JOIN glDocHeader h WITH (NOLOCK)
      ON h.SiteCode = i.SiteCode AND h.DocNo = i.DocNo
    LEFT JOIN AccMaster a WITH (NOLOCK)
      ON a.CoaCode = @coaCode AND a.AccCode = i.AccCode
    WHERE i.SiteCode = @siteCode
      AND h.RelDate BETWEEN @dateFrom AND @dateTo
    GROUP BY i.AccCode, a.AccName
    ORDER BY i.AccCode
  `);

  return result.recordset.map((row: any) => ({
    ...row,
    DebitBalance: row.Debit > row.Credit ? row.Debit - row.Credit : 0,
    CreditBalance: row.Credit > row.Debit ? row.Credit - row.Debit : 0,
  }));
}

/** 재무상태표 (K-GAAP 기준: AccCode 범위로 분류) */
export async function fetchBalanceSheet(params: FinancialParams) {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('dateTo', sql.VarChar, params.dateTo);
  req.input('coaCode', sql.VarChar, COA_CODE);

  const result = await req.query(`
    SELECT
      i.AccCode,
      ISNULL(a.AccName, i.AccCode) AS AccName,
      SUM(CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END) -
      SUM(CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END) AS NetAmount
    FROM glDocItem i WITH (NOLOCK)
    INNER JOIN glDocHeader h WITH (NOLOCK)
      ON h.SiteCode = i.SiteCode AND h.DocNo = i.DocNo
    LEFT JOIN AccMaster a WITH (NOLOCK)
      ON a.CoaCode = @coaCode AND a.AccCode = i.AccCode
    WHERE i.SiteCode = @siteCode
      AND h.RelDate <= @dateTo
      AND (i.AccCode LIKE '1%' OR i.AccCode LIKE '2%' OR i.AccCode LIKE '3%')
    GROUP BY i.AccCode, a.AccName
    HAVING SUM(CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END) -
           SUM(CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END) <> 0
    ORDER BY i.AccCode
  `);

  // K-GAAP 분류
  const assets: any[] = [];
  const liabilities: any[] = [];
  const equity: any[] = [];

  for (const row of result.recordset) {
    const code = row.AccCode?.trim();
    const entry = {
      AccCode: code,
      AccName: row.AccName?.trim(),
      Amount: Math.abs(row.NetAmount),
    };

    if (code.startsWith('1')) {
      assets.push({ ...entry, Category: 'asset', SubCategory: getAssetSubCategory(code) });
    } else if (code.startsWith('2')) {
      liabilities.push({ ...entry, Category: 'liability', SubCategory: getLiabilitySubCategory(code), Amount: Math.abs(row.NetAmount) });
    } else if (code.startsWith('3')) {
      equity.push({ ...entry, Category: 'equity', SubCategory: getEquitySubCategory(code), Amount: Math.abs(row.NetAmount) });
    }
  }

  const totalAssets = assets.reduce((s, e) => s + e.Amount, 0);
  const totalLiabilities = liabilities.reduce((s, e) => s + e.Amount, 0);
  const totalEquity = equity.reduce((s, e) => s + e.Amount, 0);

  return {
    assets,
    liabilities,
    equity,
    totalAssets,
    totalLiabilities,
    totalEquity,
    isBalanced: Math.abs(totalAssets - (totalLiabilities + totalEquity)) < 0.01,
  };
}

/** 손익계산서 */
export async function fetchIncomeStatement(params: FinancialParams) {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('dateFrom', sql.VarChar, params.dateFrom);
  req.input('dateTo', sql.VarChar, params.dateTo);
  req.input('coaCode', sql.VarChar, COA_CODE);

  const result = await req.query(`
    SELECT
      i.AccCode,
      ISNULL(a.AccName, i.AccCode) AS AccName,
      SUM(CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END) -
      SUM(CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END) AS NetAmount
    FROM glDocItem i WITH (NOLOCK)
    INNER JOIN glDocHeader h WITH (NOLOCK)
      ON h.SiteCode = i.SiteCode AND h.DocNo = i.DocNo
    LEFT JOIN AccMaster a WITH (NOLOCK)
      ON a.CoaCode = @coaCode AND a.AccCode = i.AccCode
    WHERE i.SiteCode = @siteCode
      AND h.RelDate BETWEEN @dateFrom AND @dateTo
      AND (i.AccCode LIKE '4%' OR i.AccCode LIKE '5%' OR i.AccCode LIKE '8%' OR i.AccCode LIKE '9%')
    GROUP BY i.AccCode, a.AccName
    HAVING SUM(CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END) -
           SUM(CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END) <> 0
    ORDER BY i.AccCode
  `);

  const revenue: any[] = [];
  const expenses: any[] = [];

  for (const row of result.recordset) {
    const code = row.AccCode?.trim();
    const entry = {
      AccCode: code,
      AccName: row.AccName?.trim(),
      Amount: Math.abs(row.NetAmount),
    };

    if (code.startsWith('4')) {
      revenue.push({ ...entry, Category: 'revenue', SubCategory: getRevenueSubCategory(code) });
    } else {
      expenses.push({ ...entry, Category: 'expense', SubCategory: getExpenseSubCategory(code) });
    }
  }

  const totalRevenue = revenue.reduce((s, e) => s + e.Amount, 0);
  const totalExpenses = expenses.reduce((s, e) => s + e.Amount, 0);

  return {
    revenue,
    expenses,
    totalRevenue,
    totalExpenses,
    netIncome: totalRevenue - totalExpenses,
  };
}

/** 현금흐름표 (간접법 기반 간이 현금흐름) */
export async function fetchCashFlow(params: FinancialParams) {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('dateFrom', sql.VarChar, params.dateFrom);
  req.input('dateTo', sql.VarChar, params.dateTo);
  req.input('coaCode', sql.VarChar, COA_CODE);

  // 현금성 계정(1010~1019) 기준 입출금 내역
  const result = await req.query(`
    SELECT
      i.AccCode,
      ISNULL(a.AccName, i.AccCode) AS AccName,
      SUM(CASE WHEN i.DrCr = 'D' THEN i.DocAmnt ELSE 0 END) AS CashIn,
      SUM(CASE WHEN i.DrCr = 'C' THEN i.DocAmnt ELSE 0 END) AS CashOut
    FROM glDocItem i WITH (NOLOCK)
    INNER JOIN glDocHeader h WITH (NOLOCK)
      ON h.SiteCode = i.SiteCode AND h.DocNo = i.DocNo
    LEFT JOIN AccMaster a WITH (NOLOCK)
      ON a.CoaCode = @coaCode AND a.AccCode = i.AccCode
    WHERE i.SiteCode = @siteCode
      AND h.RelDate BETWEEN @dateFrom AND @dateTo
    GROUP BY i.AccCode, a.AccName
    ORDER BY i.AccCode
  `);

  const operating: any[] = [];
  const investing: any[] = [];
  const financing: any[] = [];

  for (const row of result.recordset) {
    const code = row.AccCode?.trim();
    const amount = (row.CashIn || 0) - (row.CashOut || 0);
    if (amount === 0) continue;

    const entry = { AccCode: code, AccName: row.AccName?.trim(), Amount: amount };

    if (code.startsWith('4') || code.startsWith('5') || code.startsWith('11') || code.startsWith('12') || code.startsWith('21') || code.startsWith('22')) {
      operating.push({ ...entry, Category: 'operating' });
    } else if (code.startsWith('15') || code.startsWith('16') || code.startsWith('17') || code.startsWith('18') || code.startsWith('19')) {
      investing.push({ ...entry, Category: 'investing' });
    } else if (code.startsWith('23') || code.startsWith('24') || code.startsWith('25') || code.startsWith('3')) {
      financing.push({ ...entry, Category: 'financing' });
    }
  }

  return {
    operating,
    investing,
    financing,
    totalOperating: operating.reduce((s, e) => s + e.Amount, 0),
    totalInvesting: investing.reduce((s, e) => s + e.Amount, 0),
    totalFinancing: financing.reduce((s, e) => s + e.Amount, 0),
    netCashFlow: [...operating, ...investing, ...financing].reduce((s, e) => s + e.Amount, 0),
  };
}

/** 누계 조회 (glAccCum / glDeptCum / glCsCum) */
export async function fetchCumulative(params: CumulativeParams) {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('siteCode', sql.VarChar, SITE_CODE);
  req.input('year', sql.VarChar, params.year);
  req.input('coaCode', sql.VarChar, COA_CODE);

  const tableMap: Record<string, string> = {
    account: 'glAccCum',
    dept: 'glDeptCum',
    cs: 'glCsCum',
  };
  const tableName = tableMap[params.cumType || 'account'] || 'glAccCum';

  const result = await req.query(`
    SELECT
      c.AccCode,
      ISNULL(a.AccName, c.AccCode) AS AccName,
      ISNULL(c.Month01, 0) AS Month01,
      ISNULL(c.Month02, 0) AS Month02,
      ISNULL(c.Month03, 0) AS Month03,
      ISNULL(c.Month04, 0) AS Month04,
      ISNULL(c.Month05, 0) AS Month05,
      ISNULL(c.Month06, 0) AS Month06,
      ISNULL(c.Month07, 0) AS Month07,
      ISNULL(c.Month08, 0) AS Month08,
      ISNULL(c.Month09, 0) AS Month09,
      ISNULL(c.Month10, 0) AS Month10,
      ISNULL(c.Month11, 0) AS Month11,
      ISNULL(c.Month12, 0) AS Month12,
      ISNULL(c.Month01,0)+ISNULL(c.Month02,0)+ISNULL(c.Month03,0)+
      ISNULL(c.Month04,0)+ISNULL(c.Month05,0)+ISNULL(c.Month06,0)+
      ISNULL(c.Month07,0)+ISNULL(c.Month08,0)+ISNULL(c.Month09,0)+
      ISNULL(c.Month10,0)+ISNULL(c.Month11,0)+ISNULL(c.Month12,0) AS Total
    FROM ${tableName} c WITH (NOLOCK)
    LEFT JOIN AccMaster a WITH (NOLOCK)
      ON a.CoaCode = @coaCode AND a.AccCode = c.AccCode
    WHERE c.SiteCode = @siteCode AND c.FiscalYear = @year
    ORDER BY c.AccCode
  `);

  return result.recordset;
}

/** 계정과목 목록 조회 (필터용) */
export async function fetchAccountList() {
  const pool = await getPool('xerp');
  const req = pool.request();
  req.input('coaCode', sql.VarChar, COA_CODE);
  const result = await req.query(`
    SELECT AccCode, AccName
    FROM AccMaster WITH (NOLOCK)
    WHERE CoaCode = @coaCode AND AccUse = 'Y'
    ORDER BY AccCode
  `);
  return result.recordset;
}

// K-GAAP 분류 헬퍼 함수
function getAssetSubCategory(code: string): string {
  if (code >= '1010' && code < '1200') return '유동자산';
  if (code >= '1200' && code < '1500') return '비유동자산';
  return '기타자산';
}

function getLiabilitySubCategory(code: string): string {
  if (code >= '2010' && code < '2200') return '유동부채';
  if (code >= '2200' && code < '2500') return '비유동부채';
  return '기타부채';
}

function getEquitySubCategory(code: string): string {
  if (code >= '3010' && code < '3100') return '자본금';
  if (code >= '3100' && code < '3200') return '자본잉여금';
  if (code >= '3200' && code < '3300') return '이익잉여금';
  return '기타자본';
}

function getRevenueSubCategory(code: string): string {
  if (code >= '4010' && code < '4100') return '매출';
  if (code >= '4100' && code < '4200') return '영업외수익';
  return '기타수익';
}

function getExpenseSubCategory(code: string): string {
  if (code >= '5010' && code < '5100') return '매출원가';
  if (code >= '5100' && code < '5200') return '판매관리비';
  if (code >= '8000' && code < '9000') return '영업외비용';
  if (code >= '9000') return '법인세비용';
  return '기타비용';
}
