# SES Sender

基于 AWS SES 的邮件批量发送管理平台，前后端分离架构，支持多用户、权限管理、客群管理、批量发送和送达率追踪。

## 界面预览

**管理员面板**

![管理员面板](img/admin.png)

**用户面板**

![用户面板](img/user.png)

## 功能概览

### 管理员

| 功能 | 说明 |
|------|------|
| 用户管理 | 创建/编辑/禁用用户，为每个用户配置专属发送邮箱，设置每日发送限额，重置密码 |
| 发送实体 | 验证邮箱地址和域名（SES Identity） |
| 邮件模版 | 创建/编辑/删除邮件模版（按用户隔离），支持 `{{name}}` 等变量，AI 智能优化 |
| 测试邮件 | 选择已验证的发送实体或手动输入，自定义内容发送测试邮件 |

### 普通用户

| 功能 | 说明 |
|------|------|
| 数据概览 | 个人发送统计 Dashboard：今日/本月/总计发送量、每日配额进度、送达率/打开率指标、7 天趋势图 |
| 客群管理 | 创建/编辑/删除客群，搜索和分页 |
| 联系人管理 | 批量添加联系人，Excel 导入/导出/模版下载，支持自定义属性（JSON），搜索和分页 |
| 邮件模版 | 每个用户独立维护自己的邮件模版（创建/编辑/删除），HTML 实时预览，AI 智能优化 |
| 批量发送 | 选择模版和目标客群，异步批量发送，自动速率限制，每日配额检查，过滤已退订联系人 |
| 定时发送 | 单次定时发送、每天/每周/每月周期性发送，支持暂停/恢复，后台自动调度执行 |
| 发送历史 | 查看历史发送记录，实时发送进度，点击查看每个批次的送达率、打开率等指标 |
| 邮件明细 | 独立页面查看每封邮件的送达/退信/打开/点击状态，支持搜索和筛选 |
| 退订管理 | 查看和管理退订用户列表，支持恢复发送 |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python / FastAPI / SQLAlchemy / Alembic / Boto3 |
| 前端 | Next.js 16 / React / Tailwind CSS / TypeScript |
| 数据库 | MySQL 8 |
| 认证 | JWT (python-jose) + bcrypt |
| 监控 | AWS CloudWatch + SES VDM（Virtual Deliverability Manager） |
| 事件追踪 | SNS → SQS → 后端轮询（每封邮件的送达/打开/点击/退信追踪） |
| AI 优化 | AWS Bedrock（Claude）— 邮件模版智能优化建议 |
| 退订 | RFC 8058 一键退订，HMAC-SHA256 签名令牌 |
| 部署 | Docker / Docker Compose，前端反向代理后端 API（只暴露一个端口） |

## 项目结构

```
ses-sender/
├── docker-compose.yml
├── .env.example
├── setup-ses-events.sh            # SNS+SQS 一键配置脚本
│
├── backend/
│   ├── main.py                    # 应用入口，Alembic 迁移 + SQS 轮询 + 定时调度器 + 路由注册
│   ├── alembic/                   # 数据库迁移
│   │   ├── env.py
│   │   └── versions/              # 迁移脚本
│   ├── core/                      # 核心层（基础设施）
│   │   ├── config.py              #   配置中心
│   │   ├── database.py            #   数据库连接
│   │   ├── deps.py                #   认证 & 权限依赖
│   │   ├── ses.py                 #   AWS SES v1/v2 客户端 + 发送配额
│   │   └── unsubscribe.py         #   退订令牌生成/验证（HMAC-SHA256）
│   └── domain/                    # 业务域（DDD）
│       ├── auth/                  #   认证域：用户登录、用户管理
│       ├── identity/              #   发送实体域：SES 邮箱/域名验证
│       ├── template/              #   邮件模版域：按用户隔离的模版 CRUD + AI 优化
│       ├── audience/              #   客群域：客群、联系人、自定义属性、Excel
│       └── sending/               #   发送域：异步批量发送、定时发送、发送历史、指标、退订
│
└── frontend/
    └── app/
        ├── page.tsx               # 单页应用（登录 / 管理员面板 / 用户面板）
        └── api/[...path]/route.ts # API 反向代理（转发至后端）
```

