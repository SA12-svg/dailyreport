import React from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Card, Descriptions, Table, Tag, Button, Space, Typography, Alert } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import AmountFormat from '../../components/AmountFormat';
import { billingApi } from '../../api/billing.api';
import LoadingSpinner from '../../components/LoadingSpinner';

const { Title } = Typography;

const arApLabels: Record<string, string> = {
  AR: '매출(AR)',
  AP: '매입(AP)',
  Ax: '기타',
};

function formatDate(date: string) {
  if (!date) return '';
  const d = date.trim();
  return `${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)}`;
}

const BillDetailPage: React.FC = () => {
  const { billNo } = useParams<{ billNo: string }>();
  const [searchParams] = useSearchParams();
  const arApGubun = searchParams.get('arApGubun') || 'AR';
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['billing', 'bill', billNo, arApGubun],
    queryFn: () => billingApi.getBillDetail(billNo!, arApGubun),
    enabled: !!billNo,
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <LoadingSpinner />;
  if (!data) return <Alert type="error" message="청구서를 찾을 수 없습니다." showIcon />;

  const itemColumns = [
    {
      title: '순번',
      dataIndex: 'BillSerNo',
      key: 'BillSerNo',
      width: 60,
      align: 'center' as const,
    },
    {
      title: '품목코드',
      dataIndex: 'ItemCode',
      key: 'ItemCode',
      width: 120,
      render: (val: string) => val?.trim(),
    },
    {
      title: '품목명',
      dataIndex: 'ItemName',
      key: 'ItemName',
      width: 200,
      render: (val: string) => val?.trim(),
    },
    {
      title: '규격',
      dataIndex: 'ItemSpec',
      key: 'ItemSpec',
      width: 140,
      render: (val: string) => val?.trim(),
    },
    {
      title: '수량',
      dataIndex: 'ItemQty',
      key: 'ItemQty',
      width: 90,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '단가',
      dataIndex: 'ItemPrice',
      key: 'ItemPrice',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: '금액',
      dataIndex: 'ItemAmnt',
      key: 'ItemAmnt',
      width: 140,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
    {
      title: 'VAT',
      dataIndex: 'ItemVatAmnt',
      key: 'ItemVatAmnt',
      width: 120,
      align: 'right' as const,
      render: (val: number) => <AmountFormat value={val || 0} />,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/billing/bills')}>
          목록으로
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          청구 상세 - {billNo}
        </Title>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label="청구번호">{data.BillNo?.trim()}</Descriptions.Item>
          <Descriptions.Item label="AR/AP 구분">
            <Tag color={data.ArApGubun?.trim() === 'AR' ? 'blue' : 'orange'}>
              {arApLabels[data.ArApGubun?.trim()] || data.ArApGubun}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="청구일">{formatDate(data.BillDate)}</Descriptions.Item>
          <Descriptions.Item label="거래처">{data.CsCode?.trim()}</Descriptions.Item>
          <Descriptions.Item label="부서">{data.DeptCode?.trim()}</Descriptions.Item>
          <Descriptions.Item label="담당자">{data.EmpCode?.trim()}</Descriptions.Item>
          <Descriptions.Item label="청구금액">
            <AmountFormat value={data.BillAmnt || 0} suffix=" 원" />
          </Descriptions.Item>
          <Descriptions.Item label="VAT">
            <AmountFormat value={data.VatAmnt || 0} suffix=" 원" />
          </Descriptions.Item>
          <Descriptions.Item label="수금액">
            <AmountFormat value={data.MoneySumAmnt || 0} suffix=" 원" />
          </Descriptions.Item>
          <Descriptions.Item label="세금계산서">{data.InvoiceNo?.trim() || '-'}</Descriptions.Item>
          <Descriptions.Item label="주문번호">{data.C_JumunNo?.trim() || '-'}</Descriptions.Item>
          <Descriptions.Item label="비고">{data.BillDescr?.trim() || '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="청구 항목"
        extra={
          <Space>
            <span>공급가 합계: <AmountFormat value={data.totalItemAmnt} /></span>
            <span>VAT 합계: <AmountFormat value={data.totalVatAmnt} /></span>
          </Space>
        }
      >
        <Table
          columns={itemColumns}
          dataSource={data.items || []}
          rowKey="BillSerNo"
          pagination={false}
          size="middle"
          scroll={{ x: 'max-content' }}
          summary={() => (
            <Table.Summary fixed>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={6} align="right">
                  <strong>합계</strong>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={6} align="right">
                  <strong><AmountFormat value={data.totalItemAmnt} /></strong>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={7} align="right">
                  <strong><AmountFormat value={data.totalVatAmnt} /></strong>
                </Table.Summary.Cell>
              </Table.Summary.Row>
            </Table.Summary>
          )}
        />
      </Card>
    </div>
  );
};

export default BillDetailPage;
