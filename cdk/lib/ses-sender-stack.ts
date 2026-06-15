import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as iam from "aws-cdk-lib/aws-iam";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as sns from "aws-cdk-lib/aws-sns";
import * as logs from "aws-cdk-lib/aws-logs";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as ses from "aws-cdk-lib/aws-ses";
import * as cr from "aws-cdk-lib/custom-resources";
import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as path from "path";

export interface SesSenderStackProps extends cdk.StackProps {
  /** SES Configuration Set 名称（VDM + 事件追踪） */
  readonly configurationSetName: string;
  /** Bedrock 模型 ID（AI 邮件优化） */
  readonly bedrockModelId: string;
  /** NAT 网关数量（1 = 省钱单 NAT；>=2 = 多 AZ 高可用） */
  readonly natGateways: number;
}

/**
 * SES Sender 一键部署栈
 *
 * 架构（对应项目架构图）：
 *   用户 → CloudFront → ALB → ECS Fargate(frontend) ──proxy──> backend
 *                                         ├─ backend  : FastAPI + 发送引擎 + SQS Worker
 *                                         └─ mcp      : MCP Server（AI agent 接入）
 *   backend → Aurora MySQL（读写）
 *   backend → SES（发信）→ SNS → SQS →（backend 长轮询拉事件）
 *   backend → Bedrock（AI 优化） / CloudWatch + VDM（拉取送达指标）
 *
 * 全程使用 ECS Task Role（无 AK/SK），数据库密码与 JWT 密钥经 Secrets Manager 注入。
 */
export class SesSenderStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: SesSenderStackProps) {
    super(scope, id, props);

    const region = cdk.Stack.of(this).region;
    const account = cdk.Stack.of(this).account;
    const DB_NAME = "ses_sender";
    const DB_USER = "ses_sender";