每个业务域包含：
- `models.py` — 数据库实体（如有）
- `schemas.py` — 请求/响应模型
- `service.py` — 业务逻辑
- `router.py` — API 路由

## 快速开始

> ☁️ **想要 AWS 生产级一键部署？** 见 [`cdk/`](cdk/README.md) —— 用 AWS CDK 一条命令拉起 CloudFront + ALB + ECS Fargate + Aurora MySQL + SES/SNS/SQS 全套基础设施。以下为本地 docker-compose 方式。

### 1. 环境准备

- Docker & Docker Compose
- EC2 实例绑定具有 SES 和 CloudWatch 权限的 IAM Role（无需配置 AK/SK）

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env` 按需修改：

```env
# AWS 区域
AWS_REGION=us-east-1

# SES Configuration Set（用于 VDM 追踪送达率/打开率，留空则不追踪）
SES_CONFIGURATION_SET=ses-sender-tracking

# SQS 队列 URL（用于每封邮件的事件追踪，留空则不追踪）
SQS_QUEUE_URL=

# 退订链接基础 URL（公网可访问的后端地址，留空则不添加退订链接）
UNSUBSCRIBE_BASE_URL=

# AI 模版优化（AWS Bedrock，留空则禁用 AI 功能）
BEDROCK_MODEL_ID=global.anthropic.claude-opus-4-6-v1
BEDROCK_REGION=us-east-1

# MySQL 配置
MYSQL_ROOT_PASSWORD=ses_sender_root_123
MYSQL_DATABASE=ses_sender
MYSQL_USER=ses_sender
MYSQL_PASSWORD=ses_sender_123
```

### 3. 启动

```bash
sudo yum install git -y
sudo yum install docker -y
sudo usermod -aG docker $USER
newgrp docker

sudo systemctl start docker
sudo systemctl enable docker

sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

git clone {Current Repo}
docker-compose up -d --build
```

首次启动时，后端会自动执行数据库迁移（Alembic）并创建默认管理员账号。

### 4. 访问

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:3000 |
| API（通过前端代理） | http://localhost:3000/api/* |

> 后端 API 仅在 Docker 内部网络可访问（端口 8000 不对外暴露），所有 API 请求通过前端 Next.js 反向代理转发。

### 5. 默认管理员

```
用户名: admin
密码:   admin123
```

> 首次登录后建议立即修改密码。

## 配置 VDM 送达率追踪

### 工作原理

```
批量发送邮件
  ↓
SES send_bulk_templated_email()
  ├── ConfigurationSetName: "ses-sender-tracking"    ← 关联 VDM
  └── DefaultTags:
        ├── batch_id: "batch-a1b2c3d4e5f6"           ← 唯一批次标识
        ├── user_id: "2"                              ← 发送用户
        ├── group_name: "VIP_customers"               ← 客群名称
        └── template_name: "welcome_email"            ← 模版名称
  ↓
CloudWatch Metrics（按 batch_id 维度）
  → Send / Delivery / Open / Bounce / Complaint / Click
  ↓
发送历史页面 → 点击"查看指标" → 实时展示送达率、打开率等
```

### 配置步骤

#### Step 1: 创建 Configuration Set

```bash
aws sesv2 create-configuration-set \
  --configuration-set-name ses-sender-tracking \
  --delivery-options TlsPolicy=OPTIONAL \
  --sending-options SendingEnabled=true \
  --reputation-options ReputationMetricsEnabled=true \
  --region us-east-1
```

#### Step 2: 关闭 Suppression List（避免邮件被抑制）

```bash
aws sesv2 put-configuration-set-suppression-options \
  --configuration-set-name ses-sender-tracking \
  --suppressed-reasons \
  --region us-east-1
