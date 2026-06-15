#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { SesSenderStack } from "../lib/ses-sender-stack";

const app = new cdk.App();

/**
 * 部署区域与账户：
 *   优先使用 CDK 上下文 / 环境变量，否则回退到 CLI 默认账户与区域。
 *   SES 必须部署在已开通 SES 的区域（默认 us-east-1）。
 */
const account =
  app.node.tryGetContext("account") ||
  process.env.CDK_DEPLOY_ACCOUNT ||
  process.env.CDK_DEFAULT_ACCOUNT;

const region =
  app.node.tryGetContext("region") ||
  process.env.CDK_DEPLOY_REGION ||
  process.env.CDK_DEFAULT_REGION ||
  "us-east-1";

new SesSenderStack(app, "SesSenderStack", {
  env: { account, region },
  description:
    "SES Sender one-click deployment: CloudFront + ALB + ECS Fargate (frontend/backend/mcp) + Aurora MySQL + SES/SNS/SQS + Bedrock",
  // ---- 可通过 -c key=value 覆盖的部署参数 ----
  configurationSetName:
    app.node.tryGetContext("configurationSetName") || "ses-sender-tracking",
  bedrockModelId:
    app.node.tryGetContext("bedrockModelId") ||
    "global.anthropic.claude-opus-4-6-v1",
  // 是否启用 NAT 网关（多 AZ HA 成本更高，默认单 NAT 省钱）
  natGateways: Number(app.node.tryGetContext("natGateways") ?? 1),
});

app.synth();
