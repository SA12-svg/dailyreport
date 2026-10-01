import React from 'react';
import { Card, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import DataTable from '../../components/DataTable';
import ExportButton from '../../components/ExportButton';
import { inventoryApi } from '../../api/inventory.api';

const { Title } = Typography;

const moduleLabels: Record<string, { label: string; color: string }> = {
  MM: { label: '자재관리', color: 'blue' },
  SM: { label: '판매관리', color: 'green' },
};

const MonthClosePage: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['inventory', 'month-close'],
    queryFn: () => inventoryApi.getMonthClose(),
    staleTime: 10 * 60 * 1000,
  });

  const columns = [
    {
      title: '마감월',
      dataIndex: 'CloseMonth',
      key: 'CloseMonth',
      width: 120,
      render: (val: string) => {
        const v = val?.trim();
        return v ? `${v.substring(0, 4)}-${v.substring(4, 6)}` : '';
      },
    },
    {
      title: '모듈',
      dataIndex: 'ModuleGubun',
      key: 'ModuleGubun',
      width: 120,
      render: (val: string) => {
        const trimmed = val?.trim();
        const info = moduleLabels[trimmed];
        return info ? <Tag color={info.color}>{info.label}</Tag> : trimmed;
      },
    },
    {
      title: '마감시각',
      dataIndex: 'CloseTime',
      key: 'CloseTime',
      width: 200,
      render: (val: string) => val?.trim(),
    },
  ];

  return (
    <div>
      <Title level={4}>월마감 이력</Title>
      <Card>
        <div style={{ marginBottom: 16, textAlign: 'right' }}>
          <ExportButton
            onExport={() => {}}
            disabled={!data?.length}
          />
        </div>
        <DataTable
          columns={columns}
          data={data || []}
          loading={isLoading}
          rowKey={(record: any, index?: number) => `${record.CloseMonth}-${record.ModuleGubun}-${index}`}
        />
      </Card>
    </div>
  );
};

export default MonthClosePage;