```

#### Step 3: 配置 VDM 选项（关闭 Optimized Shared Delivery）

```bash
aws sesv2 put-configuration-set-vdm-options \
  --configuration-set-name ses-sender-tracking \
  --vdm-options '{
    "DashboardOptions": {"EngagementMetrics": "ENABLED"},
    "GuardianOptions": {"OptimizedSharedDelivery": "DISABLED"}
  }' \
  --region us-east-1
```

> **重要**：`OptimizedSharedDelivery` 必须设为 `DISABLED`，否则沙箱模式下邮件可能被延迟或不送达。

#### Step 4: 添加 CloudWatch Event Destination

```bash
aws sesv2 create-configuration-set-event-destination \
  --configuration-set-name ses-sender-tracking \
  --event-destination-name cloudwatch \
  --event-destination '{
    "Enabled": true,
    "MatchingEventTypes": ["SEND", "DELIVERY", "BOUNCE", "COMPLAINT", "OPEN", "CLICK"],
    "CloudWatchDestination": {
      "DimensionConfigurations": [
        {
          "DimensionName": "batch_id",
          "DimensionValueSource": "MESSAGE_TAG",
          "DefaultDimensionValue": "no_tag"
        }
      ]
    }
  }' \
  --region us-east-1
```

#### Step 5: 确保账户级别 VDM 设置正确

```bash
# 启用 VDM，但关闭 Optimized Shared Delivery
aws sesv2 put-account-vdm-attributes \
  --vdm-attributes '{
    "VdmEnabled": "ENABLED",
    "DashboardAttributes": {"EngagementMetrics": "ENABLED"},
    "GuardianAttributes": {"OptimizedSharedDelivery": "DISABLED"}
  }' \
  --region us-east-1
```

#### Step 6: 配置 SNS + SQS Event Destination（用于每封邮件的送达/打开/退信追踪）

本系统使用 **SNS → SQS → 后端轮询** 架构接收 SES 事件，无需后端暴露公网端口。

**一键执行：**

```bash
# 参数1: AWS 区域（必填）  参数2: Configuration Set 名称（可选，默认 ses-sender-tracking）
./setup-ses-events.sh us-east-1
# 或
./setup-ses-events.sh ap-northeast-1 my-config-set
```

脚本会自动完成以下操作：
1. 获取你的 AWS 账户 ID
2. 创建 SNS Topic (`ses-sender-events`)
3. 创建 SQS 队列 (`ses-sender-events-queue`)，配置长轮询和消息保留
4. 设置 SQS 队列策略，允许 SNS 向其发送消息
5. 创建 SNS → SQS 订阅
6. 在 SES Configuration Set 上添加 SNS Event Destination（追踪 SEND/DELIVERY/BOUNCE/COMPLAINT/OPEN/CLICK/REJECT）

执行完成后，脚本会输出需要添加到 `.env` 的变量。

<details>
<summary>如需手动执行，点击展开各步骤命令</summary>

```bash
# 6.1 创建 SNS Topic
aws sns create-topic \
  --name ses-sender-events \
  --region <REGION>

# 6.2 创建 SQS 队列
aws sqs create-queue \
  --queue-name ses-sender-events-queue \
  --attributes '{
    "ReceiveMessageWaitTimeSeconds": "20",
    "VisibilityTimeout": "300",
    "MessageRetentionPeriod": "1209600"
  }' \
  --region <REGION>

# 6.3 获取 SQS 队列 ARN
aws sqs get-queue-attributes \
  --queue-url <QUEUE_URL> \
  --attribute-names QueueArn \
  --region <REGION>

# 6.4 设置 SQS 队列策略（允许 SNS 向 SQS 发送消息）
# 参考 setup-ses-events.sh 中的策略 JSON

# 6.5 订阅 SNS Topic → SQS
aws sns subscribe \
  --topic-arn <TOPIC_ARN> \
  --protocol sqs \
  --notification-endpoint <QUEUE_ARN> \
  --attributes '{"RawMessageDelivery": "false"}' \
  --region <REGION>

