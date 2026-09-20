"""Locust entry point for direct AWS Lambda load tests."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from typing import Any

from locust import User, constant, events, task
from locust.env import Environment
from locust.runners import MasterRunner

from laymbda_benchmark.client import LambdaClient
from laymbda_benchmark.config import create_settings, load_fixture
from laymbda_benchmark.recorder import SampleRecorder


@dataclass(slots=True)
class BenchmarkRuntime:
    """Resources shared by all simulated users in one Locust process."""

    client: LambdaClient
    recorder: SampleRecorder


# Runtime resources initialized when Locust starts a benchmark.
RUNTIME: BenchmarkRuntime | None = None


@events.init_command_line_parser.add_listener
def register_arguments(parser: Any) -> None:
    """Register Laymbda-specific Locust command-line arguments.

    Args:
        parser: Locust argument parser receiving benchmark options.
    """

    parser.add_argument(
        "--aws-region",
        default="eu-west-1",
        env_var="LAYMBDA_BENCHMARK_REGION",
        help="AWS Region containing the Laymbda stack.",
    )
    parser.add_argument(
        "--stack-name",
        default="LaymbdaStack",
        env_var="LAYMBDA_BENCHMARK_STACK",
        help="CloudFormation stack exposing the function name.",
    )
    parser.add_argument(
        "--function-name",
        default=None,
        env_var="LAYMBDA_BENCHMARK_FUNCTION",
        help="Optional Lambda function name override.",
    )
    parser.add_argument(
        "--lambda-qualifier",
        default="live",
        env_var="LAYMBDA_BENCHMARK_QUALIFIER",
        help="Published Lambda version or alias to invoke.",
    )
    parser.add_argument(
        "--fixture",
        default="../examples/support-ticket.json",
        env_var="LAYMBDA_BENCHMARK_FIXTURE",
        help="Path to a Laya request fixture.",
    )
    parser.add_argument(
        "--results-directory",
        default="results",
        env_var="LAYMBDA_BENCHMARK_RESULTS",
        help="Directory receiving raw invocation samples.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        env_var="LAYMBDA_BENCHMARK_RUN_ID",
        help="Stable identifier used in result filenames.",
    )
    parser.add_argument(
        "--max-connections",
        default=50,
        type=int,
        env_var="LAYMBDA_BENCHMARK_MAX_CONNECTIONS",
        help="Maximum number of AWS SDK HTTP connections.",
    )


@events.test_start.add_listener
def start_benchmark(environment: Environment, **_: object) -> None:
    """Initialize the Lambda client and sample recorder for a test process.

    Args:
        environment: Active Locust environment.
        **_: Additional event arguments supplied by Locust.
    """

    global RUNTIME

    if isinstance(environment.runner, MasterRunner):
        return

    options = environment.parsed_options
    if not isinstance(options, Namespace):
        raise RuntimeError("Locust did not provide parsed benchmark options.")

    settings = create_settings(options)
    fixture = load_fixture(settings.fixture_path)
    recorder = SampleRecorder(settings.results_directory, settings.run_id)
    client = LambdaClient(environment, settings, fixture, recorder)
    RUNTIME = BenchmarkRuntime(client=client, recorder=recorder)


@events.test_stop.add_listener
def stop_benchmark(environment: Environment, **_: object) -> None:
    """Flush and close the process-local sample recorder.

    Args:
        environment: Active Locust environment.
        **_: Additional event arguments supplied by Locust.
    """

    global RUNTIME

    if isinstance(environment.runner, MasterRunner) or RUNTIME is None:
        return

    RUNTIME.recorder.close()
    RUNTIME = None


class LambdaUser(User):
    """A simulated caller that continuously invokes the selected fixture."""

    wait_time = constant(0)

    @task
    def invoke(self) -> None:
        """Invoke the configured Lambda alias once."""

        if RUNTIME is None:
            raise RuntimeError("Benchmark runtime has not been initialized.")

        RUNTIME.client.invoke()
