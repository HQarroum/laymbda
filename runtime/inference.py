"""Own the Laya model lifecycle and run predictions."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

import laya
import torch
from protocol import InferenceRequest, LayaState

# Local model directory baked into the container image.
MODEL_PATH = os.environ.get("LAYA_MODEL_PATH", "/opt/laya-model")

# CPU workers assigned to PyTorch by the CDK stack.
TORCH_THREADS = int(os.environ.get("TORCH_THREADS", "4"))

# Small domain-neutral request used to initialize model execution before snapshotting.
WARMUP_REQUEST = InferenceRequest.model_validate(
    {
        "state": "The model is ready.",
        "questions": {
            "ready": {
                "type": "noul",
                "instructions": "Is the model ready?",
            }
        },
    }
)


class LayaAgent(Protocol):
    """The portion of Laya's agent API used by this runtime."""

    def predict(
        self,
        state: LayaState,
        questions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Evaluate typed questions over a state.

        Args:
            state: Text or JSON-compatible state to evaluate.
            questions: Laya question definitions keyed by question ID.

        Returns:
            Laya's model result, including answers and token usage.
        """


class LayaInference:
    """Keep one initialized Laya agent available across invocations."""

    def __init__(self, model_path: str, torch_threads: int) -> None:
        """Initialize the CPU runtime and load the baked Laya model.

        Args:
            model_path: Local directory containing the model checkpoint.
            torch_threads: Number of CPU threads available to PyTorch.
        """

        self._configure_torch(torch_threads)
        self._agent: LayaAgent = laya.load(model_path, device="cpu")
        self._warm_up()

    def predict(
        self,
        request: InferenceRequest,
    ) -> tuple[dict[str, Any], float]:
        """Run a validated request through the initialized Laya agent.

        Args:
            request: Validated state and typed questions to evaluate.

        Returns:
            A pair containing Laya's result and elapsed inference time in
            milliseconds.

        Raises:
            ValueError: If Laya cannot represent the supplied question options
                within the model's configured token budget.
        """

        state, questions = request.as_laya_input()
        started_at = time.perf_counter()
        result = self._agent.predict(state, questions)
        duration_ms = (time.perf_counter() - started_at) * 1_000
        return result, duration_ms

    @staticmethod
    def _configure_torch(torch_threads: int) -> None:
        """Configure PyTorch's CPU thread pools before model initialization.

        Args:
            torch_threads: Number of threads assigned to intra-operation work.
        """

        torch.set_num_threads(torch_threads)
        torch.set_num_interop_threads(1)

    def _warm_up(self) -> None:
        """Prime model execution before Lambda captures the SnapStart snapshot.

        The warm-up result is discarded; only the initialized execution state
        is retained for future restores.
        """

        state, questions = WARMUP_REQUEST.as_laya_input()
        self._agent.predict(state, questions)


# Model instance retained across warm invocations and SnapStart restores.
INFERENCE = LayaInference(MODEL_PATH, TORCH_THREADS)