# 6.6 添加 SNS Event Destination 到 Configuration Set
aws sesv2 create-configuration-set-event-destination \
  --configuration-set-name <CONFIG_SET> \
  --event-destination-name sns-events \
  --event-destination '{
    "Enabled": true,
    "MatchingEventTypes": ["SEND", "DELIVERY", "BOUNCE", "COMPLAINT", "OPEN", "CLICK", "REJECT"],
    "SnsDestination": {
      "TopicArn": "<TOPIC_ARN>"
    }
  }' \
  --region <REGION>
```

</details>

#### Step 7: 配置环境变量并重启

```bash
# 编辑 .env 文件，添加 SQS_QUEUE_URL
SES_CONFIGURATION_SET=ses-sender-tracking
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/YOUR_ACCOUNT_ID/ses-sender-events-queue

# 重新创建容器（restart 不会读取新的环境变量）
docker-compose down && docker-compose up -d
```

启动后查看后端日志确认 SQS Worker 是否正常启动：

```bash
docker-compose logs -f backend | grep "SQS Worker"
# 应看到: [SQS Worker] 启动，队列: https://sqs.us-east-1.amazonaws.com/...
```

#### Step 8: 验证配置

```bash
# 检查 Configuration Set 配置
aws sesv2 get-configuration-set \
  --configuration-set-name ses-sender-tracking \
  --region us-east-1

# 检查 Event Destination
aws sesv2 get-configuration-set-event-destinations \
  --configuration-set-name ses-sender-tracking \
  --region us-east-1

# 检查后端环境变量
docker exec ses-sender-backend env | grep SES_CONFIGURATION
```

### 查看指标

配置完成后：
1. 通过平台发送一批邮件
2. **等待 15 分钟**（CloudWatch 指标有延迟，最短 5 分钟，建议等 15 分钟）
3. 在"发送历史"页面点击 **"查看指标"** 按钮
4. 弹框中会展示该批次的送达率、打开率、退信率等指标

> **注意**：只有在发送邮件时 `SES_CONFIGURATION_SET` 已生效的批次，才会有指标数据。之前未配置 Configuration Set 时发送的邮件不会有监控数据。

### 指标全部为 0 的排查清单

如果发送邮件成功但"查看指标"弹窗中所有数据为 0，请按以下步骤逐项排查：

#### 排查 1：确认 SES_CONFIGURATION_SET 环境变量已生效

```bash
# 检查后端容器内的环境变量
docker exec ses-sender-backend env | grep SES_CONFIGURATION

# 应输出类似：SES_CONFIGURATION_SET=ses-sender-tracking
# 如果为空，说明未配置或未生效
```

> 如果为空，编辑 `.env` 或 `docker-compose.yml` 设置 `SES_CONFIGURATION_SET`，然后执行 `docker-compose down && docker-compose up -d`（注意：`restart` 不会读取新的环境变量）。

#### 排查 2：确认 Configuration Set 已创建

```bash
aws sesv2 get-configuration-set \
  --configuration-set-name <你的ConfigurationSet名称> \
  --region <你的AWS区域>
```

如果返回 `NotFoundException`，说明还没创建，请回到上面的 Step 1 执行创建命令。

#### 排查 3：确认 CloudWatch Event Destination 已配置（最常见遗漏）

```bash
aws sesv2 get-configuration-set-event-destinations \
  --configuration-set-name <你的ConfigurationSet名称> \
  --region <你的AWS区域>
```

检查输出中是否有 `CloudWatchDestination`，且 `DimensionConfigurations` 包含 `batch_id` 维度。**如果没有 Event Destination，SES 事件不会写入 CloudWatch，指标永远为 0。** 请执行上面的 Step 4 添加 Event Destination。

#### 排查 4：确认 AWS_REGION 配置一致

后端的 `AWS_REGION` 环境变量必须与 SES/CloudWatch 所在区域一致。例如如果 SES 在 `ap-southeast-1`，则：

```bash
# 检查后端配置的区域
docker exec ses-sender-backend env | grep AWS_REGION

