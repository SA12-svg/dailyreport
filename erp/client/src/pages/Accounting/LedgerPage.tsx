import React, { useState } from 'react';
import { Card, Select, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { accountingApi } from '../../api/accounting.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const LedgerPage: React.FC = () => {
  const [accCode, setAccCode] = useState<string>('');
  const [dateRange, setDateRange] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
  });
  const [searchTriggered, setSearchTriggered] = useState(false);

  // 계정과목 목록 로드
  const { data: accounts } = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: () => accountingApi.getAccounts(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['accounting', 'ledger', accCode, dateRange],
    queryFn: () =>
      accountingApi.getLedger({
        accCode,
        dateFrom: dateRange.dateFrom,
        dateTo: dateRange.dateTo,
      }),
    enabled: searchTriggered && !!accCode,
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    if (start && end) {
      setDateRange({
        dateFrom: dayjs(start).format('YYYYMMDD'),
        dateTo: dayjs(end).format('YYYYMMDD'),
      });
    }
    setSearchTriggered(true);
  };

  const columns = [
    {
      title: '일자',
      dataIndex: 'RelDate',
      key: 'RelDate',
      width: 110,
      render: (date: string) =>
        date ? `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)}` : '',
    },
    {
      title: '전표번호',
      dataIndex: 'DocNo',
      key: 'DocNo',
      width: 140,
    },
    {
      title: '전표유형',
      dataIndex: 'DocType',
      key: 'DocType',
      width: 90,
    },
    {
      title: '적요',
      dataIndex: 'Remark',
      key: 'Remark',
      ellipsis: true,
    },
    {
      title: '차변',
      dataIndex: 'Debit',
      key: 'Debit',
      width: 130,
      align: 'right' as const,
      render: (val: number) => val ? <AmountFormat value={val} /> : '-',
    },
    {
      title: '대변',
      dataIndex: 'Credit',
      key: 'Credit',
      width: 130,
      align: 'right' as const,
      render: (val: number) => val ? <AmountFormat value={val} /> : '-',
    },
    {
      title: '잔액',
      dataIndex: 'Balance',
      key: 'Balance',
      width: 140,
      align: 'right' as const,
      render: (val: number) => (
        <AmountFormat value={val} type={val < 0 ? 'danger' : 'default'} />
      ),
    },
  ];

  const totalDebit = (data || []).reduce((s: number, r: any) => s + (r.Debit || 0), 0);
  const totalCredit = (data || []).reduce((s: number, r: any) => s + (r.Credit || 0), 0);

  return (
    <div>
      <Title level={4}>총계정원장</Title>
      <Card>
        <div style={{ marginBottom: 16 }}>
          <span style={{ marginRight: 8, fontWeight: 500 }}>계정과목:</span>
          <Select
            showSearch
            style={{ width: 300 }}
            placeholder="계정과목 선택"
            value={accCode || undefined}
            onChange={(val) => { setAccCode(val); setSearchTriggered(false); }}
            filterOption={(input, option) =>
              (option?.label as string || '').toLowerCase().includes(input.toLowerCase())
            }
            options={(accounts || []).map((acc: any) => ({
              value: acc.AccCode,
              label: `${acc.AccCode} - ${acc.AccName}`,
            }))}
          />
        </div>
        <FilterBar
          filters={filters}
          onSearch={handleSearch}
          loading={isLoading}
          extra={
            <ExportButton
              onExport={() => {}}
              disabled={!data?.length}
            />
          }
        />
        <DataTable
          columns={columns}
          data={data || []}
          loading={isLoading}
          rowKey={(record: any, index?: number) => `${record.DocNo}-${index}`}
          showSummary={!!data?.length}
          summaryRow={{ Debit: totalDebit, Credit: totalCredit }}
        />
      </Card>
    </div>
  );
};

export default LedgerPage;
