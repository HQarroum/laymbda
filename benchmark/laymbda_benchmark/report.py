"""Enrich raw Locust samples with Lambda execution telemetry."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any

import boto3

from laymbda_benchmark.config import resolve_stack_outputs
from laymbda_benchmark.models import InvocationSample

# Lambda REPORT fields emitted for every completed invocation.
REPORT_PATTERN = re.compile(
    r"REPORT RequestId: (?P<request_id>\S+)\s+"
    r"Duration: (?P<duration>[\d.]+) ms\s+"
    r"Billed Duration: (?P<billed_duration>\d+) ms\s+"
    r"Memory Size: (?P<memory_size>\d+) MB\s+"
    r"Max Memory Used: (?P<max_memory>\d+) MB"
    r"(?:\s+Restore Duration: (?P<restore_duration>[\d.]+) ms\s+"
    r"Billed Restore Duration: (?P<billed_restore_duration>\d+) ms)?"
)

# Padding around sample timestamps while querying eventually delivered log events.
LOG_QUERY_MARGIN = timedelta(minutes=2)


@dataclass(slots=True)
class ExecutionTelemetry:
    """Server-side measurements associated with one Lambda request."""

    request_id: str
    duration_ms: float | None = None
    billed_duration_ms: int | None = None
    memory_size_mb: int | None = None
    max_memory_mb: int | None = None
    restore_duration_ms: float | None = None
    billed_restore_duration_ms: int | None = None
    inference_duration_ms: float | None = None
    is_cold_start: bool | None = None


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Descriptive statistics for one latency measurement."""

    count: int
    average: float
    minimum: float
    p50: float
    p95: float
    p99: float
    maximum: float


def parse_report_message(message: str) -> ExecutionTelemetry | None:
    """Parse one Lambda ``REPORT`` log message.

    Args:
        message: Raw CloudWatch Logs event message.

    Returns:
        Parsed execution telemetry, or ``None`` for unrelated messages.
    """

    match = REPORT_PATTERN.search(message)
    if match is None:
        return None

    values = match.groupdict()
    return ExecutionTelemetry(
        request_id=values["request_id"],
        duration_ms=float(values["duration"]),
        billed_duration_ms=int(values["billed_duration"]),
        memory_size_mb=int(values["memory_size"]),
        max_memory_mb=int(values["max_memory"]),
        restore_duration_ms=_optional_float(values["restore_duration"]),
        billed_restore_duration_ms=_optional_int(values["billed_restore_duration"]),
    )


def parse_inference_message(message: str) -> tuple[str, float, bool] | None:
    """Parse one structured successful-inference log message.

    Args:
        message: Raw CloudWatch Logs event message.

    Returns:
        Request ID, model inference duration, and cold-start flag when present.
    """

    try:
        value: Any = json.loads(message)
    except json.JSONDecodeError:
        return None

    if not isinstance(value, dict) or value.get("message") != "Inference completed":
        return None

    request_id = value.get("function_request_id")
    duration_ms = value.get("duration_ms")
    is_cold_start = value.get("cold_start")
    if (
        not isinstance(request_id, str)
        or not isinstance(duration_ms, int | float)
        or not isinstance(is_cold_start, bool)
    ):
        return None

    return request_id, float(duration_ms), is_cold_start


def collect_telemetry(messages: Iterable[str]) -> dict[str, ExecutionTelemetry]:
    """Join Lambda report and application logs by request ID.

    Args:
        messages: CloudWatch Logs messages from the benchmark window.

    Returns:
        Server-side telemetry indexed by Lambda request ID.
    """

    telemetry: dict[str, ExecutionTelemetry] = {}

    for message in messages:
        report = parse_report_message(message)
        if report is not None:
            record = telemetry.setdefault(
                report.request_id,
                ExecutionTelemetry(request_id=report.request_id),
            )
            record.duration_ms = report.duration_ms
            record.billed_duration_ms = report.billed_duration_ms
            record.memory_size_mb = report.memory_size_mb
            record.max_memory_mb = report.max_memory_mb
            record.restore_duration_ms = report.restore_duration_ms
            record.billed_restore_duration_ms = report.billed_restore_duration_ms
            continue

        inference = parse_inference_message(message)
        if inference is None:
            continue

        request_id, duration_ms, is_cold_start = inference
        record = telemetry.setdefault(
            request_id,
            ExecutionTelemetry(request_id=request_id),
        )
        record.inference_duration_ms = duration_ms
        record.is_cold_start = is_cold_start

    return telemetry


