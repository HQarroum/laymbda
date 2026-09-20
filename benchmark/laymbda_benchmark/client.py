"""Locust-compatible client for synchronous AWS Lambda invocations."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

import boto3
import gevent
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from locust.env import Environment

from laymbda_benchmark.config import BenchmarkSettings
from laymbda_benchmark.models import Fixture, InvocationSample, SampleOutcome
from laymbda_benchmark.recorder import SampleRecorder

# Timeout longer than the deployed Lambda timeout to receive service errors cleanly.
CLIENT_READ_TIMEOUT_SECONDS = 35

# Short delay preventing throttled users from creating a tight retry loop.
THROTTLE_BACKOFF_SECONDS = 0.25


class LambdaFunctionError(RuntimeError):
    """Represent a Lambda invocation that returned ``FunctionError``."""


class LambdaClient:
    """Invoke Lambda directly and publish each result to Locust."""

    def __init__(
        self,
        environment: Environment,
        settings: BenchmarkSettings,
        fixture: Fixture,
        recorder: SampleRecorder,
    ) -> None:
        """Create a retry-free Lambda client for accurate load measurements.

        Args:
            environment: Locust environment receiving request events.
            settings: Resolved benchmark and AWS configuration.
            fixture: Serialized Laya request invoked by every user.
            recorder: Process-local raw sample writer.
        """

        self._environment = environment
        self._settings = settings
        self._fixture = fixture
        self._recorder = recorder
        self._client = boto3.client(
            "lambda",
            region_name=settings.region,
            config=Config(
                connect_timeout=5,
                max_pool_connections=settings.max_connections,
                read_timeout=CLIENT_READ_TIMEOUT_SECONDS,
                retries={
                    "mode": "standard",
                    "total_max_attempts": 1,
                },
            ),
        )

    def invoke(self) -> dict[str, Any] | None:
        """Invoke the configured Lambda alias and record the observation.

        Returns:
            The decoded Lambda response, or ``None`` when the AWS request fails.
        """

        started_at = datetime.now(UTC)
        start_time = time.time()
        started_counter = time.perf_counter()
        response_body: dict[str, Any] | None = None
        response_length = 0
        request_id: str | None = None
        executed_version: str | None = None
        outcome: SampleOutcome = "success"
        exception: Exception | None = None

        try:
            response = self._client.invoke(
                FunctionName=self._settings.function_name,
                InvocationType="RequestResponse",
                Payload=self._fixture.payload,
                Qualifier=self._settings.qualifier,
            )
            executed_version = response.get("ExecutedVersion")
            raw_response = response["Payload"].read()
            response_length = len(raw_response)
            response_body = _decode_response(raw_response)
            request_id = _extract_request_id(response_body)

            if response.get("FunctionError"):
                outcome = "function_error"
                exception = LambdaFunctionError(
                    str(response_body.get("errorMessage", "Lambda function error"))
                )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            outcome = (
                "throttled"
                if error_code == "TooManyRequestsException"
                else "client_error"
            )
            exception = error
        except (BotoCoreError, ValueError) as error:
            outcome = "client_error"
            exception = error

        wall_ms = (time.perf_counter() - started_counter) * 1_000
        sample = InvocationSample(
            started_at=started_at.isoformat(),
            fixture=self._fixture.name,
            wall_ms=round(wall_ms, 3),
            outcome=outcome,
            request_id=request_id,
            executed_version=executed_version,
            response_bytes=response_length,
            error=str(exception) if exception else None,
        )
        self._recorder.record(sample)
        self._environment.events.request.fire(
            request_type="Lambda",
            name=self._fixture.name,
            start_time=start_time,
            response_time=wall_ms,
            response_length=response_length,
            response=response_body,
            context={
                "executed_version": executed_version,
                "request_id": request_id,
            },
            exception=exception,
        )
        if outcome == "throttled":
            gevent.sleep(THROTTLE_BACKOFF_SECONDS)

        return response_body


def _decode_response(value: bytes) -> dict[str, Any]:
    """Decode a Lambda response payload as a JSON object.

    Args:
        value: Raw bytes returned by the Lambda Invoke API.

    Returns:
        The decoded JSON response object.

    Raises:
        ValueError: If the response is not a JSON object.
    """

    response: Any = json.loads(value)
    if not isinstance(response, dict):
        raise ValueError("Lambda response must be a JSON object.")
    return response


def _extract_request_id(response: dict[str, Any]) -> str | None:
    """Extract the Lambda request ID from success or error responses.

    Args:
        response: Decoded Lambda response object.

    Returns:
        The request ID when one is present.
    """

    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        request_id = metadata.get("request_id")
        if isinstance(request_id, str):
            return request_id

    request_id = response.get("requestId")
    return request_id if isinstance(request_id, str) else None
