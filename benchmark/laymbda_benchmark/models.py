"""Shared data models for benchmark execution and reporting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

type SampleOutcome = Literal[
    "client_error",
    "function_error",
    "success",
    "throttled",
]


@dataclass(frozen=True, slots=True)
class Fixture:
    """A serialized Laya request used by every simulated caller."""

    name: str
    path: Path
    payload: bytes


@dataclass(frozen=True, slots=True)
class InvocationSample:
    """Client-side observations for one Lambda invocation."""

    started_at: str
    fixture: str
    wall_ms: float
    outcome: SampleOutcome
    request_id: str | None
    executed_version: str | None
    response_bytes: int
    error: str | None

    def to_json(self) -> str:
        """Serialize the sample as one compact JSON line.

        Returns:
            A deterministic JSON representation of the sample.
        """

        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> InvocationSample:
        """Deserialize one JSON line into an invocation sample.

        Args:
            value: JSON object previously produced by :meth:`to_json`.

        Returns:
            The parsed invocation sample.
        """

        return cls(**json.loads(value))
