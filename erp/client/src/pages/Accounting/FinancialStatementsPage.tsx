import React, { useState } from 'react';
import { Card, Tabs, Table, Typography, Statistic, Row, Col } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import FilterBar from '../../components/FilterBar';
import AmountFormat from '../../components/AmountFormat';
import BalanceSheet from './components/BalanceSheet';
import IncomeStatement from './components/IncomeStatement';
import { accountingApi } from '../../api/accounting.api';
import type { FilterConfig } from '../../types';

const { Title } = Typography;

const filters: FilterConfig[] = [
  { type: 'dateRange', key: 'dateRange', label: '조회기간', required: true, maxDays: 365 },
];

const FinancialStatementsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('balance-sheet');
  const [dateRange, setDateRange] = useState({
    dateFrom: dayjs().startOf('year').format('YYYYMMDD'),
    dateTo: dayjs().format('YYYYMMDD'),
  });
  const [searchTriggered, setSearchTriggered] = useState(false);

  const { data: bsData, isLoading: bsLoading } = useQuery({
    queryKey: ['accounting', 'balance-sheet', dateRange.dateTo],
    queryFn: () => accountingApi.getBalanceSheet({ dateTo: dateRange.dateTo }),
    enabled: searchTriggered && activeTab === 'balance-sheet',
    staleTime: 5 * 60 * 1000,
  });

  const { data: isData, isLoading: isLoading } = useQuery({
    queryKey: ['accounting', 'income-statement', dateRange],
    queryFn: () => accountingApi.getIncomeStatement(dateRange),
    enabled: searchTriggered && activeTab === 'income-statement',
    staleTime: 5 * 60 * 1000,
  });

  const { data: cfData, isLoading: cfLoading } = useQuery({
    queryKey: ['accounting', 'cash-flow', dateRange],
    queryFn: () => accountingApi.getCashFlow(dateRange),
    enabled: searchTriggered && activeTab === 'cash-flow',
    staleTime: 5 * 60 * 1000,
  });

  const handleSearch = (values: Record<string, any>) => {
    const [start, end] = values.dateRange || [];
    if (start && end) {
      setDateRange({
        dateFrom: dayjs(start).format('YYYYMMDD'),
        dateTo: dayjs(end).format('YYYYMMDD'),
      });
    }
    setSearchTriggered(true);
  };

  const cashFlowColumns = [
    { title: '계정코드', dataIndex: 'AccCode', key: 'AccCode', width: 100 },
    { title: '계정명', dataIndex: 'AccName', key: 'AccName' },
    {
      title: '금액',
      dataIndex: 'Amount',
      key: 'Amount',
      width: 150,
      align: 'right' as const,
      render: (val: number) => (
        <AmountFormat value={val} type={val < 0 ? 'danger' : 'success'} />
      ),
    },
  ];

  const tabItems = [
    {
      key: 'balance-sheet',
      label: '재무상태표',
      children: <BalanceSheet data={bsData} loading={bsLoading} />,
    },
    {
      key: 'income-statement',
      label: '손익계산서',
      children: <IncomeStatement data={isData} loading={isLoading} />,
    },
    {
      key: 'cash-flow',
      label: '현금흐름표',
      children: cfData ? (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card>
                <Statistic
                  title="영업활동"
                  value={cfData.totalOperating}
                  precision={0}
                  prefix="₩"
                  valueStyle={{ color: cfData.totalOperating >= 0 ? '#3f8600' : '#cf1322' }}
                  formatter={(val) => Number(val).toLocaleString()}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="투자활동"
                  value={cfData.totalInvesting}
                  precision={0}
                  prefix="₩"
                  valueStyle={{ color: cfData.totalInvesting >= 0 ? '#3f8600' : '#cf1322' }}
                  formatter={(val) => Number(val).toLocaleString()}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="재무활동"
                  value={cfData.totalFinancing}
                  precision={0}
                  prefix="₩"
                  valueStyle={{ color: cfData.totalFinancing >= 0 ? '#3f8600' : '#cf1322' }}
                  formatter={(val) => Number(val).toLocaleString()}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="순현금흐름"
                  value={cfData.netCashFlow}
                  precision={0}
                  prefix="₩"
                  valueStyle={{ color: cfData.netCashFlow >= 0 ? '#3f8600' : '#cf1322' }}
                  formatter={(val) => Number(val).toLocaleString()}
                />
              </Card>
            </Col>
          </Row>

          <Card title="영업활동 현금흐름" size="small" style={{ marginBottom: 16 }}>
            <Table
              columns={cashFlowColumns}
              dataSource={cfData.operating}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={cfLoading}
            />
          </Card>
          <Card title="투자활동 현금흐름" size="small" style={{ marginBottom: 16 }}>
            <Table
              columns={cashFlowColumns}
              dataSource={cfData.investing}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={cfLoading}
            />
          </Card>
          <Card title="재무활동 현금흐름" size="small">
            <Table
              columns={cashFlowColumns}
              dataSource={cfData.financing}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={cfLoading}
            />
          </Card>
        </div>
      ) : null,
    },
  ];

  return (
    <div>
      <Title level={4}>재무제표</Title>
      <Card>
        <FilterBar
          filters={filters}
          onSearch={handleSearch}
          loading={bsLoading || isLoading || cfLoading}
        />
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
        />
      </Card>
    </div>
  );
};

export default FinancialStatementsPage;
