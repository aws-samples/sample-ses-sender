# SES Sender — AWS CDK 一键部署

用 [AWS CDK](https://docs.aws.amazon.com/cdk/) 把整套 SES Sender 部署到 AWS，**一条命令搞定**所有基础设施，无需手动建 VPC / 数据库 / SES 事件链路。

## 部署后得到什么

对应项目架构图，本栈自动创建：

| 组件 | 说明 |
|------|------|
| **VPC** | 2 AZ，公有子网（ALB/NAT）+ 私有子网（ECS/Aurora），默认单 NAT 省钱 |
| **CloudFront** | 公网入口 + HTTPS，回源 ALB |
| **ALB** | 转发到前端容器 |
| **ECS Fargate** | 3 个服务：`frontend`(Next.js) / `backend`(FastAPI+发送引擎+SQS Worker) / `mcp`(MCP Server)，经 Service Connect 互通（`http://backend:8000`） |
| **Aurora MySQL** | 3.10（`db.r8g.large` Graviton4 实例 + 自定义参数组），凭据存 Secrets Manager |
| **SES Configuration Set** | 开启 VDM、关闭 Optimized Shared Delivery、TLS=OPTIONAL |
| **事件链路** | SES → SNS → SQS（长轮询）+ CloudWatch（按 `batch_id` 维度出指标） |
| **账户级 VDM** | 自定义资源自动 `PutAccountVdmAttributes`（开启参与度指标） |
| **密钥** | JWT `SECRET_KEY`、数据库密码、MCP API Key 全部由 Secrets Manager 生成并注入容器，**无 AK/SK** |

容器镜像由 CDK 用本仓库 `backend/` `frontend/` `mcp-server/` 的 Dockerfile **本地构建并推送到 ECR**（需本机有 Docker）。

## 前置要求

- Node.js ≥ 18 与 npm
- Docker（构建容器镜像用）
- AWS CLI 已配置凭据，且账号对目标区域有管理权限
- 目标区域已可用 SES（默认 `us-east-1`）

## 一键部署

```bash
cd cdk
npm install

# 首次在该账号/区域使用 CDK 需先 bootstrap（只需一次）
npx cdk bootstrap

# 部署（自动构建镜像 + 创建全部资源）
npm run deploy
```

部署完成后，终端输出里的 **`AppUrl`** 就是访问地址（CloudFront）。默认管理员：

```
用户名: admin
密码:   admin123      # 首次登录请立即修改
```

## 可选参数

通过 `-c key=value` 覆盖（或编辑 `bin/ses-sender.ts`）：

```bash
# 指定区域 / 账户
npx cdk deploy -c region=ap-northeast-1 -c account=123456789012

# 自定义 Configuration Set 名称
npx cdk deploy -c configurationSetName=my-tracking

# 高可用：多 AZ NAT（成本更高）
npx cdk deploy -c natGateways=2

# 自定义 Bedrock 模型
npx cdk deploy -c bedrockModelId=global.anthropic.claude-opus-4-6-v1
```

也可用环境变量 `CDK_DEPLOY_ACCOUNT` / `CDK_DEPLOY_REGION`。

## 部署后必做

1. **验证发件身份**：登录应用 → 管理员 → 发送实体，验证发件邮箱或域名（域名需按提示加 DNS 记录）。
2. **移出 SES 沙箱**：新账户默认沙箱，只能发已验证邮箱。在 AWS 控制台 SES → 申请生产访问权限。
3. **等指标**：发送后 CloudWatch 指标有 5–15 分钟延迟，再到「发送历史 → 查看指标」查看。

> 退订链接 `UNSUBSCRIBE_BASE_URL` 已自动设为 `<CloudFront 域名>/api`，邮件中的一键退订（RFC 8058）开箱即用。

## 与本地 docker-compose 的关系

- 本地开发/试用：仓库根目录 `docker-compose up -d --build`（MySQL 容器 + 单机）。
- 生产部署：本目录 CDK（Aurora + ECS Fargate + CloudFront + 托管事件链路）。

两者共用同一套后端/前端代码。后端已支持云原生数据库注入：设置 `DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`/`DB_PORT` 时优先使用（密码经 Secrets Manager 注入，不落明文），未设置则回退到 `DATABASE_URL`。

## 常用命令

```bash
npm run synth      # 生成 CloudFormation 模板（含本地构建镜像）
npm run diff       # 对比变更
npm run deploy     # 部署
npm run destroy    # 销毁全部资源（Aurora 默认保留快照）
```

## 安全说明

- **ALB 不直接暴露到公网**：ALB 安全组只放行 AWS 托管的 CloudFront origin-facing 前缀列表，外部无法绕过 CloudFront 直连 ALB。
- **默认（新建 VPC）模式**：ECS 容器与 Aurora 都在**私有子网**，经 NAT 出网，不暴露公网；Aurora 仅允许应用层安全组访问。
- **复用 VPC 模式（`-c vpcId=`）**：为应对 VPC 配额限制，工作负载放在**公有子网**并分配公网 IP（省 NAT）。Aurora 仍非公开访问（安全组锁定），但生产环境建议用默认新建 VPC 模式。
- **密钥**：JWT / DB / MCP 密钥均由 Secrets Manager 生成注入，不落明文；容器全程用 IAM Role，无 AK/SK。
- **务必**：首次登录后立即修改默认管理员密码 `admin/admin123`；SES 移出沙箱前只能发已验证邮箱。

## 销毁

```bash
npm run destroy
```

> Aurora 的 `RemovalPolicy` 为 `SNAPSHOT`，销毁时会留一份快照，避免误删数据。如需彻底删除，手动到 RDS 删除快照。

## 成本提示

主要成本：NAT 网关（~$32/月/个）、ALB（~$16/月）、Aurora（`db.r8g.large` 实例按小时计费）、Fargate（3 个小任务）、CloudFront/SES 按量。试用建议 `natGateways=1`。

---

作者：CrypticDriver &lt;nerdtsai@proton.me&gt; · License: MIT
