#!/bin/bash
#
# SES Sender - 一键配置 SNS + SQS 事件追踪
# 用法: ./setup-ses-events.sh <region> [configuration-set-name]
#
# 示例:
#   ./setup-ses-events.sh us-east-1
#   ./setup-ses-events.sh ap-northeast-1 my-config-set
#

set -e

# ========== 参数解析 ==========
REGION="${1:?用法: $0 <region> [configuration-set-name]}"
CONFIG_SET="${2:-ses-sender-tracking}"
TOPIC_NAME="ses-sender-events"
QUEUE_NAME="ses-sender-events-queue"

echo "========================================"
echo "  SES Sender 事件追踪配置"
echo "========================================"
echo "  区域:              $REGION"
echo "  Configuration Set: $CONFIG_SET"
echo "  SNS Topic:         $TOPIC_NAME"
echo "  SQS Queue:         $QUEUE_NAME"
echo "========================================"
echo ""

# ========== 1. 获取 AWS 账户 ID ==========
echo "[1/6] 获取 AWS 账户 ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text --region "$REGION")
echo "  账户 ID: $ACCOUNT_ID"

# ========== 2. 创建 SNS Topic ==========
echo ""
echo "[2/6] 创建 SNS Topic: $TOPIC_NAME ..."
TOPIC_ARN=$(aws sns create-topic \
  --name "$TOPIC_NAME" \
  --region "$REGION" \
  --query "TopicArn" --output text)
echo "  Topic ARN: $TOPIC_ARN"

# ========== 3. 创建 SQS 队列 ==========
echo ""
echo "[3/6] 创建 SQS 队列: $QUEUE_NAME ..."
QUEUE_URL=$(aws sqs create-queue \
  --queue-name "$QUEUE_NAME" \
  --attributes '{
    "ReceiveMessageWaitTimeSeconds": "20",
    "VisibilityTimeout": "300",
    "MessageRetentionPeriod": "1209600"
  }' \
  --region "$REGION" \
  --query "QueueUrl" --output text)
echo "  Queue URL: $QUEUE_URL"

# 获取 SQS 队列 ARN
QUEUE_ARN=$(aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn \
  --region "$REGION" \
  --query "Attributes.QueueArn" --output text)
echo "  Queue ARN: $QUEUE_ARN"

# ========== 4. 设置 SQS 队列策略 ==========
echo ""
echo "[4/6] 设置 SQS 队列策略（允许 SNS 发送消息）..."
POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "sns.amazonaws.com"},
      "Action": "sqs:SendMessage",
      "Resource": "$QUEUE_ARN",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "$TOPIC_ARN"
        }
      }
    }
  ]
}
EOF
)

# 转义 JSON 用于 --attributes 参数
ESCAPED_POLICY=$(echo "$POLICY" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
aws sqs set-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attributes "{\"Policy\": $ESCAPED_POLICY}" \
  --region "$REGION"
echo "  策略已设置"

# ========== 5. 订阅 SNS Topic → SQS ==========
echo ""
echo "[5/6] 订阅 SNS → SQS ..."
SUB_ARN=$(aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol sqs \
  --notification-endpoint "$QUEUE_ARN" \
  --attributes '{"RawMessageDelivery": "false"}' \
  --region "$REGION" \
  --query "SubscriptionArn" --output text)
echo "  订阅 ARN: $SUB_ARN"

# ========== 6. 添加 SES Event Destination ==========
echo ""
echo "[6/6] 添加 SNS Event Destination 到 Configuration Set: $CONFIG_SET ..."
aws sesv2 create-configuration-set-event-destination \
  --configuration-set-name "$CONFIG_SET" \
  --event-destination-name sns-events \
  --event-destination "{
    \"Enabled\": true,
    \"MatchingEventTypes\": [\"SEND\", \"DELIVERY\", \"BOUNCE\", \"COMPLAINT\", \"OPEN\", \"CLICK\", \"REJECT\"],
    \"SnsDestination\": {
      \"TopicArn\": \"$TOPIC_ARN\"
    }
  }" \
  --region "$REGION" 2>&1 && echo "  Event Destination 已创建" || echo "  ⚠ Event Destination 可能已存在，请检查"

# ========== 完成 ==========
echo ""
echo "========================================"
echo "  配置完成!"
echo "========================================"
echo ""
echo "请将以下变量添加到 .env 文件中:"
echo ""
echo "  SQS_QUEUE_URL=$QUEUE_URL"
echo "  SES_CONFIGURATION_SET=$CONFIG_SET"
echo ""
echo "然后重启服务:"
echo ""
echo "  docker-compose down && docker-compose up -d"
echo ""
echo "验证 SQS Worker 是否启动:"
echo ""
echo "  docker-compose logs -f backend | grep 'SQS Worker'"
echo ""
