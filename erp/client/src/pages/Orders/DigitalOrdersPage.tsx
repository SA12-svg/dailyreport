import React, { useState } from 'react';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { ordersApi } from '../../api/orders.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const statusLabels: Record<string, { label: string; color: string }> = {
  ORDER: { label: '주문', color: 'blue' },
  PAYMENT: { label: '결제완료', color: 'green' },
  CANCEL: { label: '취소', color: 'red' },
  REFUND: { label: '환불', color: 'orange' },
};

const paymentStatusLabels: Record<string, { label: string; color: string }> = {
  PAID: { label: '결제완료', color: 'green' },
  UNPAID: { label: '미결제', color: 'default' },
  REFUNDED: { label: '환불', color: 'red' },
};

const DigitalOrdersPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYY-MM-DD'),
    dateTo: dayjs().format('YYYY-MM-DD'),
    orderStatusCode: undefined as string | undefined,
    paymentStatusCode: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['orders', 'digital', searchParams],
    queryFn: () => ordersApi.getDigitalOrders(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'orderStatusCode',
      label: '주문상태',
      options: Object.entries(statusLabels).map(([value, { label }]) => ({ value, label })),
    },
    {
      type: 'select',
      key: 'paymentStatusCode',
      label: '결제상태',
      options: Object.entries(paymentStatusLabels).map(([value, { label }]) => ({ value, label })),
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYY-MM-DD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYY-MM-DD') : prev.dateTo,
      orderStatusCode: values.orderStatusCode || undefined,
      paymentStatusCode: values.paymentStatusCode || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYY-MM-DD'),
      dateTo: dayjs().format('YYYY-MM-DD'),
      orderStatusCode: undefined,
      paymentStatusCode: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '주문ID',
      dataIndex: 'Order_ID',
      key: 'Order_ID',
      width: 100,
    },
    {
      title: '주문코드',
      dataIndex: 'Order_Code',
      key: 'Order_Code',
      width: 180,
      render: (val: string) => val?.trim(),
    },
    {
      title: '주문자',
      dataIndex: 'Name',
      key: 'Name',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '이메일',
      dataIndex: 'Email',
      key: 'Email',
      width: 160,
      render: (val: string) => val?.trim(),
    },
    {
      title: '결제금액',
      dataIndex: 'Payment_Price',
      key: 'Payment_Price',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '주문상태',
      dataIndex: 'Order_Status_Code',
      key: 'Order_Status_Code',
      width: 100,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = statusLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '결제상태',
      dataIndex: 'Payment_Status_Code',
      key: 'Payment_Status_Code',
      width: 100,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = paymentStatusLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '경로',
      dataIndex: 'Order_Path',
      key: 'Order_Path',
      width: 60,
      render: (val: string) => val?.trim(),
    },
    {
      title: '주문일시',
      dataIndex: 'Order_DateTime',
      key: 'Order_DateTime',
      width: 160,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD HH:mm') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>디지털 주문 조회</Title>
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
          rowKey="Order_ID"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default DigitalOrdersPage;
