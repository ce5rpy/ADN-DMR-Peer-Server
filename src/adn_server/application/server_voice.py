# ADN DMR Peer Server - server-originated voice identity
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

"""RF source ID for scheduled announcements, TTS, and server playback.

``VOICE.DMR_ID`` is optional. When absent (legacy ``adn-voice.yaml``), the
default is **1000001**. Per-item ``DMR_ID`` on announcement rows is also
optional and inherits the global default. Callsign/display name comes from the
subscriber alias DB (``_SUB_IDS`` / users file) for that DMR ID — not from voice
config. Invalid DMR_ID values are ignored and fall back to the default.
"""

from __future__ import annotations

from typing import Any

from ..domain import bytes_3

DEFAULT_SERVER_VOICE_ID = 1000001
LEGACY_SERVER_VOICE_ID = 5000


def _parse_dmr_id(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def server_voice_dmr_id(config: dict[str, Any] | None) -> int:
    """Global default RF source (``VOICE.DMR_ID``), default 1000001."""
    if not config:
        return DEFAULT_SERVER_VOICE_ID
    voice = config.get("VOICE")
    if not isinstance(voice, dict):
        return DEFAULT_SERVER_VOICE_ID
    for key in ("DMR_ID", "SRC_ID", "ID"):
        parsed = _parse_dmr_id(voice.get(key))
        if parsed is not None:
            return parsed
    return DEFAULT_SERVER_VOICE_ID


def server_voice_id(config: dict[str, Any] | None) -> int:
    """Alias for :func:`server_voice_dmr_id` (global default RF source)."""
    return server_voice_dmr_id(config)


def server_voice_src_id(config: dict[str, Any] | None) -> int:
    """Deprecated alias for :func:`server_voice_dmr_id`."""
    return server_voice_dmr_id(config)


def announcement_item_dmr_id(
    item: dict[str, Any] | None,
    config: dict[str, Any] | None,
) -> int:
    """Per-item ``DMR_ID`` override, else global ``VOICE.DMR_ID``."""
    if isinstance(item, dict):
        parsed = _parse_dmr_id(item.get("DMR_ID"))
        if parsed is not None:
            return parsed
    return server_voice_dmr_id(config)


def announcement_item_source_bytes(
    item: dict[str, Any] | None,
    config: dict[str, Any] | None,
) -> bytes:
    return bytes_3(announcement_item_dmr_id(item, config))


def server_voice_rf_src_bytes(config: dict[str, Any] | None) -> bytes:
    return bytes_3(server_voice_dmr_id(config))


def all_server_voice_ids(config: dict[str, Any] | None) -> frozenset[int]:
    """All RF source IDs used by server voice (global, per-item, legacy)."""
    ids = {server_voice_dmr_id(config), LEGACY_SERVER_VOICE_ID}
    if not config:
        return frozenset(ids)
    voice = config.get("VOICE")
    if not isinstance(voice, dict):
        return frozenset(ids)
    for key in ("ANNOUNCEMENTS", "TTS_ANNOUNCEMENTS"):
        for entry in voice.get(key) or []:
            if isinstance(entry, dict):
                parsed = _parse_dmr_id(entry.get("DMR_ID"))
                if parsed is not None:
                    ids.add(parsed)
    return frozenset(ids)


def is_server_voice_rf_src(rf_src: int, config: dict[str, Any] | None) -> bool:
    return int(rf_src) in all_server_voice_ids(config)
