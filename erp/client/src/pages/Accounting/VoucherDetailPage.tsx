import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Table, Tag, Badge, Button, Space, Typography, Alert } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import AmountFormat from '../../components/AmountFormat';
import { accountingApi } from '../../api/accounting.api';
import LoadingSpinner from '../../components/LoadingSpinner';

const { Title } = Typography;

const docTypeLabels: Record<string, string> = {
  '01': '일반전표',
  '02': '매입전표',
  '03': '매출전표',
  '04': '결산전표',
};

const statusLabels: Record<string, { label: string; color: string }> = {
  '0': { label: '미승인', color: 'default' },
  '1': { label: '승인', color: 'success' },
  '9': { label: '반려', color: 'error' },
};

function formatDate(date: string) {
  if (!date) return '';
  return `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)}`;
}

const VoucherDetailPage: React.FC = () => {
  const { docNo } = useParams<{ docNo: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['accounting', 'voucher', docNo],
    queryFn: () => accountingApi.getVoucherDetail(docNo!),
    enabled: !!docNo,
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <LoadingSpinner />;
  if (!data) return <Alert type="error" message="전표를 찾을 수 없습니다." showIcon />;

  const statusInfo = statusLabels[data.Status] || { label: data.Status, color: 'default' };

  const itemColumns = [
    {
      title: '순번',
      dataIndex: 'ItemSeq',
      key: 'ItemSeq',
      width: 60,
      align: 'center' as const,
    },
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
      width: 160,
    },
    {
      title: '차/대',
      dataIndex: 'DrCr',
      key: 'DrCr',
      width: 70,
      align: 'center' as const,
      render: (val: string) =>
        val === 'D' ? <Tag color="blue">차변</Tag> : <Tag color="red">대변</Tag>,
    },
    {
      title: '금액',
      dataIndex: 'Amount',
      key: 'Amount',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '적요',
      dataIndex: 'Remark',
      key: 'Remark',
      ellipsis: true,
    },
    {
      title: '부서코드',
      dataIndex: 'DeptCode',
      key: 'DeptCode',
      width: 100,
    },
    {
      title: '거래처코드',
      dataIndex: 'CustCode',
      key: 'CustCode',
      width: 110,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/accounting/vouchers')}>
          목록으로
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          전표 상세 - {docNo}
        </Title>
      </Space>

      {!data.isBalanced && (
        <Alert
          type="error"
          message="차대변 불일치"
          description={`차변 합계(${data.totalDebit.toLocaleString()})와 대변 합계(${data.totalCredit.toLocaleString()})가 일치하지 않습니다.`}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Card style={{ marginBottom: 16 }}>
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label="전표번호">{data.DocNo}</Descriptions.Item>
          <Descriptions.Item label="전표유형">{docTypeLabels[data.DocType] || data.DocType}</Descriptions.Item>
          <Descriptions.Item label="전표일자">{formatDate(data.RelDate)}</Descriptions.Item>
          <Descriptions.Item label="적요" span={2}>{data.Remark}</Descriptions.Item>
          <Descriptions.Item label="승인상태">
            <Badge status={statusInfo.color as any} text={statusInfo.label} />
          </Descriptions.Item>
          <Descriptions.Item label="등록자">{data.RegUser}</Descriptions.Item>
          <Descriptions.Item label="총액">
            <AmountFormat value={data.TotalAmt || 0} suffix=" 원" />
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="전표 항목"
        extra={
          <Space>
            <span>차변 합계: <AmountFormat value={data.totalDebit} type={data.isBalanced ? 'default' : 'danger'} /></span>
            <span>대변 합계: <AmountFormat value={data.totalCredit} type={data.isBalanced ? 'default' : 'danger'} /></span>
            {data.isBalanced ? (
              <Tag color="success">차대 일치</Tag>
            ) : (
              <Tag color="error">차대 불일치</Tag>
            )}
          </Space>
        }
      >
        <Table
          columns={itemColumns}
          dataSource={data.items || []}
          rowKey="ItemSeq"
          pagination={false}
          size="middle"
          scroll={{ x: 'max-content' }}
          summary={() => (
            <Table.Summary fixed>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={4} align="right">
                  <strong>합계</strong>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={4} align="right">
                  <strong><AmountFormat value={data.totalDebit + data.totalCredit} /></strong>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={5} colSpan={3} />
              </Table.Summary.Row>
            </Table.Summary>
          )}
        />
      </Card>
    </div>
  );
};

export default VoucherDetailPage;
