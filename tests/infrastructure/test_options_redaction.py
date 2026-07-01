# ADN DMR Peer Server - tests infrastructure options redaction
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License,
#   or (at your option) any later version.
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

"""Redaction of PASS= secret in the OPTIONS log line."""

from __future__ import annotations

from adn_server.infrastructure.options_redaction import redact_pass_in_options


def test_redact_pass_masks_secret() -> None:
    assert redact_pass_in_options(b"TS2=730;PASS=secret123;SINGLE=1;") == (
        "TS2=730;PASS=*******;SINGLE=1;"
    )


def test_redact_pass_case_insensitive() -> None:
    assert redact_pass_in_options(b"pass=hunter2;TS1=730;") == "pass=*******;TS1=730;"


def test_redact_pass_no_pass_returns_as_is() -> None:
    assert redact_pass_in_options(b"TS2=730;SINGLE=1;") == "TS2=730;SINGLE=1;"


def test_redact_pass_accepts_str() -> None:
    assert redact_pass_in_options("TS2=730;PASS=pw;") == "TS2=730;PASS=*******;"


def test_redact_pass_none_returns_empty() -> None:
    assert redact_pass_in_options(None) == ""
