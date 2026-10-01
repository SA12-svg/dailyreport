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

const TrackingSearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    trackingNo: '',
    deliveryCom: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['delivery', 'tracking', searchParams],
    queryFn: () => deliveryApi.searchTracking(searchParams),
    enabled: searchParams.trackingNo.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'input', key: 'trackingNo', label: '송장번호', required: true },
    {
      type: 'select',
      key: 'deliveryCom',
      label: '택배사',
      options: [
        { value: 'CJ', label: 'CJ대한통운' },
        { value: 'HANJIN', label: '한진택배' },
        { value: 'LOTTE', label: '롯데택배' },
        { value: 'POST', label: '우체국택배' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    setSearchParams((prev) => ({
      ...prev,
      trackingNo: values.trackingNo || '',
      deliveryCom: values.deliveryCom || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      trackingNo: '',
      deliveryCom: undefined,
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
      title: '택배사',
      dataIndex: 'delivery_com',
      key: 'delivery_com',
      width: 120,
    },
    {
      title: '송장번호',
      dataIndex: 'delivery_code_num',
      key: 'delivery_code_num',
      width: 180,
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
      title: '배송주소',
      dataIndex: 'ADDR',
      key: 'ADDR',
      width: 200,
      ellipsis: true,
      render: (val: string) => val?.trim(),
    },
    {
      title: '배송일',
      dataIndex: 'DELIVERY_DATE',
      key: 'DELIVERY_DATE',
      width: 120,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD') : '',
    },
    {
      title: '등록일',
      dataIndex: 'reg_date',
      key: 'reg_date',
      width: 160,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD HH:mm') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>송장번호 조회</Title>
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
          rowKey={(record: any) => `${record.delivery_id}-${record.delivery_code_num}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default TrackingSearchPage;