# 应与你创建 Configuration Set 的区域一致
```

#### 排查 5：确认 VDM 已启用（影响 Open/Click 指标）

```bash
aws sesv2 get-account \
  --region <你的AWS区域> \
  | grep -A5 VdmAttributes
```

如果 `VdmEnabled` 不是 `ENABLED`，Open 和 Click 指标不会被追踪。请执行上面的 Step 5。

#### 排查 6：确认等待了足够时间

CloudWatch 指标从 SES 事件产生到可查询，通常需要 **5-15 分钟**延迟。建议发送邮件后等待 15 分钟再查看。

#### 排查 7：直接在 CloudWatch 控制台验证

1. 登录 AWS 控制台 → CloudWatch → Metrics → All metrics
2. 搜索命名空间 `AWS/SES`
3. 查看是否有 `batch_id` 维度的数据
4. 如果 CloudWatch 控制台也没有 `batch_id` 维度的指标，说明 Event Destination 配置有问题

#### 排查 8：IAM 权限

确保 EC2 的 IAM Role 包含以下 CloudWatch 权限：

```json
{
  "Effect": "Allow",
  "Action": [
    "cloudwatch:GetMetricStatistics",
    "cloudwatch:ListMetrics"
  ],
  "Resource": "*"
}
```

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| **指标全部为 0** | 未配置 CloudWatch Event Destination | 执行 Step 4 添加 Event Destination（最常见原因） |
| **指标全部为 0** | AWS_REGION 不匹配 | 确保 `AWS_REGION` 与 SES/CloudWatch 所在区域一致 |
| **指标全部为 0** | SES_CONFIGURATION_SET 未生效 | 使用 `docker-compose down && up -d` 而非 `restart` |
| **指标全部为 0** | 数据延迟 | 等待 15 分钟后再查看 |
| **Open/Click 为 0，其他有数据** | VDM 未启用 | 执行 Step 5 启用账户级别 VDM |
| 配置 Configuration Set 后收不到邮件 | Suppression List 抑制了收件邮箱 | 关闭 Configuration Set 的 Suppression List |
| 配置 Configuration Set 后收不到邮件 | Optimized Shared Delivery 延迟投递 | 关闭账户和 Configuration Set 级别的 OptimizedSharedDelivery |
| 配置 Configuration Set 后收不到邮件 | TLS Policy 设为 REQUIRE | 改为 OPTIONAL |
| SES 返回 Success 但邮件未送达 | Tag 值包含中文等非 ASCII 字符 | 系统已自动过滤，确保使用最新版本 |
| 环境变量修改后不生效 | `docker-compose restart` 不读取新环境变量 | 使用 `docker-compose down && docker-compose up -d` |

## 升级指南

### 升级到最新版本

```bash
# 1. 拉取最新代码
cd ses-sender
git pull origin main

# 2. 检查是否有新增环境变量（对比 .env.example）
diff <(sort .env) <(sort .env.example)
# 如有新增变量，按需添加到 .env

# 3. 重建并重启（数据库迁移自动执行）
docker-compose down
docker-compose up -d --build

# 4. 确认服务正常
docker-compose ps
docker-compose logs --tail=10 backend | grep Alembic
```

### 升级说明

| 项目 | 说明 |
|------|------|
| 数据库迁移 | 后端启动时 Alembic 自动执行 `upgrade head`，无需手动操作 |
| MySQL 数据 | 持久化在 `./data/mysql/`，升级不丢失 |
| 上传文件 | 持久化在 `./data/uploads/`，升级不丢失 |
| 环境变量 | 新版本可能新增变量，升级前对比 `.env.example` |
| 重启方式 | 必须 `docker-compose down && up -d --build`，不能用 `restart` |

### 回滚

```bash
# 查看历史版本
git log --oneline -10

# 回到指定版本
git checkout <commit-hash>
docker-compose down && docker-compose up -d --build

