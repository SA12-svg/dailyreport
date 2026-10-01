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

const reqStatusLabels: Record<string, { label: string; color: string }> = {
  A: { label: '진행', color: 'processing' },
  B: { label: '보류', color: 'warning' },
  C: { label: '완료', color: 'success' },
};

const RequisitionListPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    reqStatus: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', 'requisitions', searchParams],
    queryFn: () => inventoryApi.getRequisitions(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'reqStatus',
      label: '상태',
      options: [
        { value: 'A', label: '진행' },
        { value: 'B', label: '보류' },
        { value: 'C', label: '완료' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYYMMDD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYYMMDD') : prev.dateTo,
      reqStatus: values.reqStatus || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      reqStatus: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '청구번호',
      dataIndex: 'ReqNo',
      key: 'ReqNo',
      width: 160,
      render: (val: string) => val?.trim(),
    },
    {
      title: '청구일자',
      dataIndex: 'ReqDate',
      key: 'ReqDate',
      width: 110,
      render: (date: string) => {
        const d = date?.trim();
        return d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';
      },
    },
    {
      title: '예상입고일',
      dataIndex: 'ExpectDate',
      key: 'ExpectDate',
      width: 110,
      render: (date: string) => {
        const d = date?.trim();
        return d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';
      },
    },
    {
      title: '상태',
      dataIndex: 'ReqStatus',
      key: 'ReqStatus',
      width: 80,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = reqStatusLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '요청부서',
      dataIndex: 'ReqDept',
      key: 'ReqDept',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '요청자',
      dataIndex: 'ReqEmp',
      key: 'ReqEmp',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '비고',
      dataIndex: 'ReqDescr',
      key: 'ReqDescr',
      ellipsis: true,
      render: (val: string) => val?.trim(),
    },
  ];

  return (
    <div>
      <Title level={4}>청구요청 목록</Title>
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
          rowKey="ReqNo"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default RequisitionListPage;