def summarize(values: Iterable[float]) -> MetricSummary | None:
    """Calculate deterministic nearest-rank latency statistics.

    Args:
        values: Numeric observations to summarize.

    Returns:
        Summary statistics, or ``None`` when no observations are available.
    """

    samples = sorted(values)
    if not samples:
        return None

    return MetricSummary(
        count=len(samples),
        average=round(fmean(samples), 3),
        minimum=round(samples[0], 3),
        p50=round(_percentile(samples, 50), 3),
        p95=round(_percentile(samples, 95), 3),
        p99=round(_percentile(samples, 99), 3),
        maximum=round(samples[-1], 3),
    )


def build_report(
    samples: list[InvocationSample],
    telemetry: dict[str, ExecutionTelemetry],
    function_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Build the final benchmark report.

    Args:
        samples: Raw client-side invocation observations.
        telemetry: Lambda measurements indexed by request ID.
        function_configuration: Deployed Lambda configuration under test.

    Returns:
        JSON-compatible benchmark summary.

    Raises:
        ValueError: If no raw invocation samples were supplied.
    """

    if not samples:
        raise ValueError("At least one invocation sample is required.")

    successful = [sample for sample in samples if sample.outcome == "success"]
    matched_pairs = [
        (sample, telemetry[sample.request_id])
        for sample in successful
        if sample.request_id in telemetry
    ]
    matched = [record for _, record in matched_pairs]
    warm_pairs = [
        (sample, record)
        for sample, record in matched_pairs
        if record.is_cold_start is False
    ]
    cold_pairs = [
        (sample, record)
        for sample, record in matched_pairs
        if record.restore_duration_ms is not None
    ]
    elapsed_seconds = _elapsed_seconds(samples)
    outcomes = Counter(sample.outcome for sample in samples)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "function": {
            "name": function_configuration.get("FunctionName"),
            "version": function_configuration.get("Version"),
            "memory_mb": function_configuration.get("MemorySize"),
            "timeout_seconds": function_configuration.get("Timeout"),
            "architecture": function_configuration.get("Architectures", [None])[0],
            "snapstart": function_configuration.get("SnapStart"),
        },
        "samples": {
            "total": len(samples),
            "successful": len(successful),
            "outcomes": dict(sorted(outcomes.items())),
            "matched_cloudwatch_records": len(matched),
            "warm_invocations": len(warm_pairs),
            "restored_invocations": len(cold_pairs),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "throughput_per_second": round(
                len(successful) / elapsed_seconds,
                3,
            ),
        },
        "latency_ms": {
            "client_wall": _as_dict(summarize(sample.wall_ms for sample in successful)),
            "warm_client_wall": _as_dict(
                summarize(sample.wall_ms for sample, _ in warm_pairs)
            ),
            "cold_client_wall": _as_dict(
                summarize(sample.wall_ms for sample, _ in cold_pairs)
            ),
            "lambda_duration": _as_dict(
                summarize(
                    record.duration_ms
                    for record in matched
                    if record.duration_ms is not None
                )
            ),
            "warm_lambda_duration": _as_dict(
                summarize(
                    record.duration_ms
                    for _, record in warm_pairs
                    if record.duration_ms is not None
                )
            ),
            "cold_lambda_duration": _as_dict(
                summarize(
                    record.duration_ms
                    for _, record in cold_pairs
                    if record.duration_ms is not None
                )
            ),
            "model_inference": _as_dict(
                summarize(
                    record.inference_duration_ms
                    for record in matched
                    if record.inference_duration_ms is not None
                )
            ),
            "warm_model_inference": _as_dict(
                summarize(
                    record.inference_duration_ms
                    for _, record in warm_pairs
                    if record.inference_duration_ms is not None
                )
            ),
            "cold_model_inference": _as_dict(
                summarize(
                    record.inference_duration_ms
                    for _, record in cold_pairs
                    if record.inference_duration_ms is not None
                )
            ),
            "snapstart_restore": _as_dict(
                summarize(
                    record.restore_duration_ms
                    for record in matched
                    if record.restore_duration_ms is not None
                )
            ),
            "cold_lambda_total": _as_dict(
                summarize(
                    record.restore_duration_ms + record.duration_ms
                    for _, record in cold_pairs
                    if record.restore_duration_ms is not None
                    and record.duration_ms is not None
                )
            ),
        },
        "billing": {
            "billed_duration_ms": _as_dict(
                summarize(
                    float(record.billed_duration_ms)
                    for record in matched
                    if record.billed_duration_ms is not None
                )
            ),
            "billed_restore_duration_ms": _as_dict(
                summarize(
                    float(record.billed_restore_duration_ms)
                    for record in matched
                    if record.billed_restore_duration_ms is not None
                )
            ),
        },
        "memory": {
            "peak_used_mb": max(
                (
                    record.max_memory_mb
                    for record in matched
                    if record.max_memory_mb is not None
                ),
                default=None,
            )
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown report for humans.

    Args:
        report: JSON-compatible benchmark report.

    Returns:
        Markdown summary containing configuration, outcomes, and percentiles.
    """

    function = report["function"]
    samples = report["samples"]
    rows = [
        _metric_row(name, summary)
        for name, summary in report["latency_ms"].items()
        if summary is not None
    ]
    table = "\n".join(rows)

    return (
        "# Laymbda benchmark\n\n"
        f"- Function: `{function['name']}:{function['version']}`\n"
        f"- Memory: `{function['memory_mb']} MB`\n"
        f"- Successful invocations: `{samples['successful']}/{samples['total']}`\n"
        f"- Throughput: `{samples['throughput_per_second']} invocations/second`\n"
        f"- Peak memory used: `{report['memory']['peak_used_mb']} MB`\n\n"
        "## Latency\n\n"
        "| Measurement | Samples | Average | p50 | p95 | p99 | Maximum |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{table}\n"
    )


def load_samples(paths: Iterable[Path]) -> list[InvocationSample]:
    """Load invocation samples from one or more JSONL files.

    Args:
        paths: Raw sample files produced by benchmark workers.

    Returns:
        Samples sorted by invocation start time.
    """

    samples = [
        InvocationSample.from_json(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    return sorted(samples, key=lambda sample: sample.started_at)


def load_log_messages(
    region: str,
    log_group_name: str,
    samples: list[InvocationSample],
) -> list[str]:
    """Read CloudWatch messages covering the benchmark interval.

    Args:
        region: AWS Region containing the Lambda log group.
        log_group_name: CloudWatch Logs group used by the function.
        samples: Client-side samples defining the time window.

    Returns:
        Raw CloudWatch Logs event messages.
    """

    starts = [datetime.fromisoformat(sample.started_at) for sample in samples]
    completions = [
        started + timedelta(milliseconds=sample.wall_ms)
        for started, sample in zip(starts, samples, strict=True)
    ]
    start_ms = int((min(starts) - LOG_QUERY_MARGIN).timestamp() * 1_000)
    end_ms = int((max(completions) + LOG_QUERY_MARGIN).timestamp() * 1_000)
    client = boto3.client("logs", region_name=region)
    paginator = client.get_paginator("filter_log_events")

    return [
        event["message"]
        for page in paginator.paginate(
            logGroupName=log_group_name,
            startTime=start_ms,
            endTime=end_ms,
        )
        for event in page.get("events", [])
    ]


def write_report(report: dict[str, Any], output: Path) -> None:
    """Write JSON and Markdown forms of a benchmark report.

    Args:
        report: JSON-compatible benchmark report.
        output: Output path prefix without an extension.
    """

    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(
        f"{json.dumps(report, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    output.with_suffix(".md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )


def main() -> None:
    """Generate a report from raw Locust invocation samples."""

    parser = argparse.ArgumentParser(
        description="Join Laymbda benchmark samples with CloudWatch logs."
    )
    parser.add_argument("samples", nargs="+", type=Path)
    parser.add_argument("--aws-region", default="eu-west-1")
    parser.add_argument("--stack-name", default="LaymbdaStack")
    parser.add_argument("--lambda-qualifier", default="live")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/benchmark-report"),
    )
    arguments = parser.parse_args()

    samples = load_samples(arguments.samples)
    outputs = resolve_stack_outputs(arguments.aws_region, arguments.stack_name)
    messages = load_log_messages(
        arguments.aws_region,
        outputs.log_group_name,
        samples,
    )
    telemetry = collect_telemetry(messages)
    lambda_client = boto3.client("lambda", region_name=arguments.aws_region)
    configuration = lambda_client.get_function_configuration(
        FunctionName=outputs.function_name,
        Qualifier=arguments.lambda_qualifier,
    )
    report = build_report(samples, telemetry, configuration)
    write_report(report, arguments.output)


def _optional_float(value: str | None) -> float | None:
    """Convert an optional string into a floating-point number.

    Args:
        value: Optional numeric string.

    Returns:
        Parsed number, or ``None`` when the input is absent.
    """

    return float(value) if value is not None else None


def _optional_int(value: str | None) -> int | None:
    """Convert an optional string into an integer.

    Args:
        value: Optional integer string.

    Returns:
        Parsed integer, or ``None`` when the input is absent.
    """

    return int(value) if value is not None else None


def _percentile(samples: list[float], percentile: int) -> float:
    """Return a nearest-rank percentile from sorted samples.

    Args:
        samples: Non-empty observations sorted in ascending order.
        percentile: Percentile between 1 and 100.

    Returns:
        The nearest-rank observation.
    """

    index = max(0, math.ceil((percentile / 100) * len(samples)) - 1)
    return samples[index]


def _elapsed_seconds(samples: list[InvocationSample]) -> float:
    """Calculate wall-clock duration covered by invocation samples.

    Args:
        samples: Non-empty client-side invocation observations.

    Returns:
        Elapsed seconds from the earliest start to the latest completion.
    """

    starts = [datetime.fromisoformat(sample.started_at) for sample in samples]
    completions = [
        started + timedelta(milliseconds=sample.wall_ms)
        for started, sample in zip(starts, samples, strict=True)
    ]
    return max((max(completions) - min(starts)).total_seconds(), 0.001)


def _as_dict(summary: MetricSummary | None) -> dict[str, Any] | None:
    """Convert an optional metric summary into JSON-compatible data.

    Args:
        summary: Calculated metric statistics.

    Returns:
        A dictionary representation, or ``None`` when no summary exists.
    """

    return asdict(summary) if summary is not None else None


def _metric_row(name: str, summary: dict[str, Any]) -> str:
    """Render one Markdown latency table row.

    Args:
        name: Machine-readable measurement name.
        summary: Calculated metric statistics.

    Returns:
        Markdown table row with millisecond values.
    """

    return (
        f"| {name.replace('_', ' ')} "
        f"| {summary['count']} "
        f"| {summary['average']:.3f} ms "
        f"| {summary['p50']:.3f} ms "
        f"| {summary['p95']:.3f} ms "
        f"| {summary['p99']:.3f} ms "
        f"| {summary['maximum']:.3f} ms |"
    )


if __name__ == "__main__":
    main()