# 如需回滚数据库迁移
docker exec ses-sender-backend alembic downgrade -1
```

## 数据库迁移

本项目使用 Alembic 管理数据库版本。服务启动时会自动检查并执行迁移。

```bash
# 生成新的迁移脚本（修改 models 后）
docker exec ses-sender-backend alembic revision --autogenerate -m "描述信息"

# 将迁移文件拷贝到本地
docker cp ses-sender-backend:/app/alembic/versions/ backend/alembic/versions

# 手动执行迁移
docker exec ses-sender-backend alembic upgrade head

# 查看当前版本
docker exec ses-sender-backend alembic current

# 查看迁移历史
docker exec ses-sender-backend alembic history
```

## 常用运维命令

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker logs ses-sender-backend
docker logs ses-sender-frontend
docker logs ses-sender-mysql

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 重建并启动
docker-compose up -d --build

# 重新创建容器（应用环境变量修改）
docker-compose down && docker-compose up -d

# 进入 MySQL 命令行
docker exec -it ses-sender-mysql mysql -u ses_sender -pses_sender_123 ses_sender
```

## IAM 权限要求

EC2 实例的 IAM Role 需要以下权限：

```json
{
  "Effect": "Allow",
  "Action": [
    "ses:ListIdentities",
    "ses:GetIdentityVerificationAttributes",
    "ses:VerifyEmailIdentity",
    "ses:VerifyDomainIdentity",
    "ses:ListTemplates",
    "ses:CreateTemplate",
    "ses:UpdateTemplate",
    "ses:DeleteTemplate",
    "ses:SendEmail",
    "ses:SendBulkTemplatedEmail",
    "sesv2:SendEmail",
    "sesv2:CreateEmailTemplate",
    "sesv2:UpdateEmailTemplate",
    "sesv2:DeleteEmailTemplate",
    "sesv2:GetAccount",
    "cloudwatch:GetMetricStatistics",
    "cloudwatch:ListMetrics",
    "sns:CreateTopic",
    "sns:Subscribe",
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:GetQueueAttributes",
    "bedrock:InvokeModel"
  ],
  "Resource": "*"
}
```

## 注意事项

1. **SES 沙箱模式**：新账户默认在沙箱模式，只能向已验证邮箱发送。需在 AWS 控制台申请移出沙箱。
2. **发送速率限制**：系统自动从 SES 获取 `MaxSendRate`，按 `min(MaxSendRate, 50)` 每秒发送，每批次后暂停 1 秒。
3. **异步发送**：批量发送为异步模式，API 立即返回批次 ID，后台线程执行发送，前端可实时查看发送进度。
4. **发送邮箱**：普通用户的发送邮箱由管理员配置，用户无法自行修改。域名验证后可配置任意 `user@yourdomain.com` 格式的邮箱。
5. **模版隔离**：每个用户独立维护自己的邮件模版，SES 中的模版名会自动加用户前缀避免冲突。
6. **VDM Tag 限制**：SES Message Tag 值只允许 ASCII 字符，系统会自动将中文等非 ASCII 字符替换为下划线。
7. **SQS 事件追踪**：配置 `SQS_QUEUE_URL` 后，后端自动轮询 SQS 获取每封邮件的送达/退信/打开/点击事件。未配置时服务正常启动，仅无法追踪单封邮件状态。
8. **Configuration Set 注意事项**：
   - 必须关闭 Suppression List 和 Optimized Shared Delivery
   - TLS Policy 建议设为 OPTIONAL
   - 修改环境变量后需要 `docker-compose down && docker-compose up -d`，`restart` 不会生效

## 一键退订

系统支持 Gmail/Yahoo 一键退订要求（RFC 8058）：

- 配置 `UNSUBSCRIBE_BASE_URL` 后，每封邮件自动添加 `List-Unsubscribe` 和 `List-Unsubscribe-Post` 头部
- `POST /unsubscribe` — RFC 8058 标准处理接口（邮件客户端自动调用）
- `GET /unsubscribe` — 退订确认页面（浏览器访问时展示）
- 已退订的联系人在后续发送中自动跳过
- 退订令牌使用 HMAC-SHA256 签名防止伪造
- 在"退订管理"页面可查看所有退订记录，支持"恢复发送"操作

