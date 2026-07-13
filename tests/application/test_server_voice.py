# ADN DMR Peer Server - tests application server voice identity
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

"""Server voice DMR_ID config (global default and per-announcement override)."""

from __future__ import annotations

from adn_server.application.server_voice import (
    DEFAULT_SERVER_VOICE_ID,
    all_server_voice_ids,
    announcement_item_dmr_id,
    announcement_item_source_bytes,
    server_voice_dmr_id,
    server_voice_id,
    server_voice_rf_src_bytes,
)
from adn_server.domain import bytes_3, int_id


def test_server_voice_defaults_when_voice_section_missing() -> None:
    assert server_voice_dmr_id({}) == DEFAULT_SERVER_VOICE_ID
    assert server_voice_id({}) == DEFAULT_SERVER_VOICE_ID
    assert int_id(server_voice_rf_src_bytes({})) == DEFAULT_SERVER_VOICE_ID


def test_server_voice_reads_dmr_id_from_config() -> None:
    config = {"VOICE": {"DMR_ID": 3109898}}
    assert server_voice_dmr_id(config) == 3109898
    assert server_voice_rf_src_bytes(config) == bytes_3(3109898)


def test_server_voice_legacy_keys_still_work() -> None:
    assert server_voice_dmr_id({"VOICE": {"SRC_ID": 2000002}}) == 2000002
    assert server_voice_dmr_id({"VOICE": {"ID": 3000003}}) == 3000003


def test_server_voice_invalid_dmr_id_falls_back_to_default() -> None:
    config = {"VOICE": {"DMR_ID": "not-a-number"}}
    assert server_voice_dmr_id(config) == DEFAULT_SERVER_VOICE_ID


def test_announcement_item_dmr_id_override() -> None:
    config = {"VOICE": {"DMR_ID": 1000001}}
    item = {"DMR_ID": 3109898, "TG": 2}
    assert announcement_item_dmr_id(item, config) == 3109898
    assert announcement_item_dmr_id({"TG": 2}, config) == 1000001


def test_all_server_voice_ids_collects_global_and_per_item() -> None:
    config = {
        "VOICE": {
            "DMR_ID": 1000001,
            "ANNOUNCEMENTS": [{"DMR_ID": 2000002}],
            "TTS_ANNOUNCEMENTS": [{"DMR_ID": 3000003}],
        }
    }
    assert all_server_voice_ids(config) == frozenset({1000001, 2000002, 3000003, 5000})


def test_legacy_voice_yaml_without_dmr_id_uses_defaults() -> None:
    """Pre-migration adn-voice.yaml (no DMR_ID keys) keeps working."""
    legacy = {
        "VOICE": {
            "ANNOUNCEMENTS": [
                {"ENABLED": True, "TG": 91, "FILE": "welcome", "LANGUAGE": "en_GB", "MODE": "interval", "INTERVAL": 60},
            ],
            "TTS_ANNOUNCEMENTS": [
                {"ENABLED": True, "TG": 92, "FILE": "texto1", "LANGUAGE": "es_ES", "MODE": "interval", "INTERVAL": 60},
            ],
        }
    }
    ann = legacy["VOICE"]["ANNOUNCEMENTS"][0]
    tts = legacy["VOICE"]["TTS_ANNOUNCEMENTS"][0]
    assert server_voice_dmr_id(legacy) == DEFAULT_SERVER_VOICE_ID
    assert announcement_item_dmr_id(ann, legacy) == DEFAULT_SERVER_VOICE_ID
    assert announcement_item_dmr_id(tts, legacy) == DEFAULT_SERVER_VOICE_ID
    assert int_id(announcement_item_source_bytes(ann, legacy)) == DEFAULT_SERVER_VOICE_ID


def test_legacy_voice_yaml_missing_voice_section_uses_defaults() -> None:
    assert server_voice_dmr_id({}) == DEFAULT_SERVER_VOICE_ID
    assert announcement_item_dmr_id(None, {}) == DEFAULT_SERVER_VOICE_ID


def test_invalid_item_dmr_id_falls_back_without_error() -> None:
    config = {"VOICE": {"DMR_ID": "bad"}}
    item = {"DMR_ID": [], "TG": 2}
    assert announcement_item_dmr_id(item, config) == DEFAULT_SERVER_VOICE_ID
