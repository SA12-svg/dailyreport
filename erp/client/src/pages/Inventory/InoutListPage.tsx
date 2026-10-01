import React, { useState } from 'react';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import ExportButton from '../../components/ExportButton';
import { inventoryApi } from '../../api/inventory.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const inoutGubunLabels: Record<string, { label: string; color: string }> = {
  SO: { label: '출고', color: 'red' },
  SI: { label: '입고', color: 'green' },
  MO: { label: '자재출고', color: 'orange' },
  MI: { label: '자재입고', color: 'blue' },
};

const InoutListPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    inoutGubun: undefined as string | undefined,
    whCode: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data: warehouses } = useQuery({
    queryKey: ['inventory', 'warehouses'],
    queryFn: () => inventoryApi.getWarehouses(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', 'inout', searchParams],
    queryFn: () => inventoryApi.getInoutList(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'inoutGubun',
      label: '입출고구분',
      options: [
        { value: 'SO', label: '출고' },
        { value: 'SI', label: '입고' },
        { value: 'MO', label: '자재출고' },
        { value: 'MI', label: '자재입고' },
      ],
    },
    {
      type: 'select',
      key: 'whCode',
      label: '창고',
      options: (warehouses || []).map((wh: string) => ({ value: wh, label: wh })),
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYYMMDD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYYMMDD') : prev.dateTo,
      inoutGubun: values.inoutGubun || undefined,
      whCode: values.whCode || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      inoutGubun: undefined,
      whCode: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '전표번호',
      dataIndex: 'InoutNo',
      key: 'InoutNo',
      width: 160,
      render: (val: string) => val?.trim(),
    },
    {
      title: '구분',
      dataIndex: 'InoutGubun',
      key: 'InoutGubun',
      width: 100,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = inoutGubunLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '일자',
      dataIndex: 'InoutDate',
      key: 'InoutDate',
      width: 110,
      render: (date: string) => {
        const d = date?.trim();
        return d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';
      },
    },
    {
      title: '사유코드',
      dataIndex: 'SysCase',
      key: 'SysCase',
      width: 90,
      render: (val: string) => val?.trim(),
    },
    {
      title: '거래처',
      dataIndex: 'InoutPlace',
      key: 'InoutPlace',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '비고',
      dataIndex: 'InoutDescr',
      key: 'InoutDescr',
      ellipsis: true,
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
      <Title level={4}>입출고 내역</Title>
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
          rowKey={(record: any) => `${record.InoutNo}-${record.InoutGubun}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default InoutListPage;
