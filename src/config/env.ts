import { z } from 'zod';

/**
 * AWS environment variables supplied by the CDK CLI.
 */
const AwsEnvironmentSchema = z
  .object({

    /**
     * AWS account that receives the synthesized stack.
     */
    CDK_DEFAULT_ACCOUNT: z
      .string()
      .regex(/^\d{12}$/)
      .optional(),

    /**
     * AWS Region used when the CDK CLI does not provide one.
     */
    CDK_DEFAULT_REGION: z.string().min(1)
  })
  .strict();

/**
 * Parsed AWS environment used by the CDK application.
 */
export type AwsEnvironment = z.infer<typeof AwsEnvironmentSchema>;

/**
 * Parse the CDK environment at the process boundary.
 * @returns The validated AWS environment.
 */
const parseAwsEnvironment = (): AwsEnvironment => {
  const result = AwsEnvironmentSchema.safeParse({
    CDK_DEFAULT_ACCOUNT: process.env.CDK_DEFAULT_ACCOUNT,
    CDK_DEFAULT_REGION: process.env.CDK_DEFAULT_REGION
  });

  if (!result.success) {
    throw new Error(`Invalid AWS environment: ${result.error.message}`);
  }

  return (result.data);
};

/**
 * Validated AWS account and Region for the CDK application.
 */
export const awsEnvironment = parseAwsEnvironment();
