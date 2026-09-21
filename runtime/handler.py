"""Validate a Laya request and run it inside AWS Lambda."""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools.utilities.typing import LambdaContext
from inference import INFERENCE
from observability import LOGGER, TRACER
from protocol import InvalidRequestError, validate_request


@LOGGER.inject_lambda_context(clear_state=True)
@TRACER.capture_lambda_handler
def handler(
    event: object,
    context: LambdaContext,
) -> dict[str, Any]:
    """Validate and execute one Laya inference request.

    Args:
        event: Lambda event containing Laya ``state`` and ``questions`` fields.
        context: Runtime metadata supplied by AWS Lambda.

    Returns:
        Laya's native result with the Lambda request ID attached as metadata.

    Raises:
        InvalidRequestError: If the event is malformed or Laya rejects its
            question definitions.
    """

    # Validate the incoming request against the expected schema.
    try:
        request = validate_request(event)
    except InvalidRequestError:
        LOGGER.warning("Request validation failed")
        raise

    # Execute the inference request.
    try:
        result, duration_ms = INFERENCE.predict(request)
    except ValueError as error:
        LOGGER.warning(
            "Laya rejected the validated request",
            extra={"error_type": type(error).__name__},
        )
        raise InvalidRequestError(f"Laya rejected the request: {error}") from error

    # Logging inference completion details.
    LOGGER.info(
        "Inference completed",
        extra={
            "duration_ms": round(duration_ms, 2),
            "question_count": len(request.questions),
        },
    )

    return result | {
        "metadata": {
            "request_id": context.aws_request_id,
        },
    }
