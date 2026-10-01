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

const brandLabels: Record<string, string> = {
  B: '바른손카드',
  C: '더카드',
  S: '비핸즈',
  X: '디어디어',
  W: 'W카드',
  N: '네이처',
  I: '이니스',
  H: '비핸즈프리미엄',
  F: '플라워',
  D: '디자인카드',
  P: '프리미어',
  M: '모바일',
  G: '글로벌',
  U: '유니세프',
  Y: '유니크',
  K: '비케이',
  T: '프리미어더카드',
  A: '기타',
};

const divLabels: Record<string, string> = {
  A01: '일반청첩장',
  A02: '봉투',
  A03: '감사장',
  A04: '스티커',
  A05: '식권/부속',
  B01: '포토북/앨범',
};

const displayLabels: Record<string, { label: string; color: string }> = {
  Y: { label: '표시', color: 'green' },
  N: { label: '숨김', color: 'default' },
};

const PhysicalProductsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useState({
    cardBrand: undefined as string | undefined,
    cardDiv: undefined as string | undefined,
    displayYorn: undefined as string | undefined,
    keyword: undefined as string | undefined,
    page: 1,
    pageSize: 20,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['products', 'physical', searchParams],
    queryFn: () => productsApi.getPhysicalProducts(searchParams),
    staleTime: 5 * 60 * 1000,
  });

  const filters: FilterConfig[] = [
    {
      type: 'input',
      key: 'keyword',
      label: '카드명/코드',
      placeholder: '카드코드 또는 카드명',
    },
    {
      type: 'select',
      key: 'cardBrand',
      label: '브랜드',
      options: Object.entries(brandLabels).map(([value, label]) => ({ value, label })),
    },
    {
      type: 'select',
      key: 'cardDiv',
      label: '카테고리',
      options: Object.entries(divLabels).map(([value, label]) => ({ value, label })),
    },
    {
      type: 'select',
      key: 'displayYorn',
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
      cardBrand: values.cardBrand || undefined,
      cardDiv: values.cardDiv || undefined,
      displayYorn: values.displayYorn || undefined,
      page: 1,
    }));
  };

  const handleReset = () => {
    setSearchParams({
      cardBrand: undefined,
      cardDiv: undefined,
      displayYorn: undefined,
      keyword: undefined,
      page: 1,
      pageSize: 20,
    });
  };

  const columns = [
    {
      title: '카드순번',
      dataIndex: 'Card_Seq',
      key: 'Card_Seq',
      width: 90,
    },
    {
      title: '브랜드',
      dataIndex: 'CardBrand',
      key: 'CardBrand',
      width: 120,
      render: (val: string) => {
        const trimmed = val?.trim();
        return brandLabels[trimmed] || trimmed;
      },
    },
    {
      title: '카드코드',
      dataIndex: 'Card_Code',
      key: 'Card_Code',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '카테고리',
      dataIndex: 'Card_Div',
      key: 'Card_Div',
      width: 110,
      render: (val: string) => {
        const trimmed = val?.trim();
        return divLabels[trimmed] || trimmed;
      },
    },
    {
      title: '카드명',
      dataIndex: 'Card_Name',
      key: 'Card_Name',
      width: 200,
      render: (val: string) => val?.trim(),
    },
    {
      title: '단가',
      dataIndex: 'Card_Price',
      key: 'Card_Price',
      width: 100,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '세트가',
      dataIndex: 'CardSet_Price',
      key: 'CardSet_Price',
      width: 100,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '원가',
      dataIndex: 'Cost_Price',
      key: 'Cost_Price',
      width: 100,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '최소수량',
      dataIndex: 'Unit_Min',
      key: 'Unit_Min',
      width: 80,
      align: 'right' as const,
    },
    {
      title: '표시',
      dataIndex: 'DISPLAY_YORN',
      key: 'DISPLAY_YORN',
      width: 70,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = displayLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: 'ERP코드',
      dataIndex: 'Card_ERPCode',
      key: 'Card_ERPCode',
      width: 110,
      render: (val: string) => val?.trim(),
    },
    {
      title: '등록일',
      dataIndex: 'RegDate',
      key: 'RegDate',
      width: 110,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>실물 카드 상품 목록</Title>
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
          rowKey="Card_Seq"
          pagination={data?.pagination}
          onPageChange={(page, pageSize) => setSearchParams((p) => ({ ...p, page, pageSize }))}
        />
      </Card>
    </div>
  );
};

export default PhysicalProductsPage;
