import * as path from 'node:path';
import * as cdk from 'aws-cdk-lib';
import * as assets from 'aws-cdk-lib/aws-ecr-assets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';

import { Construct } from 'constructs';

/**
 * Configuration for the Laya inference construct.
 */
export type LayaInferenceProps = {

  /**
   * Hugging Face model repository baked into the container image.
   */
  modelId: string;

  /**
   * Exact Hugging Face commit baked into the container image.
   */
  modelRevision: string;

  /**
   * Memory allocated to each Lambda execution environment.
   */
  memorySize: number;

  /**
   * Maximum number of simultaneous execution environments.
   */
  reservedConcurrency: number;

  /**
   * Number of CPU threads assigned to PyTorch.
   */
  torchThreads: number;

  /**
   * Maximum duration of one inference invocation.
   */
  timeout: cdk.Duration;
};

/**
 * A SnapStart-enabled Lambda function containing the Laya model and weights.
 */
export class LayaInference extends Construct {

  /**
   * CloudWatch Logs group receiving runtime and execution reports.
   */
  public readonly logGroup: logs.LogGroup;

  /**
   * Container-image Lambda function running Laya.
   */
  public readonly function: lambda.DockerImageFunction;

  /**
   * Stable alias backed by the current SnapStart-enabled version.
   */
  public readonly liveAlias: lambda.Alias;

  /**
   * Construct the Laya inference service.
   * @param scope - Parent CDK construct.
   * @param id - Construct identifier.
   * @param props - Inference configuration.
   */
  public constructor(scope: Construct, id: string, props: LayaInferenceProps) {
    super(scope, id);

    // Create the log group for the Lambda function.
    this.logGroup = new logs.LogGroup(this, 'Logs', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      retention: logs.RetentionDays.ONE_WEEK
    });

    // Create the execution role for the Lambda function.
    const executionRole = this.createExecutionRole(this.logGroup);

    // Create the SnapStart-enabled Lambda function for Laya inference.
    this.function = new lambda.DockerImageFunction(this, 'Function', {
      architecture: lambda.Architecture.X86_64,
      code: this.createImageCode(props),
      currentVersionOptions: {
        removalPolicy: cdk.RemovalPolicy.DESTROY
      },
      description: 'Runs typed Laya decisions without text generation.',
      environment: {
        HF_HUB_OFFLINE: '1',
        LAYA_MODEL_PATH: '/opt/laya-model',
        POWERTOOLS_LOGGER_LOG_EVENT: 'false',
        POWERTOOLS_LOG_LEVEL: 'INFO',
        POWERTOOLS_SERVICE_NAME: 'inference',
        POWERTOOLS_TRACER_CAPTURE_RESPONSE: 'false',
        TOKENIZERS_PARALLELISM: 'false',
        TORCH_THREADS: props.torchThreads.toString(),
        TRANSFORMERS_VERBOSITY: 'error'
      },
      logGroup: this.logGroup,
      memorySize: props.memorySize,
      reservedConcurrentExecutions: props.reservedConcurrency,
      role: executionRole,
      snapStart: lambda.SnapStartConf.ON_PUBLISHED_VERSIONS,
      timeout: props.timeout,
      tracing: lambda.Tracing.ACTIVE
    });

    // SnapStart-enabled stable alias for the Lambda function.
    this.liveAlias = this.function.addAlias('live', {
      description: 'Stable entry point for the SnapStart-enabled version.'
    });
  }

  /**
   * Create the least-privilege role used by the inference runtime.
   * @param logGroup - Log group receiving runtime logs.
   * @returns The Lambda execution role.
   */
  private createExecutionRole(logGroup: logs.ILogGroup): iam.Role {
    const executionRole = new iam.Role(this, 'ExecutionRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'Writes Laymbda logs and X-Ray trace segments.'
    });

    // Allow the Lambda function to write logs to the specified log group.
    executionRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['logs:CreateLogStream', 'logs:PutLogEvents'],
        effect: iam.Effect.ALLOW,
        resources: [`${logGroup.logGroupArn}:*`]
      })
    );

    // Allow the Lambda function to write X-Ray trace segments.
    executionRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['xray:PutTelemetryRecords', 'xray:PutTraceSegments'],
        effect: iam.Effect.ALLOW,
        resources: ['*']
      })
    );

    return (executionRole);
  }

  /**
   * Create the x86_64 image asset containing the pinned model revision.
   * @param props - Inference configuration used as Docker build arguments.
   * @returns The Lambda container-image code.
   */
  private createImageCode(
    props: Pick<LayaInferenceProps, 'modelId' | 'modelRevision'>
  ): lambda.DockerImageCode {
    return lambda.DockerImageCode.fromImageAsset(
      path.resolve(import.meta.dirname, '..', '..', 'runtime'),
      {
        buildArgs: {
          LAYA_MODEL_ID: props.modelId,
          LAYA_MODEL_REVISION: props.modelRevision
        },
        platform: assets.Platform.LINUX_AMD64
      }
    );
  }
}
