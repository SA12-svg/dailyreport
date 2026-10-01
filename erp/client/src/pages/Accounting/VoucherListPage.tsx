import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { accountingApi } from '../../api/accounting.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const docTypeLabels: Record<string, { label: string; color: string }> = {
  '01': { label: '일반전표', color: 'blue' },
  '02': { label: '매입전표', color: 'green' },
  '03': { label: '매출전표', color: 'orange' },
  '04': { label: '결산전표', color: 'purple' },
};

const statusLabels: Record<string, { label: string; color: string }> = {
  '0': { label: '미승인', color: 'default' },
  '1': { label: '승인', color: 'success' },
  '9': { label: '반려', color: 'error' },
};

const filters: FilterConfig[] = [
  { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 31 },
  {
    type: 'select',
    key: 'docType',
    label: '전표유형',
    options: [
      { value: '01', label: '일반전표' },
      { value: '02', label: '매입전표' },
      { value: '03', label: '매출전표' },
      { value: '04', label: '결산전표' },
    ],
  },
  {
    type: 'select',
    key: 'status',
    label: '승인상태',
    options: [
      { value: '0', label: '미승인' },
      { value: '1', label: '승인' },
      { value: '9', label: '반려' },
    ],
  },
];

const VoucherListPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useState({
    dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
    docType: undefined as string | undefined,
    status: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['accounting', 'vouchers', searchParams],
    queryFn: () => accountingApi.getVouchers(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    setSearchParams((prev) => ({
      ...prev,
      dateFrom: start ? dayjs(start).format('YYYYMMDD') : prev.dateFrom,
      dateTo: end ? dayjs(end).format('YYYYMMDD') : prev.dateTo,
      docType: values.docType || undefined,
      status: values.status || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      dateFrom: dayjs().startOf('month').format('YYYYMMDD'),
      dateTo: dayjs().format('YYYYMMDD'),
      docType: undefined,
      status: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '전표번호',
      dataIndex: 'DocNo',
      key: 'DocNo',
      width: 140,
    },
    {
      title: '전표유형',
      dataIndex: 'DocType',
      key: 'DocType',
      width: 100,
      render: (type: string) => {
        const info = docTypeLabels[type];
        return info ? <Tag color={info.color}>{info.label}</Tag> : type;
      },
    },
    {
      title: '전표일자',
      dataIndex: 'RelDate',
      key: 'RelDate',
      width: 110,
      render: (date: string) =>
        date ? `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)}` : '',
    },
    {
      title: '적요',
      dataIndex: 'Remark',
      key: 'Remark',
      ellipsis: true,
    },
    {
      title: '금액',
      dataIndex: 'TotalAmt',
      key: 'TotalAmt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '승인상태',
      dataIndex: 'Status',
      key: 'Status',
      width: 90,
      render: (status: string) => {
        const info = statusLabels[status];
        return info ? <Tag color={info.color}>{info.label}</Tag> : status;
      },
    },
    {
      title: '등록자',
      dataIndex: 'RegUser',
      key: 'RegUser',
      width: 100,
    },
  ];

  return (
    <div>
      <Title level={4}>전표 목록</Title>
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
          rowKey="DocNo"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
          onRowClick={(record: any) => navigate(`/accounting/vouchers/${record.DocNo}`)}
        />
      </Card>
    </div>
  );
};

export default VoucherListPage;
