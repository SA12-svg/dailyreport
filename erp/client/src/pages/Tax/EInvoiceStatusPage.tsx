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

const EInvoiceStatusPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    arApGubun: undefined as string | undefined,
    csCode: undefined as string | undefined,
    hasInvoiceNo: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data: customers } = useQuery({
    queryKey: ['tax', 'customers'],
    queryFn: () => taxApi.getCustomers(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['tax', 'e-invoices', searchParams],
    queryFn: () => taxApi.getEInvoices(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
    {
      type: 'select',
      key: 'arApGubun',
      label: 'AR/AP 구분',
      options: [
        { value: 'AR', label: '매출(AR)' },
        { value: 'AP', label: '매입(AP)' },
      ],
    },
    {
      type: 'select',
      key: 'hasInvoiceNo',
      label: '발행상태',
      options: [
        { value: 'Y', label: '발행완료' },
        { value: 'N', label: '미발행' },
      ],
    },
    {
      type: 'select',
      key: 'csCode',
      label: '거래처',
      options: (customers || []).map((cs: string) => ({ value: cs, label: cs })),
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYYMMDD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYYMMDD') : prev.dateTo,
      arApGubun: values.arApGubun || undefined,
      csCode: values.csCode || undefined,
      hasInvoiceNo: values.hasInvoiceNo || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      arApGubun: undefined,
      csCode: undefined,
      hasInvoiceNo: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '청구번호',
      dataIndex: 'BillNo',
      key: 'BillNo',
      width: 180,
      render: (val: string) => val?.trim(),
    },
    {
      title: 'AR/AP',
      dataIndex: 'ArApGubun',
      key: 'ArApGubun',
      width: 100,
      render: (val: string) => {
        const trimmed = val?.trim();
        return trimmed === 'AR'
          ? <Tag color="blue">매출(AR)</Tag>
          : <Tag color="orange">매입(AP)</Tag>;
      },
    },
    {
      title: '발행일',
      dataIndex: 'BillDate',
      key: 'BillDate',
      width: 110,
      render: (date: string) => {
        const d = date?.trim();
        return d ? `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}` : '';
      },
    },
    {
      title: '거래처',
      dataIndex: 'CsCode',
      key: 'CsCode',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '공급가액',
      dataIndex: 'BillAmnt',
      key: 'BillAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '세액',
      dataIndex: 'VatAmnt',
      key: 'VatAmnt',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '승인번호',
      dataIndex: 'InvoiceNo',
      key: 'InvoiceNo',
      width: 200,
      render: (val: string) => val?.trim() || '-',
    },
    {
      title: '상태',
      dataIndex: 'EInvoiceStatus',
      key: 'EInvoiceStatus',
      width: 100,
      render: (val: string) => {
        const trimmed = val?.trim();
        return trimmed === '발행완료'
          ? <Tag color="green">발행완료</Tag>
          : <Tag color="red">미발행</Tag>;
      },
    },
  ];

  return (
    <div>
      <Title level={4}>전자세금계산서 현황</Title>
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
          rowKey={(record: any) => `${record.BillNo}-${record.ArApGubun}`}
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default EInvoiceStatusPage;
