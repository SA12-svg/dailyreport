import React from 'react';
import { Card, Row, Col, Table, Tag, Statistic, Typography } from 'antd';
import AmountFormat from '../../../components/AmountFormat';

const { Text } = Typography;

interface BalanceSheetProps {
  data: {
    assets: any[];
    liabilities: any[];
    equity: any[];
    totalAssets: number;
    totalLiabilities: number;
    totalEquity: number;
    isBalanced: boolean;
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

const BalanceSheet: React.FC<BalanceSheetProps> = ({ data, loading }) => {
  if (!data) return null;

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="자산 총계"
              value={data.totalAssets}
              precision={0}
              prefix="₩"
              formatter={(val) => Number(val).toLocaleString()}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="부채 총계"
              value={data.totalLiabilities}
              precision={0}
              prefix="₩"
              formatter={(val) => Number(val).toLocaleString()}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="자본 총계"
              value={data.totalEquity}
              precision={0}
              prefix="₩"
              formatter={(val) => Number(val).toLocaleString()}
            />
          </Card>
        </Col>
      </Row>

      {!data.isBalanced && (
        <div style={{ marginBottom: 16, padding: '8px 16px', background: '#fff2f0', border: '1px solid #ffccc7', borderRadius: 4 }}>
          <Text type="danger">
            대차 불일치: 자산({data.totalAssets.toLocaleString()}) ≠ 부채({data.totalLiabilities.toLocaleString()}) + 자본({data.totalEquity.toLocaleString()})
          </Text>
        </div>
      )}

      <Row gutter={16}>
        <Col span={12}>
          <Card title="자산" size="small">
            <Table
              columns={columns}
              dataSource={data.assets}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={loading}
              summary={() => (
                <Table.Summary>
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={3}>
                      <strong>자산 합계</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">
                      <strong><AmountFormat value={data.totalAssets} /></strong>
                    </Table.Summary.Cell>
                  </Table.Summary.Row>
                </Table.Summary>
              )}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="부채" size="small" style={{ marginBottom: 16 }}>
            <Table
              columns={columns}
              dataSource={data.liabilities}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={loading}
              summary={() => (
                <Table.Summary>
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={3}>
                      <strong>부채 합계</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">
                      <strong><AmountFormat value={data.totalLiabilities} /></strong>
                    </Table.Summary.Cell>
                  </Table.Summary.Row>
                </Table.Summary>
              )}
            />
          </Card>
          <Card title="자본" size="small">
            <Table
              columns={columns}
              dataSource={data.equity}
              rowKey="AccCode"
              pagination={false}
              size="small"
              loading={loading}
              summary={() => (
                <Table.Summary>
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={3}>
                      <strong>자본 합계</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">
                      <strong><AmountFormat value={data.totalEquity} /></strong>
                    </Table.Summary.Cell>
                  </Table.Summary.Row>
                </Table.Summary>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default BalanceSheet;
