import React, { useState } from 'react';
import { Card, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { billingApi } from '../../api/billing.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const OutstandingDetailPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
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
    queryKey: ['billing', 'outstanding', searchParams],
    queryFn: () => billingApi.getOutstanding(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
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
      csCode: values.csCode || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      csCode: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '청구번호',
      dataIndex: 'OriginNo',
      key: 'OriginNo',
      width: 180,
      render: (val: string) => val?.trim(),
    },
    {
      title: '거래처',
      dataIndex: 'CsCode',
      key: 'CsCode',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '예정일',
      dataIndex: 'ExpectDate',
      key: 'ExpectDate',
      width: 110,
      render: (date: string) => {
        const d = date?.trim();
        return d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';
      },
    },
    {
      title: '예정금액',
      dataIndex: 'ExpectAmnt',
      key: 'ExpectAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '미수잔액',
      dataIndex: 'ExpectRemainAmnt',
      key: 'ExpectRemainAmnt',
      width: 150,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} type={val > 0 ? 'danger' : 'default'} />,
    },
    {
      title: '채권계정',
      dataIndex: 'ArApAcc',
      key: 'ArApAcc',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '주문번호',
      dataIndex: 'C_JumunNo',
      key: 'C_JumunNo',
      width: 140,
      render: (val: string) => val?.trim(),
    },
  ];

  return (
    <div>
      <Title level={4}>미수금 상세</Title>
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
          rowKey={(record: any, index: number) => `${record.OriginNo}-${index}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default OutstandingDetailPage;
