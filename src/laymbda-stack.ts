import * as cdk from 'aws-cdk-lib';
import type { Construct } from 'constructs';
import { LayaInference } from './constructs/laya-inference.js';

/**
 * Hugging Face model repository baked into the image.
 */
const LAYA_MODEL_ID = 'convaiinnovations/laya';

/**
 * Exact Hugging Face commit baked into the image.
 */
const LAYA_MODEL_REVISION = '1c5edc17a7acd8701df6fc341c0d179f1c62c982';

/**
 * Lambda memory selected for the initial real-world benchmark.
 * @type {number} in mebibytes
 */
const FUNCTION_MEMORY_MB: number = 4_096;

/**
 * Maximum time allowed for one inference invocation.
 */
const FUNCTION_TIMEOUT = cdk.Duration.seconds(30);

/**
 * PyTorch CPU workers matched to the Lambda memory allocation.
 */
const TORCH_THREADS = 2;

/**
 * Safety ceiling for simultaneous model environments during initial testing.
 */
const RESERVED_CONCURRENCY = 10;

/**
 * Infrastructure for serverless Laya inference.
 */
export class LaymbdaStack extends cdk.Stack {
  /**
   * Laya inference service deployed by the stack.
   */
  public readonly inference: LayaInference;

  /**
   * Create the Laymbda infrastructure.
   * @param scope - Parent CDK construct.
   * @param id - Logical stack identifier.
   * @param props - Stack properties.
   */
  public constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope, id, {
      description: 'Serverless Laya inference on AWS Lambda.',
      ...props
    });

    // Create the Laya inference construct.
    this.inference = new LayaInference(this, 'Inference', {
      memorySize: FUNCTION_MEMORY_MB,
      modelId: LAYA_MODEL_ID,
      modelRevision: LAYA_MODEL_REVISION,
      reservedConcurrency: RESERVED_CONCURRENCY,
      timeout: FUNCTION_TIMEOUT,
      torchThreads: TORCH_THREADS
    });

    // Output the Lambda function name.
    new cdk.CfnOutput(this, 'FunctionName', {
      description: 'Lambda function name.',
      value: this.inference.function.functionName
    });

    // Output the ARN of the SnapStart-enabled live alias.
    new cdk.CfnOutput(this, 'LiveAliasArn', {
      description: 'ARN of the SnapStart-enabled live alias.',
      value: this.inference.liveAlias.functionArn
    });

    // Output the log group used to enrich benchmark samples.
    new cdk.CfnOutput(this, 'LogGroupName', {
      description: 'CloudWatch Logs group containing Lambda execution reports.',
      value: this.inference.logGroup.logGroupName
    });
  }
}
