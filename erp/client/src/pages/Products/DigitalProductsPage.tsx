import React, { useState } from 'react';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import DataTable from '../../components/DataTable';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { productsApi } from '../../api/products.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const displayLabels: Record<string, { label: string; color: string }> = {
  Y: { label: '표시', color: 'green' },
  N: { label: '숨김', color: 'default' },
};

const DigitalProductsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    categoryCode: undefined as string | undefined,
    brandCode: undefined as string | undefined,
    displayYN: undefined as string | undefined,
    keyword: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['products', 'digital', searchParams],
    queryFn: () => productsApi.getDigitalProducts(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    {
      type: 'input',
      key: 'keyword',
      label: '상품명/코드',
      placeholder: 'MC코드 또는 상품명',
    },
    {
      type: 'select',
      key: 'displayYN',
      label: '표시상태',
      options: [
        { value: 'Y', label: '표시' },
        { value: 'N', label: '숨김' },
      ],
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    setSearchParams((prev) => ({
      ...prev,
      keyword: values.keyword || undefined,
      categoryCode: values.categoryCode || undefined,
      brandCode: values.brandCode || undefined,
      displayYN: values.displayYN || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      categoryCode: undefined,
      brandCode: undefined,
      displayYN: undefined,
      keyword: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '상품ID',
      dataIndex: 'Product_ID',
      key: 'Product_ID',
      width: 80,
    },
    {
      title: '상품코드',
      dataIndex: 'Product_Code',
      key: 'Product_Code',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '상품명',
      dataIndex: 'Product_Name',
      key: 'Product_Name',
      width: 200,
      render: (val: string) => val?.trim(),
    },
    {
      title: '카테고리',
      dataIndex: 'Product_Category_Code',
      key: 'Product_Category_Code',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '브랜드',
      dataIndex: 'Product_Brand_Code',
      key: 'Product_Brand_Code',
      width: 100,
      render: (val: string) => val?.trim(),
    },
    {
      title: '가격',
      dataIndex: 'Price',
      key: 'Price',
      width: 100,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '할인율',
      dataIndex: 'Discount_Rate',
      key: 'Discount_Rate',
      width: 80,
      align: 'right' as const,
      render: (val: number) => val ? `${val}%` : '-',
    },
    {
      title: '할인가',
      dataIndex: 'Discount_Price',
      key: 'Discount_Price',
      width: 100,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '표시',
      dataIndex: 'Display_YN',
      key: 'Display_YN',
      width: 70,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = displayLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '등록일',
      dataIndex: 'Regist_DateTime',
      key: 'Regist_DateTime',
      width: 120,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>MC시리즈 디지털 상품</Title>
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
          rowKey="Product_ID"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default DigitalProductsPage;
