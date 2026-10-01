import React, { useState } from 'react';
import { Card, Tag, Typography, Input, Select, Space } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { ordersApi } from '../../api/orders.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const sourceLabels: Record<string, { label: string; color: string }> = {
  digital: { label: '디지털', color: 'blue' },
  physical: { label: '실물', color: 'green' },
};

const OrderSearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    keyword: '',
    source: 'all' as 'digital' | 'physical' | 'all',
    dateFrom: undefined as string | undefined,
    dateTo: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['orders', 'search', searchParams],
    queryFn: () => ordersApi.searchOrders(searchParams),
    enabled: searchParams.keyword.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'input', key: 'keyword', label: '주문번호/주문코드', required: true, placeholder: '주문번호 또는 주문코드 입력' },
    {
      type: 'select',
      key: 'source',
      label: '검색범위',
      options: [
        { value: 'all', label: '전체' },
        { value: 'digital', label: '디지털 주문' },
        { value: 'physical', label: '실물 주문' },
      ],
    },
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: false },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      keyword: values.keyword || '',
      source: values.source || 'all',
      dateFrom: start ? dayjs(start).format('YYYY-MM-DD') : undefined,
      dateTo: end ? dayjs(end).format('YYYY-MM-DD') : undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      keyword: '',
      source: 'all',
      dateFrom: undefined,
      dateTo: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '구분',
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (val: string) => {
        const info = sourceLabels[val];
        return info ? <Tag color={info.color}>{info.label}</Tag> : val;
      },
    },
    {
      title: '주문번호',
      dataIndex: 'order_id',
      key: 'order_id',
      width: 160,
    },
    {
      title: '주문일',
      dataIndex: 'order_date',
      key: 'order_date',
      width: 120,
    },
    {
      title: '주문자',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 100,
    },
    {
      title: '금액',
      dataIndex: 'amount',
      key: 'amount',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '상태',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (val: string) => val?.trim(),
    },
  ];

  return (
    <div>
      <Title level={4}>통합 주문 검색</Title>
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
          rowKey={(record: any) => `${record.source}-${record.order_id}`}
        />
      </Card>
    </div>
  );
};

export default OrderSearchPage;
