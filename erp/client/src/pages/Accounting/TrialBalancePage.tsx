import React, { useState } from 'react';
import { Card, Alert, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { accountingApi } from '../../api/accounting.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const filters: FilterConfig[] = [
  { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
];

const TrialBalancePage: React.FC = () => {
  const [dateRange, setDateRange] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
  });
  const [searchTriggered, setSearchTriggered] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['accounting', 'trial-balance', dateRange],
    queryFn: () => accountingApi.getTrialBalance(dateRange),
    enabled: searchTriggered,
    staleTime: 5 * 60 * 1000,
  });

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
      title: '계정코드',
      dataIndex: 'AccCode',
      key: 'AccCode',
      width: 100,
    },
    {
      title: '계정명',
      dataIndex: 'AccName',
      key: 'AccName',
      width: 180,
    },
    {
      title: '차변 합계',
      dataIndex: 'Debit',
      key: 'Debit',
      width: 140,
      align: 'right' as const,
      render: (val: number) => val ? <AmountFormat value={val} /> : '-',
    },
    {
      title: '대변 합계',
      dataIndex: 'Credit',
      key: 'Credit',
      width: 140,
      align: 'right' as const,
      render: (val: number) => val ? <AmountFormat value={val} /> : '-',
    },
    {
      title: '차변 잔액',
      dataIndex: 'DebitBalance',
      key: 'DebitBalance',
      width: 140,
      align: 'right' as const,
      render: (val: number) => val ? <AmountFormat value={val} /> : '-',
    },
    {
      title: '대변 잔액',
      dataIndex: 'CreditBalance',
      key: 'CreditBalance',
      width: 140,
      align: 'right' as const,
      render: (val: number) => val ? <AmountFormat value={val} /> : '-',
    },
  ];

  const items = data?.data || [];
  const summary = data?.summary;

  return (
    <div>
      <Title level={4}>시산표</Title>
      <Card>
        <FilterBar
          filters={filters}
          onSearch={handleSearch}
          loading={isLoading}
          extra={
            <ExportButton
              onExport={() => {}}
              disabled={!items.length}
            />
          }
        />

        {summary && !summary.isBalanced && (
          <Alert
            type="error"
            message="차대변 불일치"
            description={`차변 합계(${summary.totalDebit.toLocaleString()})와 대변 합계(${summary.totalCredit.toLocaleString()})가 일치하지 않습니다. 차이: ${Math.abs(summary.totalDebit - summary.totalCredit).toLocaleString()}`}
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        {summary && summary.isBalanced && items.length > 0 && (
          <Alert
            type="success"
            message="차대변 일치"
            description={`차변/대변 합계가 ${summary.totalDebit.toLocaleString()}원으로 일치합니다.`}
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <DataTable
          columns={columns}
          data={items}
          loading={isLoading}
          rowKey="AccCode"
          showSummary={!!items.length}
          summaryRow={{
            Debit: summary?.totalDebit || 0,
            Credit: summary?.totalCredit || 0,
            DebitBalance: items.reduce((s: number, e: any) => s + (e.DebitBalance || 0), 0),
            CreditBalance: items.reduce((s: number, e: any) => s + (e.CreditBalance || 0), 0),
          }}
        />
      </Card>
    </div>
  );
};

export default TrialBalancePage;
