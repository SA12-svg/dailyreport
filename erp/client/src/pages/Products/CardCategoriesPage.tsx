import React, { useState } from 'react';
import { Card, Table, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import FilterBar from '../../components/FilterBar';
import { productsApi } from '../../api/products.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const divLabels: Record<string, string> = {
  A01: '일반청첩장',
  A02: '봉투',
  A03: '감사장',
  A04: '스티커',
  A05: '식권/부속',
  B01: '포토북/앨범',
};

const CardCategoriesPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    cardDiv: undefined as string | undefined,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['products', 'categories', searchParams],
    queryFn: () => productsApi.getCardCategories(searchParams),
    staleTime: 10 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    {
      type: 'select',
      key: 'cardDiv',
      label: '카테고리 구분',
      options: Object.entries(divLabels).map(([value, label]) => ({ value, label })),
    },
  ];

  const handleSearch = (values: Record<string, any>) => {
    setSearchParams({
      cardDiv: values.cardDiv || undefined,
    });
  };

  const handleReset = () => {
    setSearchParams({ cardDiv: undefined });
  };

  const columns = [
    {
      title: '종류 번호',
      dataIndex: 'CardKind_Seq',
      key: 'CardKind_Seq',
      width: 100,
    },
    {
      title: '종류명',
      dataIndex: 'CardKind_Name',
      key: 'CardKind_Name',
      width: 200,
      render: (val: string) => val?.trim(),
    },
    {
      title: '카드 수',
      dataIndex: 'card_count',
      key: 'card_count',
      width: 120,
      align: 'right' as const,
      render: (val: number) => (val || 0).toLocaleString(),
    },
  ];

  return (
    <div>
      <Title level={4}>카드 카테고리</Title>
      <Card>
        <FilterBar
          filters={filters}
          onSearch={handleSearch}
          onReset={handleReset}
          loading={isLoading}
        />
        <Table
          columns={columns}
          dataSource={data?.data || []}
          loading={isLoading}
          rowKey="CardKind_Seq"
          pagination={false}
          size="middle"
        />
      </Card>
    </div>
  );
};

export default CardCategoriesPage;
