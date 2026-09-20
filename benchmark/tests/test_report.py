"""Tests for Lambda log parsing and percentile calculations."""

from laymbda_benchmark.report import (
    collect_telemetry,
    parse_inference_message,
    parse_report_message,
    summarize,
)


def test_parse_report_message_includes_snapstart_fields() -> None:
    """Parse duration, memory, and restore values from a REPORT line."""

    message = (
        "REPORT RequestId: request-1\t"
        "Duration: 2235.24 ms\t"
        "Billed Duration: 2466 ms\t"
        "Memory Size: 6144 MB\t"
        "Max Memory Used: 3015 MB\t"
        "Restore Duration: 2810.55 ms\t"
        "Billed Restore Duration: 230 ms"
    )

    telemetry = parse_report_message(message)

    assert telemetry is not None
    assert telemetry.request_id == "request-1"
    assert telemetry.duration_ms == 2235.24
    assert telemetry.restore_duration_ms == 2810.55
    assert telemetry.max_memory_mb == 3015


def test_parse_inference_message_reads_structured_logging() -> None:
    """Read inference duration and cold-start state from a Powertools log."""

    message = (
        '{"message":"Inference completed","function_request_id":"request-1",'
        '"duration_ms":381.5,"cold_start":true}'
    )

    assert parse_inference_message(message) == ("request-1", 381.5, True)


def test_summarize_uses_nearest_rank_percentiles() -> None:
    """Calculate stable percentile values from sorted latency samples."""

    summary = summarize(float(value) for value in range(1, 101))

    assert summary is not None
    assert summary.average == 50.5
    assert summary.p50 == 50
    assert summary.p95 == 95
    assert summary.p99 == 99


def test_collect_telemetry_merges_application_and_report_logs() -> None:
    """Retain model timing when the REPORT message arrives last."""

    messages = [
        (
            '{"message":"Inference completed","function_request_id":"request-1",'
            '"duration_ms":381.5,"cold_start":true}'
        ),
        (
            "REPORT RequestId: request-1\t"
            "Duration: 386.01 ms\t"
            "Billed Duration: 405 ms\t"
            "Memory Size: 6144 MB\t"
            "Max Memory Used: 3015 MB\t"
            "Restore Duration: 2110.54 ms\t"
            "Billed Restore Duration: 18 ms"
        ),
    ]

    telemetry = collect_telemetry(messages)["request-1"]

    assert telemetry.inference_duration_ms == 381.5
    assert telemetry.duration_ms == 386.01
    assert telemetry.restore_duration_ms == 2110.54
    assert telemetry.is_cold_start is True
