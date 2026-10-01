import React, { useState } from 'react';
import { Card, Table, Tag, Typography, Select, Space, Statistic, Row, Col } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import AmountFormat from '../../components/AmountFormat';
import ExportButton from '../../components/ExportButton';
import { taxApi } from '../../api/tax.api';

const { Title } = Typography;

const taxCodeLabels: Record<string, string> = {
  '01': '과세',
  '02': '영세',
  '03': '면세',
  '04': '비과세',
  '11': '수출',
  '12': '기타',
};

const arApLabels: Record<string, string> = {
  AR: '매출',
  AP: '매입',
};

const VatReturnPage: React.FC = () => {
  const [year, setYear] = useState(dayjs().format('YYYY'));
  const [quarter, setQuarter] = useState(String(Math.ceil((dayjs().month() + 1) / 3)));
  const [arApGubun, setArApGubun] = useState<string | undefined>(undefined);

  const { data, isLoading } = useQuery({
    queryKey: ['tax', 'vat-return', year, quarter, arApGubun],
    queryFn: () => taxApi.getVatReturn({ year, quarter, arApGubun }),
    staleTime: 5 * 60 * 1000,
  });

  const rows = data?.data || [];

  const salesRows = rows.filter((r: any) => r.ArApGubun?.trim() === 'AR');
  const purchaseRows = rows.filter((r: any) => r.ArApGubun?.trim() === 'AP');

  const totalSalesSupply = salesRows.reduce((s: number, r: any) => s + (r.SupplyAmnt || 0), 0);
  const totalSalesVat = salesRows.reduce((s: number, r: any) => s + (r.VatAmnt || 0), 0);
  const totalPurchaseSupply = purchaseRows.reduce((s: number, r: any) => s + (r.SupplyAmnt || 0), 0);
  const totalPurchaseVat = purchaseRows.reduce((s: number, r: any) => s + (r.VatAmnt || 0), 0);
  const netVat = totalSalesVat - totalPurchaseVat;

  const columns = [
    {
      title: '구분',
      dataIndex: 'ArApGubun',
      key: 'ArApGubun',
      width: 80,
      render: (val: string) => {
        const trimmed = val?.trim();
        return <Tag color={trimmed === 'AR' ? 'blue' : 'orange'}>{arApLabels[trimmed] || trimmed}</Tag>;
      },
    },
    {
      title: '세금코드',
      dataIndex: 'TaxCode',
      key: 'TaxCode',
      width: 100,
      render: (val: string) => taxCodeLabels[val?.trim()] || val?.trim(),
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

  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = String(dayjs().year() - i);
    return { value: y, label: `${y}년` };
  });

  return (
    <div>
      <Title level={4}>부가세 신고 자동집계</Title>
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            value={year}
            onChange={setYear}
            options={yearOptions}
            style={{ width: 120 }}
          />
          <Select
            value={quarter}
            onChange={setQuarter}
            options={[
              { value: '1', label: '1분기 (1~3월)' },
              { value: '2', label: '2분기 (4~6월)' },
              { value: '3', label: '3분기 (7~9월)' },
              { value: '4', label: '4분기 (10~12월)' },
            ]}
            style={{ width: 160 }}
          />
          <Select
            value={arApGubun}
            onChange={setArApGubun}
            allowClear
            placeholder="전체"
            options={[
              { value: 'AR', label: '매출' },
              { value: 'AP', label: '매입' },
            ]}
            style={{ width: 120 }}
          />
          <ExportButton onExport={() => {}} disabled={!rows.length} />
        </Space>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Statistic title="매출 공급가액" value={totalSalesSupply} precision={0} groupSeparator="," />
          </Col>
          <Col span={6}>
            <Statistic title="매출 세액" value={totalSalesVat} precision={0} groupSeparator="," />
          </Col>
          <Col span={6}>
            <Statistic title="매입 세액" value={totalPurchaseVat} precision={0} groupSeparator="," />
          </Col>
          <Col span={6}>
            <Statistic
              title="납부(환급) 세액"
              value={netVat}
              precision={0}
              groupSeparator=","
              valueStyle={{ color: netVat >= 0 ? '#cf1322' : '#3f8600' }}
            />
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={rows}
          loading={isLoading}
          rowKey={(record: any) => `${record.ArApGubun}-${record.TaxCode}`}
          pagination={false}
          size="small"
          summary={() => (
            <Table.Summary fixed>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={2}><strong>매출 소계</strong></Table.Summary.Cell>
                <Table.Summary.Cell index={2} align="right"><strong>{salesRows.reduce((s: number, r: any) => s + (r.InvoiceCount || 0), 0).toLocaleString()}</strong></Table.Summary.Cell>
                <Table.Summary.Cell index={3} align="right"><strong><AmountFormat value={totalSalesSupply} /></strong></Table.Summary.Cell>
                <Table.Summary.Cell index={4} align="right"><strong><AmountFormat value={totalSalesVat} /></strong></Table.Summary.Cell>
                <Table.Summary.Cell index={5} align="right"><strong><AmountFormat value={totalSalesSupply + totalSalesVat} /></strong></Table.Summary.Cell>
              </Table.Summary.Row>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={2}><strong>매입 소계</strong></Table.Summary.Cell>
                <Table.Summary.Cell index={2} align="right"><strong>{purchaseRows.reduce((s: number, r: any) => s + (r.InvoiceCount || 0), 0).toLocaleString()}</strong></Table.Summary.Cell>
                <Table.Summary.Cell index={3} align="right"><strong><AmountFormat value={totalPurchaseSupply} /></strong></Table.Summary.Cell>
                <Table.Summary.Cell index={4} align="right"><strong><AmountFormat value={totalPurchaseVat} /></strong></Table.Summary.Cell>
                <Table.Summary.Cell index={5} align="right"><strong><AmountFormat value={totalPurchaseSupply + totalPurchaseVat} /></strong></Table.Summary.Cell>
              </Table.Summary.Row>
            </Table.Summary>
          )}
        />
      </Card>
    </div>
  );
};

export default VatReturnPage;
