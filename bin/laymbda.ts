#!/usr/bin/env node

import * as cdk from 'aws-cdk-lib';

import { awsEnvironment } from '../src/config/env.js';
import { LaymbdaStack } from '../src/laymbda-stack.js';

/**
 * The environment configuration for the CDK stack.
 */
const env: cdk.Environment =
  awsEnvironment.CDK_DEFAULT_ACCOUNT === undefined
    ? {
        region: awsEnvironment.CDK_DEFAULT_REGION
      }
    : {
        account: awsEnvironment.CDK_DEFAULT_ACCOUNT,
        region: awsEnvironment.CDK_DEFAULT_REGION
      };

/**
 * The CDK application that owns the Laymbda stack.
 */
const app = new cdk.App();

/**
 * The `LaymbdaStack` CDK stack instance.
 */
const stack = new LaymbdaStack(app, 'LaymbdaStack', { env });

/**
 * Acknowledge the AWS CDK SnapStart requirement warning for the Lambda function.
 */
cdk.Annotations.of(stack).acknowledgeWarning(
  '@aws-cdk/aws-lambda:snapStartRequirePublish',
  'The stack publishes the current function version behind the live alias.'
);
