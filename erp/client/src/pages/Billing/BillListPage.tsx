import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { billingApi } from '../../api/billing.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const arApLabels: Record<string, { label: string; color: string }> = {
  AR: { label: '매출(AR)', color: 'blue' },
  AP: { label: '매입(AP)', color: 'orange' },
  Ax: { label: '기타', color: 'default' },
};

const BillListPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    arApGubun: undefined as string | undefined,
    csCode: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data: customers } = useQuery({
    queryKey: ['billing', 'customers'],
    queryFn: () => billingApi.getCustomers(),
    staleTime: 30 * 60 * 1000,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['billing', 'bills', searchParams],
    queryFn: () => billingApi.getBills(searchParams),
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
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      arApGubun: undefined,
      csCode: undefined,
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
        const info = arApLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '청구일',
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
      title: '청구금액',
      dataIndex: 'BillAmnt',
      key: 'BillAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: 'VAT',
      dataIndex: 'VatAmnt',
      key: 'VatAmnt',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '수금액',
      dataIndex: 'MoneySumAmnt',
      key: 'MoneySumAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '비고',
      dataIndex: 'BillDescr',
      key: 'BillDescr',
      ellipsis: true,
      render: (val: string) => val?.trim(),
    },
  ];

  return (
    <div>
      <Title level={4}>매출매입 목록</Title>
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
          onRowClick={(record: any) =>
            navigate(`/billing/bills/${encodeURIComponent(record.BillNo.trim())}?arApGubun=${record.ArApGubun.trim()}`)
          }
        />
      </Card>
    </div>
  );
};

export default BillListPage;