**配置方式**：在 `.env` 中设置 `UNSUBSCRIBE_BASE_URL` 为公网可访问的后端 URL（如 `https://api.example.com`）。

> 也可在邮件模版中使用 `{{unsubscribe_url}}` 变量插入自定义退订链接。模版编辑器提供"插入退订链接"快捷按钮。

## AI 邮件模版优化

基于 AWS Bedrock（Claude）的邮件模版智能优化功能：

- 一键分析邮件模版，从送达率、打开率、点击率、移动端适配、合规性等维度提供优化建议
- AI 自动生成优化后的主题行和 HTML 内容
- 支持对比原始内容和优化结果（主题和 HTML 预览并排展示）
- **迭代优化**：对 AI 结果不满意时，可输入修改建议让 AI 基于上次结果再次优化
- 采纳后一键应用到模版编辑器

**配置方式**：在 `.env` 中设置：
```env
BEDROCK_MODEL_ID=global.anthropic.claude-opus-4-6-v1
BEDROCK_REGION=us-east-1
```

**IAM 权限**：需要 `bedrock:InvokeModel` 权限。

## 联系人自定义属性

联系人支持自定义 JSON 属性，用于个性化邮件内容：

- 在联系人管理中可为每个联系人设置键值对属性（如 `company`、`city`、`plan` 等）
- Excel 导入时，除 `name` 和 `email` 列外的其他列自动识别为自定义属性
- Excel 导出时，自定义属性自动展开为独立列
- 在邮件模版中使用 `{{属性名}}` 引用（如 `{{company}}`、`{{city}}`）
- 发送时系统自动将联系人属性替换到模版变量中

## 每日发送配额

管理员可为每个用户设置每日邮件发送限额（默认 1000 封/天）：

- 管理员在创建/编辑用户时设置 `每日发送限额`，用户列表显示每个用户的配额使用进度条
- 用户发送邮件前自动检查当日已发送量，超限返回 HTTP 429 拒绝
- 用户批量发送页面顶部展示配额使用进度（已用/剩余/总限额），颜色自适应
- 发送完成后自动刷新配额数据
- 配额按 UTC 日期重置

## 数据概览 Dashboard

每个用户登录后默认进入数据概览页面，包含：

- **统计卡片**：今日发送、本月发送、历史总量、成功批次
- **配额进度条**：今日发送量 vs 每日限额，颜色自适应（绿/橙/红）
- **最近 7 天趋势**：柱状图展示每日发送量
- **送达指标**：送达率、打开率、点击率、退信率、投诉率（带进度条和百分比）
- **最近发送记录**：最近 5 个批次的摘要信息

## 定时发送

支持单次定时发送和周期性自动发送：

| 类型 | 说明 |
|------|------|
| 单次定时 | 指定一个未来时间点发送，执行后自动标记为"已完成" |
| 每天 | 每天在指定时间（UTC）自动发送 |
| 每周 | 每周指定星期几的指定时间自动发送 |
| 每月 | 每月指定日期的指定时间自动发送 |

**工作原理**：
- 后台调度线程每 30 秒检查一次到期任务（`next_run_at <= now` 且 `status = active`）
- 到期后调用 `send_bulk_email()` 执行发送，遵守所有现有规则（配额限制、退订过滤、速率限制等）
- 周期任务执行后自动计算下次执行时间
- 支持暂停/恢复/删除操作
- 发送结果（批次 ID、错误信息）记录在任务中

## AI 编码助手支持

项目内置了多个 AI 编码工具的指令文件，帮助 AI 理解项目上下文：

| 文件 | 适用工具 |
|------|---------|
| `AGENTS.md` | 通用（Claude Code / Kiro / 任何 AI 工具） |
| `CLAUDE.md` | Claude Code |
| `.github/copilot-instructions.md` | GitHub Copilot |
| `.cursor/rules/ses-sender.md` | Cursor |

## License

MIT
