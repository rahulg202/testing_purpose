#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { AtheriaStack } from '../lib/atheria-stack';

const app = new cdk.App();

const env = app.node.tryGetContext('environment') || 'dev';

new AtheriaStack(app, `Atheria-${env}`, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
  },
  description: `Atheria PV Intelligence Platform - ${env}`,
  tags: {
    Project: 'Atheria',
    Environment: env,
    ManagedBy: 'CDK',
  },
});
