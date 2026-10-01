import React from 'react';
import { Card, Row, Col, Table, Tag, Statistic, Typography } from 'antd';
import AmountFormat from '../../../components/AmountFormat';

const { Text } = Typography;

interface IncomeStatementProps {
  data: {
    revenue: any[];
    expenses: any[];
    totalRevenue: number;
    totalExpenses: number;
    netIncome: number;
  } | null;
  loading?: boolean;
}

const columns = [
  {
    title: '계정코드',
    dataIndex: 'AccCode',
    key: 'AccCode',
    width: 100,
  },
  {
    title: '계정명',
    dataIndex: 'AccName',
    key: 'AccName',
  },
  {
    title: '분류',
    dataIndex: 'SubCategory',
    key: 'SubCategory',
    width: 100,
    render: (val: string) => <Tag>{val}</Tag>,
  },
  {
    title: '금액',
    dataIndex: 'Amount',
    key: 'Amount',
    width: 150,
    align: 'right' as const,
    render: (val: number) => <AmountFormat value={val || 0} />,
  },
];

const IncomeStatement: React.FC<IncomeStatementProps> = ({ data, loading }) => {
  if (!data) return null;

  const isProfit = data.netIncome >= 0;

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="수익 총계"
              value={data.totalRevenue}
              precision={0}
              prefix="₩"
              valueStyle={{ color: '#3f8600' }}
              formatter={(val) => Number(val).toLocaleString()}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="비용 총계"
              value={data.totalExpenses}
              precision={0}
              prefix="₩"
              valueStyle={{ color: '#cf1322' }}
              formatter={(val) => Number(val).toLocaleString()}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={isProfit ? '당기순이익' : '당기순손실'}
              value={Math.abs(data.netIncome)}
              precision={0}
              prefix="₩"
              valueStyle={{ color: isProfit ? '#3f8600' : '#cf1322' }}
              formatter={(val) => Number(val).toLocaleString()}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="수익" size="small">
            <Table
              columns={columns}
              dataSource={data.revenue}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={loading}
              summary={() => (
                <Table.Summary>
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={3}>
                      <strong>수익 합계</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">
                      <Text strong style={{ color: '#3f8600' }}>
                        <AmountFormat value={data.totalRevenue} />
                      </Text>
                    </Table.Summary.Cell>
                  </Table.Summary.Row>
                </Table.Summary>
              )}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="비용" size="small">
            <Table
              columns={columns}
              dataSource={data.expenses}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={loading}
              summary={() => (
                <Table.Summary>
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={3}>
                      <strong>비용 합계</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">
                      <Text strong style={{ color: '#cf1322' }}>
                        <AmountFormat value={data.totalExpenses} />
                      </Text>
                    </Table.Summary.Cell>
                  </Table.Summary.Row>
                </Table.Summary>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginTop: 16, textAlign: 'center' }}>
        <Text strong style={{ fontSize: 18 }}>
          {isProfit ? '당기순이익' : '당기순손실'}:{' '}
          <Text style={{ color: isProfit ? '#3f8600' : '#cf1322', fontSize: 20 }}>
            ₩{Math.abs(data.netIncome).toLocaleString()}
          </Text>
        </Text>
      </Card>
    </div>
  );
};

export default IncomeStatement;
