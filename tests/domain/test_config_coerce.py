# ADN DMR Peer Server - tests domain config coerce
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

from __future__ import annotations

from adn_server.application.report.payloads import resolve_peer_single_and_timer
from adn_server.domain.config_coerce import coerce_bool, parse_options_single


def test_coerce_bool_accepts_common_string_forms() -> None:
    assert coerce_bool(True) is True
    assert coerce_bool(False) is False
    assert coerce_bool("true") is True
    assert coerce_bool("True") is True
    assert coerce_bool("TRUE") is True
    assert coerce_bool("false") is False
    assert coerce_bool("False") is False
    assert coerce_bool("0") is False
    assert coerce_bool("1") is True


def test_parse_options_single_accepts_true_false_and_digits() -> None:
    assert parse_options_single("0") is False
    assert parse_options_single("1") is True
    assert parse_options_single("true") is True
    assert parse_options_single("True") is True
    assert parse_options_single("false") is False


def test_resolve_peer_single_uses_yaml_when_options_omit_single() -> None:
    yaml_cfg = {"SINGLE_MODE": "false", "DEFAULT_UA_TIMER": 15}
    single, timer = resolve_peer_single_and_timer({"TS2_STATIC": "730444"}, yaml_cfg)
    assert single is False
    assert timer == 15.0


def test_resolve_peer_single_true_string_not_only_digit_one() -> None:
    yaml_cfg = {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 10}
    single, _ = resolve_peer_single_and_timer({"SINGLE": "true"}, yaml_cfg)
    assert single is True
