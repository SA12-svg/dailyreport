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

const CollectionStatusPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    csCode: undefined as string | undefined,
    payCode: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data: customers } = useQuery({
    queryKey: ['billing', 'customers'],
    queryFn: () => billingApi.getCustomers(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['billing', 'collections', searchParams],
    queryFn: () => billingApi.getCollections(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'csCode',
      label: '거래처',
      options: (customers || []).map((cs: string) => ({ value: cs, label: cs })),
    },
    {
      type: 'select',
      key: 'payCode',
      label: '수금방법',
      options: [
        { value: '01', label: '현금' },
        { value: '02', label: '어음' },
        { value: '03', label: '계좌이체' },
        { value: '04', label: '카드' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYYMMDD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYYMMDD') : prev.dateTo,
      csCode: values.csCode || undefined,
      payCode: values.payCode || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      csCode: undefined,
      payCode: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '수금일',
      dataIndex: 'AllocDate',
      key: 'AllocDate',
      width: 110,
      render: (date: string) => {
        const d = date?.trim();
        return d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';
      },
    },
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
      title: '수금방법',
      dataIndex: 'PayCode',
      key: 'PayCode',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '수금액',
      dataIndex: 'AllocAmnt',
      key: 'AllocAmnt',
      width: 150,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
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
      <Title level={4}>수금현황</Title>
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
          rowKey={(record: any, index: number) => `${record.OriginNo}-${record.AllocDate}-${index}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default CollectionStatusPage;
