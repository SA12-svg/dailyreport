import React, { useState } from 'react';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { taxApi } from '../../api/tax.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const SummaryTablePage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    arApGubun: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['tax', 'summary-table', searchParams],
    queryFn: () => taxApi.getSummaryTable(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 92 },
    {
      type: 'select',
      key: 'arApGubun',
      label: 'AR/AP 구분',
      options: [
        { value: 'AR', label: '매출(AR)' },
        { value: 'AP', label: '매입(AP)' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYYMMDD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYYMMDD') : prev.dateTo,
      arApGubun: values.arApGubun || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      arApGubun: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '거래처',
      dataIndex: 'CsCode',
      key: 'CsCode',
      width: 150,
      render: (val: string) => val?.trim(),
    },
    {
      title: '건수',
      dataIndex: 'InvoiceCount',
      key: 'InvoiceCount',
      width: 100,
      align: 'right' as const,
      render: (val: number) => (val || 0).toLocaleString(),
    },
    {
      title: '공급가액',
      dataIndex: 'SupplyAmnt',
      key: 'SupplyAmnt',
      width: 160,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '세액',
      dataIndex: 'VatAmnt',
      key: 'VatAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '합계',
      dataIndex: 'TotalAmnt',
      key: 'TotalAmnt',
      width: 160,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
  ];

  return (
    <div>
      <Title level={4}>세금계산서 합계표</Title>
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
          rowKey={(record: any) => record.CsCode}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default SummaryTablePage;
