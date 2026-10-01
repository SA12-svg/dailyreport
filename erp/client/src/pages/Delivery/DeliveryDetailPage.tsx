import React from 'react';
import { Card, Descriptions, Table, Typography, Spin, Empty } from 'antd';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { deliveryApi } from '../../api/delivery.api';

const { Title } = Typography;

const DeliveryDetailPage: React.FC = () => {
  const { orderSeq, deliverySeq } = useParams<{ orderSeq: string; deliverySeq: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ['delivery', 'detail', orderSeq, deliverySeq],
    queryFn: () => deliveryApi.getDeliveryDetail(
      parseInt(orderSeq!, 10),
      parseInt(deliverySeq!, 10),
    ),
    enabled: !!orderSeq && !!deliverySeq,
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  if (!data) {
    return <Empty description="배송 정보를 찾을 수 없습니다." />;
  }

  const detailColumns = [
    { title: '항목유형', dataIndex: 'item_type', key: 'item_type', width: 120 },
    { title: '항목명', dataIndex: 'item_title', key: 'item_title', width: 200 },
    { title: '수량', dataIndex: 'item_count', key: 'item_count', width: 80, align: 'right' as const },
  ];

  const trackingColumns = [
    { title: '택배사', dataIndex: 'delivery_com', key: 'delivery_com', width: 120 },
    { title: '송장번호', dataIndex: 'delivery_code_num', key: 'delivery_code_num', width: 200 },
    {
      title: '등록일',
      dataIndex: 'reg_date',
      key: 'reg_date',
      width: 160,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD HH:mm') : '',
    },
  ];

  return (
    <div>
      <Title level={4}>배송 상세 정보</Title>

      <Card title="배송 기본정보" style={{ marginBottom: 16 }}>
        <Descriptions bordered column={2} size="small">
          <Descriptions.Item label="주문번호">{data.ORDER_SEQ}</Descriptions.Item>
          <Descriptions.Item label="배송순번">{data.DELIVERY_SEQ}</Descriptions.Item>
          <Descriptions.Item label="수령인">{data.NAME}</Descriptions.Item>
          <Descriptions.Item label="이메일">{data.EMAIL}</Descriptions.Item>
          <Descriptions.Item label="연락처">{data.PHONE}</Descriptions.Item>
          <Descriptions.Item label="휴대폰">{data.HPHONE}</Descriptions.Item>
          <Descriptions.Item label="배송주소" span={2}>{data.ADDR} {data.ADDR_DETAIL}</Descriptions.Item>
          <Descriptions.Item label="우편번호">{data.ZIPCODE}</Descriptions.Item>
          <Descriptions.Item label="배송일">
            {data.DELIVERY_DATE ? dayjs(data.DELIVERY_DATE).format('YYYY-MM-DD') : ''}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="배송 항목" style={{ marginBottom: 16 }}>
        <Table
          columns={detailColumns}
          dataSource={data.details || []}
          rowKey="delivery_id"
          size="small"
          pagination={false}
        />
      </Card>

      <Card title="송장 정보">
        <Table
          columns={trackingColumns}
          dataSource={data.trackings || []}
          rowKey={(record: any) => `${record.delivery_id}-${record.delivery_code_num}`}
          size="small"
          pagination={false}
        />
      </Card>
    </div>
  );
};

export default DeliveryDetailPage;
