import React, { useState } from 'react';
import { Card, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { billingApi } from '../../api/billing.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const AgingAnalysisPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    baseDate: dayjs().format('YYYYMMDD'),
    csCode: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data: customers } = useQuery({
    queryKey: ['billing', 'customers'],
    queryFn: () => billingApi.getCustomers(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['billing', 'aging', searchParams],
    queryFn: () => billingApi.getAging(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'date', key: 'baseDate', label: '기준일', required: true },
    {
      type: 'select',
      key: 'csCode',
      label: '거래처',
      options: (customers || []).map((cs: string) => ({ value: cs, label: cs })),
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    setSearchParams((prev) => ({
      ...prev,
      baseDate: values.baseDate ? dayjs(values.baseDate).format('YYYYMMDD') : prev.baseDate,
      csCode: values.csCode || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      baseDate: dayjs().format('YYYYMMDD'),
      csCode: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '거래처',
      dataIndex: 'CsCode',
      key: 'CsCode',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '미도래',
      dataIndex: 'Current',
      key: 'Current',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '1~30일',
      dataIndex: 'Days30',
      key: 'Days30',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '31~60일',
      dataIndex: 'Days60',
      key: 'Days60',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '61~90일',
      dataIndex: 'Days90',
      key: 'Days90',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '91~120일',
      dataIndex: 'Days120',
      key: 'Days120',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '120일 초과',
      dataIndex: 'Over120',
      key: 'Over120',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} type={val > 0 ? 'danger' : 'default'} />,
    },
    {
      title: '합계',
      dataIndex: 'Total',
      key: 'Total',
      width: 150,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
  ];

  return (
    <div>
      <Title level={4}>채권연령분석</Title>
      <Card>
        <FilterBar
          filters={filters}
          onSearch={handleSearch}
          onReset={handleReset}
          loading={isLoading}
          extra={
            <ExportButton
              onExport={() => {}}
              disabled={!data?.data?.length}
            />
          }
        />
        <DataTable
          columns={columns}
          data={data?.data || []}
          loading={isLoading}
          rowKey="CsCode"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default AgingAnalysisPage;
