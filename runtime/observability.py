"""Shared AWS Lambda Powertools providers."""

from aws_lambda_powertools import Logger, Tracer

# Structured application logger configured by CDK environment variables.
LOGGER = Logger()

# AWS X-Ray tracer for Lambda invocations and downstream work.
TRACER = Tracer()
