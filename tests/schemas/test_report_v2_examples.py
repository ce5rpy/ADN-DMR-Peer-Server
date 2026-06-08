"""Validate report v2 JSON Schema against committed examples (V2-P1-001)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "report-v2.json"
_EXAMPLES_DIR = _SCHEMA_PATH.parent / "examples"


@pytest.fixture(scope="module")
def report_v2_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def validator(report_v2_schema: dict) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(report_v2_schema)


@pytest.mark.parametrize("path", sorted(_EXAMPLES_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_example_validates(path: Path, validator: jsonschema.Draft202012Validator) -> None:
    with path.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    validator.validate(doc)
