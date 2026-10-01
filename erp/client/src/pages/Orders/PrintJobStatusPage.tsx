import React, { useState } from 'react';
import { Card, Tag, Typography, Segmented } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { ordersApi } from '../../api/orders.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const ptypeLabels: Record<string, { label: string; color: string }> = {
  C: { label: '카드', color: 'blue' },
  E: { label: '봉투/내지', color: 'green' },
};

type ViewMode = 'detail' | 'summary';

const PrintJobStatusPage: React.FC = () => {
  const [viewMode, setViewMode] = useState<ViewMode>('summary');
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    dateTo: dayjs().format('YYYY-MM-DD'),
    ptype: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['orders', 'printjobs', searchParams, viewMode],
    queryFn: () => ordersApi.getPrintJobs({ ...searchParams, view: viewMode }),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'ptype',
      label: '인쇄유형',
      options: Object.entries(ptypeLabels).map(([value, { label }]) => ({ value, label })),
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYY-MM-DD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYY-MM-DD') : prev.dateTo,
      ptype: values.ptype || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
      dateTo: dayjs().format('YYYY-MM-DD'),
      ptype: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const detailColumns = [
    {
      title: '인쇄일',
      dataIndex: 'pdate',
      key: 'pdate',
      width: 110,
    },
    {
      title: '생성일',
      dataIndex: 'cdate',
      key: 'cdate',
      width: 110,
    },
    {
      title: '차수',
      dataIndex: 'cseq',
      key: 'cseq',
      width: 70,
    },
    {
      title: '유형',
      dataIndex: 'ptype',
      key: 'ptype',
      width: 90,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = ptypeLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '수량',
      dataIndex: 'pcount',
      key: 'pcount',
      width: 90,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '프린터',
      dataIndex: 'printer_id',
      key: 'printer_id',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '카드코드',
      dataIndex: 'card_code',
      key: 'card_code',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '카드명',
      dataIndex: 'card_name',
      key: 'card_name',
      ellipsis: true,
      render: (val: string) => val?.trim(),
    },
  ];

  const summaryColumns = [
    {
      title: '인쇄일',
      dataIndex: 'pdate',
      key: 'pdate',
      width: 120,
    },
    {
      title: '총 작업수',
      dataIndex: 'total_jobs',
      key: 'total_jobs',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '총 수량',
      dataIndex: 'total_quantity',
      key: 'total_quantity',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '카드 작업',
      dataIndex: 'card_types',
      key: 'card_types',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '봉투/내지 작업',
      dataIndex: 'envelope_types',
      key: 'envelope_types',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
  ];

  const columns = viewMode === 'summary' ? summaryColumns : detailColumns;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>인쇄작업 현황</Title>
        <Segmented
          options={[
            { label: '일별 요약', value: 'summary' },
            { label: '상세 내역', value: 'detail' },
          ]}
          value={viewMode}
          onChange={(val) => setViewMode(val as ViewMode)}
        />
      </div>
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
          rowKey={viewMode === 'summary' ? 'pdate' : (record: any) => `${record.cdate}-${record.cseq}-${record.pid}`}
          pagination={viewMode === 'detail' ? data?.pagination : undefined}
          onPageChange={viewMode === 'detail' ? (page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize })) : undefined}
        />
      </Card>
    </div>
  );
};

export default PrintJobStatusPage;
