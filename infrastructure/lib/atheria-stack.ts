import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export class AtheriaStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly cluster: ecs.Cluster;
  public readonly database: rds.DatabaseInstance;
  public readonly evidenceBucket: s3.Bucket;
  public readonly userPool: cognito.UserPool;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // --- VPC ---
    this.vpc = new ec2.Vpc(this, 'AtheriaVpc', {
      maxAzs: 2,
      natGateways: 1, // Cost optimization for dev
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
        {
          name: 'isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // --- S3 Evidence Bucket ---
    this.evidenceBucket = new s3.Bucket(this, 'EvidenceBucket', {
      bucketName: `atheria-evidence-${this.region}-${this.account}`,
      versioned: true, // MVP: versioning. Pre-pilot: add Object Lock
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        {
          id: 'move-to-ia-after-90-days',
          transitions: [
            {
              storageClass: s3.StorageClass.INFREQUENT_ACCESS,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
      ],
    });

    // --- RDS PostgreSQL ---
    const dbSecret = new secretsmanager.Secret(this, 'DbSecret', {
      secretName: 'atheria/db-credentials',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: 'atheria' }),
        generateStringKey: 'password',
        excludePunctuation: true,
        passwordLength: 32,
      },
    });

    this.database = new rds.DatabaseInstance(this, 'AtheriaDb', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16_3,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T4G,
        ec2.InstanceSize.SMALL
      ),
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      credentials: rds.Credentials.fromSecret(dbSecret),
      databaseName: 'atheria',
      allocatedStorage: 20,
      maxAllocatedStorage: 100,
      multiAz: false, // Dev only — enable for production
      deletionProtection: false,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Dev only
      backupRetention: cdk.Duration.days(7),
      cloudwatchLogsExports: ['postgresql'],
      parameterGroup: new rds.ParameterGroup(this, 'DbParams', {
        engine: rds.DatabaseInstanceEngine.postgres({
          version: rds.PostgresEngineVersion.VER_16_3,
        }),
        parameters: {
          'shared_preload_libraries': 'pg_stat_statements',
        },
      }),
    });

    // --- ECS Cluster ---
    this.cluster = new ecs.Cluster(this, 'AtheriaCluster', {
      vpc: this.vpc,
      clusterName: 'atheria',
      containerInsights: true,
    });

    // --- ECR Repository ---
    const backendRepo = new ecr.Repository(this, 'BackendRepo', {
      repositoryName: 'atheria-backend',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      lifecycleRules: [
        {
          maxImageCount: 10,
          description: 'Keep last 10 images',
        },
      ],
    });

    // --- Cognito User Pool ---
    this.userPool = new cognito.UserPool(this, 'AtheriaUserPool', {
      userPoolName: 'atheria-users',
      selfSignUpEnabled: false, // Admin-only user creation
      signInAliases: { email: true },
      standardAttributes: {
        email: { required: true, mutable: false },
        givenName: { required: true, mutable: true },
        familyName: { required: true, mutable: true },
      },
      customAttributes: {
        tenant_id: new cognito.StringAttribute({ mutable: false }),
        role: new cognito.StringAttribute({ mutable: true }),
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: {
        sms: false,
        otp: true,
      },
    });

    const userPoolClient = this.userPool.addClient('AtheriaWebClient', {
      userPoolClientName: 'atheria-web',
      authFlows: {
        userSrp: true,
        userPassword: false,
      },
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
        callbackUrls: ['http://localhost:5173/callback', 'https://app.atheria.ai/callback'],
        logoutUrls: ['http://localhost:5173/', 'https://app.atheria.ai/'],
      },
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    });

    // --- ECS Fargate Service (Backend API) ---
    const backendTaskDef = new ecs.FargateTaskDefinition(this, 'BackendTask', {
      memoryLimitMiB: 1024,
      cpu: 512,
    });

    backendTaskDef.addContainer('backend', {
      image: ecs.ContainerImage.fromEcrRepository(backendRepo, 'latest'),
      portMappings: [{ containerPort: 8000 }],
      environment: {
        ATHERIA_ENVIRONMENT: 'dev',
        ATHERIA_AWS_REGION: this.region,
        ATHERIA_EVIDENCE_BUCKET: this.evidenceBucket.bucketName,
        ATHERIA_COGNITO_USER_POOL_ID: this.userPool.userPoolId,
        ATHERIA_COGNITO_APP_CLIENT_ID: userPoolClient.userPoolClientId,
      },
      secrets: {
        ATHERIA_DATABASE_URL: ecs.Secret.fromSecretsManager(dbSecret),
      },
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'atheria-backend',
        logRetention: logs.RetentionDays.ONE_MONTH,
      }),
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:8000/api/v1/health || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
      },
    });

    // Grant permissions
    this.evidenceBucket.grantReadWrite(backendTaskDef.taskRole);
    this.database.connections.allowDefaultPortFrom(
      new ec2.Connections({
        securityGroups: [
          new ec2.SecurityGroup(this, 'BackendSG', { vpc: this.vpc }),
        ],
      })
    );

    // --- Outputs ---
    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId });
    new cdk.CfnOutput(this, 'DbEndpoint', { value: this.database.instanceEndpoint.hostname });
    new cdk.CfnOutput(this, 'EvidenceBucketName', { value: this.evidenceBucket.bucketName });
    new cdk.CfnOutput(this, 'UserPoolId', { value: this.userPool.userPoolId });
    new cdk.CfnOutput(this, 'UserPoolClientId', { value: userPoolClient.userPoolClientId });
    new cdk.CfnOutput(this, 'EcrRepoUri', { value: backendRepo.repositoryUri });
  }
}
