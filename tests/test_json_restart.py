"""Verify the documented JSON example works across Python process boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "replay_json.py"


def test_json_log_replays_identically_in_a_fresh_process(tmp_path: Path) -> None:
    log = tmp_path / "expense-run.json"
    saved = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "save", str(log)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    replayed = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "replay", str(log)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    original = json.loads(saved.stdout)
    assert json.loads(replayed.stdout) == original
    assert original["status"] == "completed"
    assert original["node"] == "approved"
    assert original["context"] == {
        "amount": 500,
        "details": {"employee": "Zoë", "items": [1.5, True, None]},
        "report_id": "EXP-001",
        "vp_approved": True,
    }
    assert original["idempotency_keys"][1:] == ["submit", "manager", "route", "vp", "finish"]
    assert len(original["timestamps"]) == 6
    document = json.loads(log.read_text(encoding="utf-8"))
    assert document["format_version"] == 1
    assert document["workflow"]["version"] == "1.0.0"
    assert document["events"][0]["payload"]["context"]["amount"] == 5000


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ('{"format_version": 2}', "Unsupported JSON log format_version"),
        ('{"format_version": 1, "value": NaN}', "Non-finite number is not supported"),
    ],
)
def test_json_example_rejects_unsupported_format_and_nonfinite_numbers(
    tmp_path: Path, document: str, message: str
) -> None:
    log = tmp_path / "invalid.json"
    log.write_text(document, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "replay", str(log)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert message in result.stderr
