"""Tests for benchmark fixture loading."""

from pathlib import Path

import pytest

from laymbda_benchmark.config import load_fixture


def test_load_fixture_serializes_a_laya_request(tmp_path: Path) -> None:
    """Load valid Laya input as compact UTF-8 JSON."""

    path = tmp_path / "fixture.json"
    path.write_text(
        '{"state":"hello","questions":{"q":{"type":"noul",'
        '"instructions":"Is this a greeting?"}}}',
        encoding="utf-8",
    )

    fixture = load_fixture(path)

    assert fixture.name == "fixture"
    assert fixture.payload.startswith(b'{"state":"hello"')


def test_load_fixture_rejects_unrelated_json(tmp_path: Path) -> None:
    """Reject JSON objects that do not contain Laya input fields."""

    path = tmp_path / "fixture.json"
    path.write_text('{"message":"hello"}', encoding="utf-8")

    with pytest.raises(ValueError, match="not a Laya request"):
        load_fixture(path)
