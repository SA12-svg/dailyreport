import React, { useState } from 'react';
import { Card, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { inventoryApi } from '../../api/inventory.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const ValuationPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    invMonth: dayjs().subtract(1, 'month').format('YYYYMM'),
    invStatus: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', 'valuation', searchParams],
    queryFn: () => inventoryApi.getValuation(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'month', key: 'invMonth', label: '평가월', required: true },
    {
      type: 'select',
      key: 'invStatus',
      label: '재고상태',
      options: [
        { value: 'GOOD', label: '양품' },
        { value: 'POOR', label: '불량' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    setSearchParams((prev) => ({
      ...prev,
      invMonth: values.invMonth ? dayjs(values.invMonth).format('YYYYMM') : prev.invMonth,
      invStatus: values.invStatus || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      invMonth: dayjs().subtract(1, 'month').format('YYYYMM'),
      invStatus: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '품목코드',
      dataIndex: 'ItemCode',
      key: 'ItemCode',
      width: 140,
      render: (val: string) => val?.trim(),
    },
    {
      title: '상태',
      dataIndex: 'InvStatus',
      key: 'InvStatus',
      width: 80,
      render: (val: string) => val?.trim() === 'GOOD' ? '양품' : '불량',
    },
    {
      title: '기초수량',
      dataIndex: 'SQty',
      key: 'SQty',
      width: 110,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '기초금액',
      dataIndex: 'SAmnt',
      key: 'SAmnt',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '입고수량',
      dataIndex: 'InQty',
      key: 'InQty',
      width: 110,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '입고금액',
      dataIndex: 'InAmnt',
      key: 'InAmnt',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '표준단가',
      dataIndex: 'StdPrice',
      key: 'StdPrice',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '기말수량',
      dataIndex: 'OhQty',
      key: 'OhQty',
      width: 110,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '기말금액',
      dataIndex: 'OhAmnt',
      key: 'OhAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
  ];

  return (
    <div>
      <Title level={4}>재고평가</Title>
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
          rowKey={(record: any) => `${record.ItemCode}-${record.InvStatus}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default ValuationPage;
