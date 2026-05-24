# ADN DMR Peer Server - Talker Alias use cases
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Talker Alias policy: template formatting, inject vs passthrough."""

from __future__ import annotations

import logging
from typing import Any

from ..domain import int_id
from ..domain.talker_alias import (
    DMRA_BLOCK_COUNT,
    DMRA_PAYLOAD_LEN,
    build_dmra_packet,
    build_dmra_packets,
    buffer_from_blocks,
    decode_7bit,
    encode_talker_alias_emblc,
    encode_talker_alias_emblc_from_blocks,
    truncate_talker_alias,
)

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({"inject", "passthrough", "both"})


def talker_alias_settings(config: dict[str, Any], system_name: str | None = None) -> dict[str, Any]:
    """Effective Talker Alias settings (GLOBAL with optional per-system override)."""
    global_cfg = config.get("GLOBAL", {})
    sys_cfg = config.get("SYSTEMS", {}).get(system_name or "", {}) if system_name else {}
    enabled = sys_cfg.get("TALKER_ALIAS")
    if enabled is None:
        enabled = global_cfg.get("TALKER_ALIAS", False)
    mode = sys_cfg.get("TALKER_ALIAS_MODE")
    if mode is None:
        mode = global_cfg.get("TALKER_ALIAS_MODE", "both")
    if mode not in VALID_MODES:
        mode = "both"
    fmt = sys_cfg.get("TALKER_ALIAS_FORMAT")
    if fmt is None:
        fmt = global_cfg.get("TALKER_ALIAS_FORMAT", "{callsign} {fname}")
    return {
        "enabled": bool(enabled),
        "mode": mode,
        "format": str(fmt),
    }


def format_talker_alias_text(config: dict[str, Any], rf_src: bytes) -> str:
    """Build display string from subscriber profile + template."""
    settings = talker_alias_settings(config)
    template = settings["format"]
    rid = int_id(rf_src)
    profiles = config.get("_SUB_PROFILES", {})
    profile = profiles.get(rid, {})
    sub_ids = config.get("_SUB_IDS", {})
    callsign = profile.get("callsign") or sub_ids.get(rid) or ""
    fname = profile.get("fname") or ""
    surname = profile.get("surname") or ""
    if profile.get("talker_alias"):
        text = str(profile["talker_alias"])
    else:
        try:
            text = template.format(
                callsign=callsign,
                fname=fname,
                surname=surname,
                id=rid,
            )
        except (KeyError, ValueError):
            text = callsign or f"DMR ID:{rid}"
    text = " ".join(text.split())
    if not text.strip():
        text = callsign or f"DMR ID:{rid}"
    return truncate_talker_alias(text)


def passthrough_complete(blocks: dict[int, bytes]) -> bool:
    """True when all four TA blocks were received."""
    return all(i in blocks and len(blocks[i]) >= DMRA_PAYLOAD_LEN for i in range(DMRA_BLOCK_COUNT))


def passthrough_packets_from_blocks(rf_src: bytes, blocks: dict[int, bytes]) -> list[bytes]:
    """Rebuild four DMRA packets from buffered block payloads."""
    packets: list[bytes] = []
    for block_id in range(DMRA_BLOCK_COUNT):
        payload = blocks.get(block_id, b"\x00" * DMRA_PAYLOAD_LEN)
        packets.append(build_dmra_packet(rf_src, block_id, payload))
    return packets


class TalkerAliasUseCases:
    """Orchestrate inject / passthrough for bridge forwarding."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._sent_streams: set[tuple[str, bytes]] = set()
        self._embed_logged: set[tuple[str, bytes]] = set()

    def clear_stream(self, system_name: str, stream_id: bytes) -> None:
        self._sent_streams.discard((system_name, stream_id))
        self._embed_logged.discard((system_name, stream_id))

    def should_send_on_vhead(self, target_system: str, stream_id: bytes) -> bool:
        key = (target_system, stream_id)
        if key in self._sent_streams:
            return False
        self._sent_streams.add(key)
        return True

    def packets_for_stream(
        self,
        source_system: str,
        rf_src: bytes,
        stream_id: bytes,
        get_passthrough_blocks: Any,
        *,
        target_system: str | None = None,
    ) -> list[bytes] | None:
        """Return DMRA packets to send on VHEAD, or None if TA disabled / nothing to send."""
        settings = talker_alias_settings(self._config, source_system)
        if not settings["enabled"]:
            return None
        target = target_system or source_system
        via = "repeat" if source_system == target else "bridge"
        mode = settings["mode"]
        blocks = get_passthrough_blocks(source_system, stream_id) if get_passthrough_blocks else None
        have_passthrough = bool(blocks and passthrough_complete(blocks))
        if mode == "passthrough":
            if not have_passthrough:
                return None
            text = decode_7bit(buffer_from_blocks(blocks))
            logger.debug(
                "(%s) *TALKER ALIAS* passthrough '%s' via %s -> %s stream %s",
                source_system, text, via, target, int_id(stream_id),
            )
            return passthrough_packets_from_blocks(rf_src, blocks)
        if mode == "inject":
            text = format_talker_alias_text(self._config, rf_src)
            logger.debug(
                "(%s) *TALKER ALIAS* inject '%s' via %s -> %s stream %s",
                source_system, text, via, target, int_id(stream_id),
            )
            return build_dmra_packets(rf_src, text)
        # both
        if have_passthrough:
            text = decode_7bit(buffer_from_blocks(blocks))
            logger.debug(
                "(%s) *TALKER ALIAS* passthrough '%s' via %s -> %s stream %s",
                source_system, text, via, target, int_id(stream_id),
            )
            return passthrough_packets_from_blocks(rf_src, blocks)
        text = format_talker_alias_text(self._config, rf_src)
        logger.debug(
            "(%s) *TALKER ALIAS* inject '%s' via %s -> %s stream %s",
            source_system, text, via, target, int_id(stream_id),
        )
        return build_dmra_packets(rf_src, text)

    def embedded_emblc_for_stream(
        self,
        source_system: str,
        rf_src: bytes,
        stream_id: bytes,
        get_passthrough_blocks: Any,
        *,
        target_system: str | None = None,
    ) -> tuple[list[dict[int, Any]], int] | None:
        """Return (encode_emblc dicts, block count 1–4) for embedded TA in DMRD, or None."""
        settings = talker_alias_settings(self._config, source_system)
        if not settings["enabled"]:
            return None
        target = target_system or source_system
        via = "repeat" if source_system == target else "bridge"
        mode = settings["mode"]
        log_key = (source_system, stream_id)
        log_embed = log_key not in self._embed_logged

        def _log_embed(text: str, passthrough: bool) -> None:
            if not log_embed:
                return
            self._embed_logged.add(log_key)
            kind = "passthrough" if passthrough else "inject"
            logger.debug(
                "(%s) *TALKER ALIAS* embed %s '%s' via %s -> %s stream %s",
                source_system, kind, text, via, target, int_id(stream_id),
            )

        blocks = get_passthrough_blocks(source_system, stream_id) if get_passthrough_blocks else None
        have_passthrough = bool(blocks and passthrough_complete(blocks))
        if mode == "passthrough":
            if not have_passthrough:
                return None
            text = decode_7bit(buffer_from_blocks(blocks))
            _log_embed(text, True)
            return encode_talker_alias_emblc_from_blocks(blocks)
        if mode == "inject":
            text = format_talker_alias_text(self._config, rf_src)
            _log_embed(text, False)
            return encode_talker_alias_emblc(text)
        if have_passthrough:
            text = decode_7bit(buffer_from_blocks(blocks))
            _log_embed(text, True)
            return encode_talker_alias_emblc_from_blocks(blocks)
        text = format_talker_alias_text(self._config, rf_src)
        _log_embed(text, False)
        return encode_talker_alias_emblc(text)
