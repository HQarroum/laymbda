"""Download the immutable English Laya checkpoint during the image build."""

from __future__ import annotations

import os

from huggingface_hub import snapshot_download

# Destination baked into the final Lambda container image.
MODEL_PATH = "/opt/laya-model"

# Files required by the English checkpoint at the repository root.
MODEL_FILES = (
    "encoder/*",
    "model.safetensors",
    "rl_agent_config.json",
    "tokenizer/*",
)


def get_required_environment(name: str) -> str:
    """Read a required environment variable used during the image build.

    Args:
        name: Name of the environment variable to read.

    Returns:
        The configured non-empty value.

    Raises:
        RuntimeError: If the environment variable is missing or empty.
    """

    value = os.environ.get(name)

    if not value:
        raise RuntimeError(f"{name} must be set during the container build.")

    return value


def main() -> None:
    """Download the pinned files required by the English Laya checkpoint.

    The checkpoint is written to the model directory copied into the final
    Lambda container image.
    """

    snapshot_download(
        repo_id=get_required_environment("LAYA_MODEL_ID"),
        revision=get_required_environment("LAYA_MODEL_REVISION"),
        local_dir=MODEL_PATH,
        allow_patterns=MODEL_FILES,
    )


if __name__ == "__main__":
    main()
