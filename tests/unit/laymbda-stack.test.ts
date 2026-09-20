import * as cdk from 'aws-cdk-lib';
import * as assertions from 'aws-cdk-lib/assertions';

import { describe, expect, it } from 'vitest';
import { LaymbdaStack } from '../../src/laymbda-stack.js';

/**
 * Account used only while synthesizing unit-test templates.
 */
const TEST_ACCOUNT = '111111111111';

/**
 * Region used only while synthesizing unit-test templates.
 */
const TEST_REGION = 'eu-west-1';

/**
 * Unit tests for the `LaymbdaStack`.
 */
describe('LaymbdaStack', () => {
  it('creates an x86_64 image function with SnapStart', () => {
    const app = new cdk.App();
    const stack = new LaymbdaStack(app, 'TestStack', {
      env: {
        account: TEST_ACCOUNT,
        region: TEST_REGION
      }
    });
    const template = assertions.Template.fromStack(stack);

    template.hasResourceProperties('AWS::Lambda::Function', {
      Architectures: ['x86_64'],
      Environment: {
        Variables: assertions.Match.objectLike({
          HF_HUB_OFFLINE: '1',
          LAYA_MODEL_PATH: '/opt/laya-model',
          POWERTOOLS_SERVICE_NAME: 'inference',
          TORCH_THREADS: '2'
        })
      },
      MemorySize: 4_096,
      PackageType: 'Image',
      ReservedConcurrentExecutions: 10,
      SnapStart: {
        ApplyOn: 'PublishedVersions'
      },
      Timeout: 30,
      TracingConfig: {
        Mode: 'Active'
      }
    });

    template.hasResourceProperties('AWS::Lambda::Alias', {
      Name: 'live'
    });
    template.hasOutput('LogGroupName', {
      Description: 'CloudWatch Logs group containing Lambda execution reports.'
    });
    expect(stack.inference.liveAlias.aliasName).toBe('live');
  });

  it('does not grant the runtime access to Amazon S3', () => {
    const app = new cdk.App();
    const stack = new LaymbdaStack(app, 'TestStack', {
      env: {
        account: TEST_ACCOUNT,
        region: TEST_REGION
      }
    });
    const template = assertions.Template.fromStack(stack);
    const policies = template.findResources('AWS::IAM::Policy');

    expect(JSON.stringify(policies).toLowerCase()).not.toContain('s3:');
  });
});
