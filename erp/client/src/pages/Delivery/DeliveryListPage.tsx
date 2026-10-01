import React, { useState } from 'react';
import { Card, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import ExportButton from '../../components/ExportButton';
import { deliveryApi } from '../../api/delivery.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const DeliveryListPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYY-MM-DD'),
    dateTo: dayjs().format('YYYY-MM-DD'),
    orderSeq: undefined as number | undefined,
    keyword: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['delivery', 'list', searchParams],
    queryFn: () => deliveryApi.getDeliveryList(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '배송일 기간', required: true, maxDays: 31 },
    { type: 'input', key: 'orderSeq', label: '주문번호' },
    { type: 'input', key: 'keyword', label: '수령인명' },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYY-MM-DD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYY-MM-DD') : prev.dateTo,
      orderSeq: values.orderSeq ? parseInt(values.orderSeq, 10) : undefined,
      keyword: values.keyword || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYY-MM-DD'),
      dateTo: dayjs().format('YYYY-MM-DD'),
      orderSeq: undefined,
      keyword: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '주문번호',
      dataIndex: 'ORDER_SEQ',
      key: 'ORDER_SEQ',
      width: 110,
    },
    {
      title: '배송순번',
      dataIndex: 'DELIVERY_SEQ',
      key: 'DELIVERY_SEQ',
      width: 90,
    },
    {
      title: '수령인',
      dataIndex: 'NAME',
      key: 'NAME',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '연락처',
      dataIndex: 'PHONE',
      key: 'PHONE',
      width: 140,
      render: (val: string) => val?.trim(),
    },
    {
      title: '휴대폰',
      dataIndex: 'HPHONE',
      key: 'HPHONE',
      width: 140,
      render: (val: string) => val?.trim(),
    },
    {
      title: '배송주소',
      dataIndex: 'ADDR',
      key: 'ADDR',
      width: 200,
      ellipsis: true,
      render: (val: string) => val?.trim(),
    },
    {
      title: '우편번호',
      dataIndex: 'ZIPCODE',
      key: 'ZIPCODE',
      width: 80,
    },
    {
      title: '배송일',
      dataIndex: 'DELIVERY_DATE',
      key: 'DELIVERY_DATE',
      width: 120,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>배송 목록 조회</Title>
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
          rowKey={(record: any) => `${record.ORDER_SEQ}-${record.DELIVERY_SEQ}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default DeliveryListPage;
