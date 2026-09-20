"""Resolve benchmark settings, stack outputs, and request fixtures."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3

from laymbda_benchmark.models import Fixture

# Directory containing the benchmark project.
BENCHMARK_DIRECTORY = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BenchmarkSettings:
    """Configuration required by the Lambda invocation client."""

    region: str
    stack_name: str
    function_name: str
    qualifier: str
    fixture_path: Path
    results_directory: Path
    run_id: str
    max_connections: int


@dataclass(frozen=True, slots=True)
class StackOutputs:
    """CloudFormation outputs consumed by benchmark tooling."""

    function_name: str
    log_group_name: str


def create_settings(options: Namespace) -> BenchmarkSettings:
    """Create validated benchmark settings from Locust arguments.

    Args:
        options: Parsed Locust command-line options.

    Returns:
        Fully resolved settings for one benchmark process.

    Raises:
        ValueError: If the connection count is not positive.
    """

    if options.max_connections < 1:
        raise ValueError("--max-connections must be greater than zero.")

    function_name = (
        options.function_name
        or resolve_stack_outputs(
            options.aws_region,
            options.stack_name,
        ).function_name
    )
    run_id = options.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    return BenchmarkSettings(
        region=options.aws_region,
        stack_name=options.stack_name,
        function_name=function_name,
        qualifier=options.lambda_qualifier,
        fixture_path=_resolve_path(options.fixture),
        results_directory=_resolve_path(options.results_directory),
        run_id=run_id,
        max_connections=options.max_connections,
    )


def resolve_stack_outputs(region: str, stack_name: str) -> StackOutputs:
    """Read function and log-group names from CloudFormation outputs.

    Args:
        region: AWS Region containing the stack.
        stack_name: Name of the deployed CloudFormation stack.

    Returns:
        Function and log-group names exported by the stack.

    Raises:
        RuntimeError: If a required output is absent.
    """

    client = boto3.client("cloudformation", region_name=region)
    response = client.describe_stacks(StackName=stack_name)
    outputs = {
        output["OutputKey"]: output["OutputValue"]
        for output in response["Stacks"][0].get("Outputs", [])
    }

    try:
        return StackOutputs(
            function_name=outputs["FunctionName"],
            log_group_name=outputs["LogGroupName"],
        )
    except KeyError as error:
        raise RuntimeError(
            f"Stack output {error.args[0]!r} is required by the benchmark."
        ) from error


def load_fixture(path: Path) -> Fixture:
    """Load and minimally validate a serialized Laya request.

    Args:
        path: JSON fixture containing ``state`` and ``questions``.

    Returns:
        The fixture name, path, and compact serialized payload.

    Raises:
        ValueError: If the fixture is not a Laya request object.
    """

    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not {"state", "questions"} <= value.keys():
        raise ValueError(f"{path} is not a Laya request fixture.")

    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return Fixture(name=path.stem, path=path, payload=payload)


def _resolve_path(value: str) -> Path:
    """Resolve a CLI path relative to the benchmark directory.

    Args:
        value: Absolute or benchmark-relative path.

    Returns:
        The normalized absolute path.
    """

    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        path = BENCHMARK_DIRECTORY / path
    return path.resolve()
