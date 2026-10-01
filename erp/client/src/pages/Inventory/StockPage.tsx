import React, { useState } from 'react';
import { Card, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { inventoryApi } from '../../api/inventory.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const invStatusLabels: Record<string, string> = {
  GOOD: '양품',
  POOR: '불량',
};

const StockPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    whCode: undefined as string | undefined,
    invStatus: undefined as string | undefined,
    itemCode: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data: warehouses } = useQuery({
    queryKey: ['inventory', 'warehouses'],
    queryFn: () => inventoryApi.getWarehouses(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', 'stock', searchParams],
    queryFn: () => inventoryApi.getStock(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    {
      type: 'select',
      key: 'whCode',
      label: '창고',
      options: (warehouses || []).map((wh: string) => ({ value: wh, label: wh })),
    },
    {
      type: 'select',
      key: 'invStatus',
      label: '재고상태',
      options: [
        { value: 'GOOD', label: '양품' },
        { value: 'POOR', label: '불량' },
      ],
    },
    { type: 'input', key: 'itemCode', label: '품목코드' },
  ];

  const handleSearch = (values: Record<string, any>) => {
    setSearchParams((prev) => ({
      ...prev,
      whCode: values.whCode || undefined,
      invStatus: values.invStatus || undefined,
      itemCode: values.itemCode || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      whCode: undefined,
      invStatus: undefined,
      itemCode: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '창고',
      dataIndex: 'WhCode',
      key: 'WhCode',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '재고상태',
      dataIndex: 'InvStatus',
      key: 'InvStatus',
      width: 90,
      render: (val: string) => invStatusLabels[val?.trim()] || val,
    },
    {
      title: '품목코드',
      dataIndex: 'ItemCode',
      key: 'ItemCode',
      width: 140,
      render: (val: string) => val?.trim(),
    },
    {
      title: '재고수량',
      dataIndex: 'OhQty',
      key: 'OhQty',
      width: 130,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '재고금액',
      dataIndex: 'OhAmnt',
      key: 'OhAmnt',
      width: 150,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
  ];

  return (
    <div>
      <Title level={4}>현재재고 현황</Title>
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
          rowKey={(record: any) => `${record.WhCode}-${record.InvStatus}-${record.ItemCode}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default StockPage;