    // ============================================================
    // 1. 网络层 — VPC（公有子网放 ALB/NAT，私有子网放 ECS/Aurora）
    // ============================================================
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: props.natGateways,
      subnetConfiguration: [
        { name: "public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        {
          name: "private",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
      ],
    });

    // ============================================================
    // 2. 密钥层 — JWT SECRET_KEY + 数据库凭据（Secrets Manager）
    // ============================================================
    const jwtSecret = new secretsmanager.Secret(this, "JwtSecret", {
      description: "SES Sender JWT signing key (SECRET_KEY)",
      generateSecretString: {
        passwordLength: 48,
        excludePunctuation: true,
        // 直接生成一个字符串密钥
        secretStringTemplate: JSON.stringify({}),
        generateStringKey: "SECRET_KEY",
      },
    });

    const dbSecret = new secretsmanager.Secret(this, "DbSecret", {
      description: "SES Sender Aurora MySQL credentials",
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: DB_USER }),
        generateStringKey: "password",
        excludePunctuation: true,
        passwordLength: 32,
      },
    });

    // ============================================================
    // 3. 数据库层 — Aurora MySQL Serverless v2
    // ============================================================
    const dbCluster = new rds.DatabaseCluster(this, "Aurora", {
      engine: rds.DatabaseClusterEngine.auroraMysql({
        version: rds.AuroraMysqlEngineVersion.VER_3_07_1,
      }),
      credentials: rds.Credentials.fromSecret(dbSecret),
      defaultDatabaseName: DB_NAME,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 4,
      writer: rds.ClusterInstance.serverlessV2("writer"),
      removalPolicy: RemovalPolicy.SNAPSHOT,
      storageEncrypted: true,
    });

    // ============================================================
    // 4. 消息层 — SNS Topic + SQS Queue（SES 事件 → SNS → SQS → 后端轮询）
    // ============================================================
    const eventDlq = new sqs.Queue(this, "EventDlq", {
      queueName: "ses-sender-events-dlq",
      retentionPeriod: Duration.days(14),
    });

    const eventQueue = new sqs.Queue(this, "EventQueue", {
      queueName: "ses-sender-events-queue",
      receiveMessageWaitTime: Duration.seconds(20), // 长轮询
      visibilityTimeout: Duration.seconds(300),
      retentionPeriod: Duration.days(14),
      deadLetterQueue: { queue: eventDlq, maxReceiveCount: 5 },
    });

    const eventTopic = new sns.Topic(this, "EventTopic", {
      topicName: "ses-sender-events",
    });

    // SNS → SQS 订阅（RawMessageDelivery=false，与项目脚本一致）
    new sns.Subscription(this, "EventSubscription", {
      topic: eventTopic,
      protocol: sns.SubscriptionProtocol.SQS,
      endpoint: eventQueue.queueArn,
      rawMessageDelivery: false,
    });

    // 允许 SNS 向 SQS 投递（限定来源 Topic）
    eventQueue.addToResourcePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        principals: [new iam.ServicePrincipal("sns.amazonaws.com")],
        actions: ["sqs:SendMessage"],
        resources: [eventQueue.queueArn],
        conditions: { ArnEquals: { "aws:SourceArn": eventTopic.topicArn } },
      })
    );

    // ============================================================
    // 5. SES 层 — Configuration Set + VDM + 事件目的地
    //    复制 setup-ses-events.sh / README 的所有手动步骤
    // ============================================================
    const configSet = new ses.ConfigurationSet(this, "ConfigSet", {
      configurationSetName: props.configurationSetName,
      tlsPolicy: ses.ConfigurationSetTlsPolicy.OPTIONAL,
      reputationMetrics: true,
      // VDM 参与度指标（Open/Click 追踪）
      vdmOptions: { engagementMetrics: true, optimizedSharedDelivery: false },
    });

    // 5a. CloudWatch 事件目的地 — 按 batch_id 维度出指标（送达率/打开率）
    new ses.CfnConfigurationSetEventDestination(this, "CwEventDest", {
      configurationSetName: configSet.configurationSetName,
      eventDestination: {
        name: "cloudwatch",
        enabled: true,
        matchingEventTypes: [
          "SEND",
          "DELIVERY",
          "BOUNCE",
          "COMPLAINT",
          "OPEN",
          "CLICK",
        ],
        cloudWatchDestination: {
          dimensionConfigurations: [
            {
              dimensionName: "batch_id",
              dimensionValueSource: "messageTag",
              defaultDimensionValue: "no_tag",
            },
          ],
        },
      },
    });

    // 5b. SNS 事件目的地 — 每封邮件的送达/退信/打开/点击事件
    new ses.CfnConfigurationSetEventDestination(this, "SnsEventDest", {
      configurationSetName: configSet.configurationSetName,
      eventDestination: {
        name: "sns-events",
        enabled: true,
        matchingEventTypes: [
          "SEND",
          "DELIVERY",
          "BOUNCE",
          "COMPLAINT",
          "OPEN",
          "CLICK",
          "REJECT",
        ],
        snsDestination: { topicArn: eventTopic.topicArn },
      },
    });

    // 5c. 账户级 VDM 开启（put-account-vdm-attributes 无 CFN 资源，用自定义资源）
    new cr.AwsCustomResource(this, "AccountVdm", {
      onUpdate: {
        service: "SESV2",
        action: "putAccountVdmAttributes",
        parameters: {
          VdmAttributes: {
            VdmEnabled: "ENABLED",
            DashboardAttributes: { EngagementMetrics: "ENABLED" },
            GuardianAttributes: { OptimizedSharedDelivery: "DISABLED" },
          },
        },
        physicalResourceId: cr.PhysicalResourceId.of("account-vdm"),
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE,
      }),
      installLatestAwsSdk: false,
    });
    // ============================================================
    // 6. ECS 集群 + 服务发现（Service Connect）
    // ============================================================
    const cluster = new ecs.Cluster(this, "Cluster", {
      vpc,
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
      defaultCloudMapNamespace: {
        name: "ses-sender.local",
        useForServiceConnect: true,
      },
    });

    const logGroup = new logs.LogGroup(this, "LogGroup", {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // ---- ALB（公网入口）与 CloudFront 先建好，便于拿到退订公网 URL ----
    const alb = new elbv2.ApplicationLoadBalancer(this, "Alb", {
      vpc,
      internetFacing: true,
    });
    const listener = alb.addListener("Http", { port: 80, open: true });

    const distribution = new cloudfront.Distribution(this, "Cdn", {
      comment: "SES Sender frontend",
      defaultBehavior: {
        origin: new origins.LoadBalancerV2Origin(alb, {
          protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        }),
        viewerProtocolPolicy:
          cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
      },
    });
    const publicUrl = `https://${distribution.distributionDomainName}`;

    // ---- Backend Task Role（无 AK/SK，全靠 IAM Role）----
    const backendTaskRole = new iam.Role(this, "BackendTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });
    backendTaskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
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
          "sesv2:SendBulkEmail",
          "sesv2:CreateEmailTemplate",
          "sesv2:UpdateEmailTemplate",
          "sesv2:DeleteEmailTemplate",
          "sesv2:GetAccount",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "bedrock:InvokeModel",
        ],
        resources: ["*"],
      })
    );
    eventQueue.grantConsumeMessages(backendTaskRole);
    eventTopic.grantPublish(backendTaskRole);

    // ---- Backend Task Definition ----
    const backendTask = new ecs.FargateTaskDefinition(this, "BackendTask", {
      cpu: 512,
      memoryLimitMiB: 1024,
      taskRole: backendTaskRole,
    });
    const backendContainer = backendTask.addContainer("backend", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "backend")),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "backend", logGroup }),
      environment: {
        AWS_REGION: region,
        SES_CONFIGURATION_SET: props.configurationSetName,
        SQS_QUEUE_URL: eventQueue.queueUrl,
        UNSUBSCRIBE_BASE_URL: `${publicUrl}/api`,
        BEDROCK_MODEL_ID: props.bedrockModelId,
        BEDROCK_REGION: region,
        ENABLE_SENDER: "true",
        SENDER_CONCURRENCY: "2",
        SENDER_MESSAGE_RATE: "0",
        DB_HOST: dbCluster.clusterEndpoint.hostname,
        DB_PORT: "3306",
        DB_NAME: DB_NAME,
        DB_USER: DB_USER,
      },
      secrets: {
        DB_PASSWORD: ecs.Secret.fromSecretsManager(dbSecret, "password"),
        SECRET_KEY: ecs.Secret.fromSecretsManager(jwtSecret, "SECRET_KEY"),
      },
    });
    backendContainer.addPortMappings({ containerPort: 8000, name: "backend" });

    const backendService = new ecs.FargateService(this, "BackendService", {
      cluster,
      taskDefinition: backendTask,
      desiredCount: 1,
      minHealthyPercent: 100,
      circuitBreaker: { rollback: true },
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      serviceConnectConfiguration: {
        services: [
          { portMappingName: "backend", dnsName: "backend", port: 8000 },
        ],
      },
    });
    dbCluster.connections.allowDefaultPortFrom(backendService, "backend->aurora");

    // ---- Frontend Task Definition + Service（接 ALB，反代 backend）----
    const frontendTask = new ecs.FargateTaskDefinition(this, "FrontendTask", {
      cpu: 256,
      memoryLimitMiB: 512,
    });
    const frontendContainer = frontendTask.addContainer("frontend", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "frontend")),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "frontend", logGroup }),
      environment: { BACKEND_URL: "http://backend:8000" },
    });
    frontendContainer.addPortMappings({ containerPort: 3000, name: "frontend" });

    const frontendService = new ecs.FargateService(this, "FrontendService", {
      cluster,
      taskDefinition: frontendTask,
      desiredCount: 1,
      minHealthyPercent: 100,
      circuitBreaker: { rollback: true },
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      serviceConnectConfiguration: {}, // 作为客户端解析 backend
    });

    listener.addTargets("Frontend", {
      port: 3000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [frontendService],
      healthCheck: {
        path: "/",
        healthyHttpCodes: "200-399",
        interval: Duration.seconds(30),
      },
    });
    backendService.connections.allowFrom(
      frontendService,
      ec2.Port.tcp(8000),
      "frontend->backend"
    );

    // ---- MCP Server Task Definition + Service（AI agent 接入）----
    const mcpApiKey = new secretsmanager.Secret(this, "McpApiKey", {
      description: "SES Sender MCP Server API key",
      generateSecretString: {
        secretStringTemplate: JSON.stringify({}),
        generateStringKey: "MCP_API_KEY",
        excludePunctuation: true,
        passwordLength: 40,
      },
    });
    const mcpTask = new ecs.FargateTaskDefinition(this, "McpTask", {
      cpu: 256,
      memoryLimitMiB: 512,
    });
    const mcpContainer = mcpTask.addContainer("mcp", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "mcp-server")),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "mcp", logGroup }),
      environment: {
        SES_SENDER_URL: "http://backend:8000",
        MCP_PORT: "8808",
      },
      secrets: {
        MCP_API_KEY: ecs.Secret.fromSecretsManager(mcpApiKey, "MCP_API_KEY"),
      },
    });
    mcpContainer.addPortMappings({ containerPort: 8808, name: "mcp" });

    const mcpService = new ecs.FargateService(this, "McpService", {
      cluster,
      taskDefinition: mcpTask,
      desiredCount: 1,
      minHealthyPercent: 100,
      circuitBreaker: { rollback: true },
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      serviceConnectConfiguration: {
        services: [{ portMappingName: "mcp", dnsName: "mcp", port: 8808 }],
      },
    });
    backendService.connections.allowFrom(
      mcpService,
      ec2.Port.tcp(8000),
      "mcp->backend"
    );

    // ============================================================
    // 7. 输出
    // ============================================================
    new cdk.CfnOutput(this, "AppUrl", {
      value: publicUrl,
      description: "应用访问地址（CloudFront）。默认管理员 admin / admin123",
    });
    new cdk.CfnOutput(this, "AlbDnsName", {
      value: alb.loadBalancerDnsName,
      description: "ALB 域名（CloudFront 回源）",
    });
    new cdk.CfnOutput(this, "DbEndpoint", {
      value: dbCluster.clusterEndpoint.hostname,
      description: "Aurora MySQL 写入端点",
    });
    new cdk.CfnOutput(this, "SqsQueueUrl", {
      value: eventQueue.queueUrl,
      description: "SES 事件追踪 SQS 队列",
    });
    new cdk.CfnOutput(this, "ConfigurationSetName", {
      value: props.configurationSetName,
      description: "SES Configuration Set（VDM 追踪）",
    });
    new cdk.CfnOutput(this, "JwtSecretArn", {
      value: jwtSecret.secretArn,
      description: "JWT SECRET_KEY 密钥 ARN",
    });
    new cdk.CfnOutput(this, "McpApiKeyArn", {
      value: mcpApiKey.secretArn,
      description: "MCP Server API Key 密钥 ARN",
    });
    new cdk.CfnOutput(this, "NoteSesSandbox", {
      value:
        "SES 默认沙箱模式，需在控制台申请移出；并在应用内验证发件邮箱/域名。",
      description: "部署后提醒",
    });
  }
}
