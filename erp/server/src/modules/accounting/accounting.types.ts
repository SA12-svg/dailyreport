// 전표 헤더
export interface VoucherHeader {
  DocNo: string;
  DocType: string;
  RelDate: string;
  Remark: string;
  TotalAmt: number;
  Status: string;
  RegUser: string;
  RegDate: string;
}

// 전표 항목 (차대변)
export interface VoucherItem {
  ItemSeq: number;
  AccCode: string;
  AccName: string;
  DrCr: 'D' | 'C'; // D: 차변, C: 대변
  Amount: number;
  Remark: string;
  DeptCode: string;
  CustCode: string;
}

// 전표 상세 (헤더 + 항목)
export interface VoucherDetail extends VoucherHeader {
  items: VoucherItem[];
  totalDebit: number;
  totalCredit: number;
  isBalanced: boolean;
}

// 총계정원장 항목
export interface LedgerEntry {
  RelDate: string;
  DocNo: string;
  DocType: string;
  Remark: string;
  Debit: number;
  Credit: number;
  Balance: number;
}

// 시산표 항목
export interface TrialBalanceEntry {
  AccCode: string;
  AccName: string;
  Debit: number;
  Credit: number;
  DebitBalance: number;
  CreditBalance: number;
}

// 재무상태표 항목
export interface BalanceSheetEntry {
  AccCode: string;
  AccName: string;
  Category: 'asset' | 'liability' | 'equity';
  SubCategory: string;
  Amount: number;
  children?: BalanceSheetEntry[];
}

// 손익계산서 항목
export interface IncomeStatementEntry {
  AccCode: string;
  AccName: string;
  Category: 'revenue' | 'expense';
  SubCategory: string;
  Amount: number;
  children?: IncomeStatementEntry[];
}

// 현금흐름표 항목
export interface CashFlowEntry {
  Category: 'operating' | 'investing' | 'financing';
  AccCode: string;
  AccName: string;
  Amount: number;
}

// 누계 항목
export interface CumulativeEntry {
  AccCode: string;
  AccName: string;
  Month01: number;
  Month02: number;
  Month03: number;
  Month04: number;
  Month05: number;
  Month06: number;
  Month07: number;
  Month08: number;
  Month09: number;
  Month10: number;
  Month11: number;
  Month12: number;
  Total: number;
}

// 전표 목록 쿼리 파라미터
export interface VoucherListParams {
  dateFrom: string;
  dateTo: string;
  docType?: string;
  status?: string;
  page: number;
  pageSize: number;
}

// 총계정원장 쿼리 파라미터
export interface LedgerParams {
  accCode: string;
  dateFrom: string;
  dateTo: string;
}

// 시산표/재무제표 쿼리 파라미터
export interface FinancialParams {
  dateFrom: string;
  dateTo: string;
}

// 누계 쿼리 파라미터
export interface CumulativeParams {
  year: string;
  cumType?: 'account' | 'dept' | 'cs';
}
