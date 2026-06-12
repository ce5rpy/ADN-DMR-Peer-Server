# ADN DMR Peer Server - tests schemas report schema examples
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

"""Validate report JSON Schema against committed examples."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "report-v2.json"
_EXAMPLES_DIR = _SCHEMA_PATH.parent / "examples"


@pytest.fixture(scope="module")
def report_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def validator(report_schema: dict) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(report_schema)


@pytest.mark.parametrize("path", sorted(_EXAMPLES_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_example_validates(path: Path, validator: jsonschema.Draft202012Validator) -> None:
    with path.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    validator.validate(doc)
