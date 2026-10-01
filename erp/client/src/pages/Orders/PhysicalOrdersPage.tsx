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

const statusLabels: Record<number, { label: string; color: string }> = {
  1: { label: '접수', color: 'blue' },
  2: { label: '인쇄중', color: 'processing' },
  3: { label: '인쇄완료', color: 'cyan' },
  4: { label: '배송중', color: 'orange' },
  5: { label: '배송완료', color: 'green' },
  9: { label: '취소', color: 'red' },
};

const PhysicalOrdersPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYY-MM-DD'),
    dateTo: dayjs().format('YYYY-MM-DD'),
    statusSeq: undefined as number | undefined,
    orderType: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['orders', 'physical', searchParams],
    queryFn: () => ordersApi.getPhysicalOrders(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'statusSeq',
      label: '주문상태',
      options: Object.entries(statusLabels).map(([value, { label }]) => ({ value, label })),
    },
    {
      type: 'select',
      key: 'orderType',
      label: '주문유형',
      options: [
        { value: 'card', label: '청첩장' },
        { value: 'envelope', label: '봉투' },
        { value: 'sticker', label: '스티커' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYY-MM-DD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYY-MM-DD') : prev.dateTo,
      statusSeq: values.statusSeq ? parseInt(values.statusSeq, 10) : undefined,
      orderType: values.orderType || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYY-MM-DD'),
      dateTo: dayjs().format('YYYY-MM-DD'),
      statusSeq: undefined,
      orderType: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '주문번호',
      dataIndex: 'order_seq',
      key: 'order_seq',
      width: 110,
    },
    {
      title: '주문유형',
      dataIndex: 'order_type',
      key: 'order_type',
      width: 90,
      render: (val: string) => val?.trim(),
    },
    {
      title: '판매구분',
      dataIndex: 'sales_Gubun',
      key: 'sales_Gubun',
      width: 90,
      render: (val: string) => val?.trim(),
    },
    {
      title: '결제유형',
      dataIndex: 'pay_Type',
      key: 'pay_Type',
      width: 90,
      render: (val: string) => val?.trim(),
    },
    {
      title: '주문자',
      dataIndex: 'order_name',
      key: 'order_name',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '이메일',
      dataIndex: 'order_email',
      key: 'order_email',
      width: 160,
      render: (val: string) => val?.trim(),
    },
    {
      title: '총금액',
      dataIndex: 'last_total_price',
      key: 'last_total_price',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '실결제액',
      dataIndex: 'settle_price',
      key: 'settle_price',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '상태',
      dataIndex: 'status_seq',
      key: 'status_seq',
      width: 90,
      render: (val: number) => {
        const info = statusLabels[val];
        return info ? <Tag color={info.color}>{info.label}</Tag> : val;
      },
    },
    {
      title: '주문일',
      dataIndex: 'order_date',
      key: 'order_date',
      width: 160,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD HH:mm') : '',
    },
    {
      title: '발송일',
      dataIndex: 'src_send_date',
      key: 'src_send_date',
      width: 110,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>실물 주문 조회</Title>
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
          rowKey="order_seq"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default PhysicalOrdersPage;
