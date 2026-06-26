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
import * as ecrAssets from "aws-cdk-lib/aws-ecr-assets";
import * as elasticache from "aws-cdk-lib/aws-elasticache";
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
    // 镜像与 Fargate 运行时架构。默认 X86_64（与常见 x86 构建主机一致，免 QEMU 跨架构模拟）。
    // 如需 Graviton(ARM64) 降本，用 -c arch=arm64（要求构建主机为 ARM 或已装 QEMU/buildx）。
    const archCtx = (this.node.tryGetContext("arch") as string | undefined) || "x86_64";
    const isArm = archCtx.toLowerCase() === "arm64";
    const cpuArchitecture = isArm
      ? ecs.CpuArchitecture.ARM64
      : ecs.CpuArchitecture.X86_64;
    const imagePlatform = isArm
      ? ecrAssets.Platform.LINUX_ARM64
      : ecrAssets.Platform.LINUX_AMD64;

    // ============================================================
    // 1. 网络层 — 新建 VPC，或复用已有 VPC（-c vpcId=vpc-xxx，适用于 VPC 配额已满）
    // ============================================================
    const existingVpcId = this.node.tryGetContext("vpcId") as string | undefined;
    let vpc: ec2.IVpc;
    let workloadSubnets: ec2.SubnetSelection;
    let assignPublicIp: boolean;

    if (existingVpcId) {
      // 复用已有 VPC：工作负载放公有子网（Fargate 分配公网 IP 出网，免 NAT）
      vpc = ec2.Vpc.fromLookup(this, "Vpc", { vpcId: existingVpcId });
      workloadSubnets = { subnetType: ec2.SubnetType.PUBLIC };
      assignPublicIp = true;
    } else {
      vpc = new ec2.Vpc(this, "Vpc", {
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
      workloadSubnets = { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS };
      assignPublicIp = false;
    }

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
    // 3. 数据库层 — Aurora MySQL 3.10（t4g.xlarge 实例 + 自定义参数组）
    // ============================================================
    const auroraEngine = rds.DatabaseClusterEngine.auroraMysql({
      version: rds.AuroraMysqlEngineVersion.VER_3_10_4,
    });

    // 自定义集群参数组
    const dbParameterGroup = new rds.ParameterGroup(this, "AuroraParams", {
      engine: auroraEngine,
      description: "SES Sender custom Aurora MySQL cluster parameter group",
      parameters: {
        character_set_server: "utf8mb4",
        collation_server: "utf8mb4_unicode_ci",
      },
    });

    const dbCluster = new rds.DatabaseCluster(this, "Aurora", {
      engine: auroraEngine,
      credentials: rds.Credentials.fromSecret(dbSecret),
      defaultDatabaseName: DB_NAME,
      vpc,
      vpcSubnets: workloadSubnets,
      parameterGroup: dbParameterGroup,
      writer: rds.ClusterInstance.provisioned("writer", {
        instanceType: ec2.InstanceType.of(
          ec2.InstanceClass.MEMORY8_GRAVITON,
          ec2.InstanceSize.LARGE
        ),
      }),
      removalPolicy: RemovalPolicy.SNAPSHOT,
      storageEncrypted: true,
    });

    // ---- ElastiCache Redis（全局发送令牌桶限流）----
    const redisSg = new ec2.SecurityGroup(this, "RedisSg", {
      vpc,
      description: "SES Sender Redis (global rate-limit token bucket)",
      allowAllOutbound: true,
    });
    const redisSubnetGroup = new elasticache.CfnSubnetGroup(this, "RedisSubnets", {
      description: "SES Sender Redis subnet group",
      subnetIds: vpc.selectSubnets(workloadSubnets).subnetIds,
    });
    const redis = new elasticache.CfnCacheCluster(this, "Redis", {
      engine: "redis",
      cacheNodeType: "cache.t4g.micro",
      numCacheNodes: 1,
      vpcSecurityGroupIds: [redisSg.securityGroupId],
      cacheSubnetGroupName: redisSubnetGroup.ref,
    });
    redis.addDependency(redisSubnetGroup);
    const redisUrl = `redis://${redis.attrRedisEndpointAddress}:${redis.attrRedisEndpointPort}/0`;

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

    // ---- 发送任务队列（内部任务分发：Producer → SQS → 多实例 Consumer）----
    const sendDlq = new sqs.Queue(this, "SendDlq", {
      queueName: "ses-sender-send-dlq",
      retentionPeriod: Duration.days(14),
    });
    const sendQueue = new sqs.Queue(this, "SendQueue", {
      queueName: "ses-sender-send-queue",
      receiveMessageWaitTime: Duration.seconds(20), // 长轮询
      visibilityTimeout: Duration.seconds(120),     // 略大于单封发送耗时，失败自动重投
      retentionPeriod: Duration.days(4),
      deadLetterQueue: { queue: sendDlq, maxReceiveCount: 5 },
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

    // 统一的应用层安全组（3 个服务共用，组内互通）。
    // 避免跨服务 SG 交叉引用，从而能安全地给客户端服务加 backend 依赖。
    const ecsSg = new ec2.SecurityGroup(this, "EcsSg", {
      vpc,
      description: "SES Sender app tier (frontend/backend/mcp)",
      allowAllOutbound: true,
    });
    ecsSg.addIngressRule(ecsSg, ec2.Port.allTraffic(), "intra app tier");

    // ---- ALB（公网入口）与 CloudFront。ALB 仅允许 CloudFront 访问，不对公网裸露 ----
    const alb = new elbv2.ApplicationLoadBalancer(this, "Alb", {
      vpc,
      internetFacing: true,
    });
    // open:false 不加 0.0.0.0/0；仅放行 CloudFront 源站 IP（AWS 托管前缀列表）。
    const listener = alb.addListener("Http", { port: 80, open: false });

    // 查找 CloudFront origin-facing 托管前缀列表 ID（各区域不同）
    const cfPrefixList = new cr.AwsCustomResource(this, "CfPrefixList", {
      onUpdate: {
        service: "EC2",
        action: "describeManagedPrefixLists",
        parameters: {
          Filters: [
            {
              Name: "prefix-list-name",
              Values: ["com.amazonaws.global.cloudfront.origin-facing"],
            },
          ],
        },
        physicalResourceId: cr.PhysicalResourceId.of("cf-origin-prefix-list"),
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE,
      }),
      installLatestAwsSdk: false,
    });
    const cfPrefixListId = cfPrefixList.getResponseField(
      "PrefixLists.0.PrefixListId"
    );
    alb.connections.allowFrom(
      ec2.Peer.prefixList(cfPrefixListId),
      ec2.Port.tcp(80),
      "CloudFront origin-facing only"
    );

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
          "ses:GetTemplate",
          "ses:CreateEmailTemplate",
          "ses:UpdateEmailTemplate",
          "ses:DeleteEmailTemplate",
          "ses:GetEmailTemplate",
          "ses:ListEmailTemplates",
          "ses:SendEmail",
          "ses:SendBulkTemplatedEmail",
          "sesv2:SendEmail",
          "sesv2:SendBulkEmail",
          "sesv2:CreateEmailTemplate",
          "sesv2:UpdateEmailTemplate",
          "sesv2:DeleteEmailTemplate",
          "sesv2:GetEmailTemplate",
          "sesv2:ListEmailTemplates",
          "sesv2:GetAccount",
          "ses:GetAccount",
          "ses:GetAccountSendingEnabled",
          "ses:GetSendQuota",
          "ses:GetSendStatistics",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "bedrock:InvokeModel",
        ],
        resources: ["*"],
      })
    );
    eventQueue.grantConsumeMessages(backendTaskRole);
    eventTopic.grantPublish(backendTaskRole);
    // 发送队列：Producer 投递 + Consumer 消费
    sendQueue.grantSendMessages(backendTaskRole);
    sendQueue.grantConsumeMessages(backendTaskRole);
    // 允许应用层访问 Redis
    redisSg.addIngressRule(ecsSg, ec2.Port.tcp(6379), "app tier to redis");

    // ---- Backend Task Definition ----
    const backendTask = new ecs.FargateTaskDefinition(this, "BackendTask", {
      cpu: 512,
      memoryLimitMiB: 1024,
      taskRole: backendTaskRole,
      runtimePlatform: { cpuArchitecture },
    });
    const backendContainer = backendTask.addContainer("backend", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "backend"), { platform: imagePlatform }),
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
        // SQS 发送队列 + Redis 全局令牌桶（大批量 / 多实例水平扩展）
        SEND_QUEUE_URL: sendQueue.queueUrl,
        ENABLE_PRODUCER: "true",
        ENABLE_CONSUMER: "true",
        SEND_CONSUMER_THREADS: "4",
        GLOBAL_SEND_RATE: "0",
        REDIS_URL: redisUrl,
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
      assignPublicIp,
      vpcSubnets: workloadSubnets,
      securityGroups: [ecsSg],
      serviceConnectConfiguration: {
        services: [
          { portMappingName: "backend", dnsName: "backend", port: 8000 },
        ],
      },
    });
    dbCluster.connections.allowDefaultPortFrom(ecsSg, "app to aurora");

    // ---- Frontend Task Definition + Service（接 ALB，反代 backend）----
    const frontendTask = new ecs.FargateTaskDefinition(this, "FrontendTask", {
      cpu: 256,
      memoryLimitMiB: 512,
      runtimePlatform: { cpuArchitecture },
    });
    const frontendContainer = frontendTask.addContainer("frontend", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "frontend"), { platform: imagePlatform }),
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
      assignPublicIp,
      vpcSubnets: workloadSubnets,
      securityGroups: [ecsSg],
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
      runtimePlatform: { cpuArchitecture },
    });
    const mcpContainer = mcpTask.addContainer("mcp", {
      image: ecs.ContainerImage.fromAsset(path.join(__dirname, "..", "..", "mcp-server"), { platform: imagePlatform }),
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
      assignPublicIp,
      vpcSubnets: workloadSubnets,
      securityGroups: [ecsSg],
      serviceConnectConfiguration: {
        services: [{ portMappingName: "mcp", dnsName: "mcp", port: 8808 }],
      },
    });

    // Service Connect 启动时序：客户端服务（frontend/mcp）必须在 backend 的 SC 别名
    // 注册之后再启动，否则 Envoy 拿不到 "backend" 别名 → ENOTFOUND。
    // （三个服务共用 ecsSg，无跨 SG 交叉引用，故不会成环）
    frontendService.node.addDependency(backendService);
    mcpService.node.addDependency(backendService);

    // ============================================================
    // 7. 输出
    // ============================================================
    new cdk.CfnOutput(this, "AppUrl", {
      value: publicUrl,
      description: "Application URL (CloudFront). Default admin login: admin / admin123",
    });
    new cdk.CfnOutput(this, "AlbDnsName", {
      value: alb.loadBalancerDnsName,
      description: "ALB DNS name (CloudFront origin)",
    });
    new cdk.CfnOutput(this, "DbEndpoint", {
      value: dbCluster.clusterEndpoint.hostname,
      description: "Aurora MySQL writer endpoint",
    });
    new cdk.CfnOutput(this, "SqsQueueUrl", {
      value: eventQueue.queueUrl,
      description: "SQS queue URL for SES event tracking",
    });
    new cdk.CfnOutput(this, "SendQueueUrl", {
      value: sendQueue.queueUrl,
      description: "SQS send queue URL (internal task dispatch)",
    });
    new cdk.CfnOutput(this, "RedisUrl", {
      value: redisUrl,
      description: "ElastiCache Redis endpoint (global send rate-limit token bucket)",
    });
    new cdk.CfnOutput(this, "ConfigurationSetName", {
      value: props.configurationSetName,
      description: "SES Configuration Set (VDM tracking)",
    });
    new cdk.CfnOutput(this, "JwtSecretArn", {
      value: jwtSecret.secretArn,
      description: "Secrets Manager ARN of the JWT SECRET_KEY",
    });
    new cdk.CfnOutput(this, "McpApiKeyArn", {
      value: mcpApiKey.secretArn,
      description: "Secrets Manager ARN of the MCP Server API key",
    });
    new cdk.CfnOutput(this, "NoteSesSandbox", {
      value:
        "SES starts in sandbox mode: request production access in the console, then verify sender email/domain in the app.",
      description: "Post-deploy note",
    });
    new cdk.CfnOutput(this, "NoteSecurity", {
      value: assignPublicIp
        ? "Reused-VPC mode: ECS/Aurora run in PUBLIC subnets (no NAT). Aurora is not publicly accessible (SG-locked), but for production prefer the default new-VPC mode (private subnets + NAT). ALB only accepts CloudFront origin-facing traffic."
        : "New-VPC mode: ECS/Aurora in private subnets behind NAT. ALB only accepts CloudFront origin-facing traffic; backend/Aurora are not exposed to the internet.",
      description: "Security posture",
    });
  }
}
