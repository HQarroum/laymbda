"""Persist raw invocation samples without altering timed requests."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import TextIO

from laymbda_benchmark.models import InvocationSample


class SampleRecorder:
    """Write one JSON object per invocation to a process-local file."""

    def __init__(self, results_directory: Path, run_id: str) -> None:
        """Open the raw sample file for one Locust process.

        Args:
            results_directory: Directory receiving benchmark artifacts.
            run_id: Stable identifier shared by files from the same run.
        """

        results_directory.mkdir(parents=True, exist_ok=True)
        self.path = results_directory / f"{run_id}-samples-{os.getpid()}.jsonl"
        self._file: TextIO = self.path.open("a", encoding="utf-8")
        self._lock = Lock()

    def record(self, sample: InvocationSample) -> None:
        """Append one invocation sample to the result stream.

        Args:
            sample: Completed client-side invocation observation.
        """

        with self._lock:
            self._file.write(f"{sample.to_json()}\n")

    def close(self) -> None:
        """Flush pending samples and close the result stream."""

        with self._lock:
            if self._file.closed:
                return
            self._file.flush()
            self._file.close()
