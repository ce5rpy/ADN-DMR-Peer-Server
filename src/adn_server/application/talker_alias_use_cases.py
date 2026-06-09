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
    buffer_from_blocks,
    buffer_from_wire_blocks,
    build_dmra_packet,
    build_dmra_packets,
    decode_ta_from_blocks,
    is_ta_header_byte,
    parse_ta_text_formats,
    required_ta_block_count,
    talker_alias_decode_complete,
    truncate_talker_alias,
)
from .ports import TalkerAliasEmblcEncoder

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
    tfmt = sys_cfg.get("TALKER_ALIAS_TEXT_FORMAT")
    if tfmt is None:
        tfmt = global_cfg.get("TALKER_ALIAS_TEXT_FORMAT", "utf8")
    return {
        "enabled": bool(enabled),
        "mode": mode,
        "format": str(fmt),
        "text_formats": parse_ta_text_formats(tfmt),
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


def _passthrough_buf_ready(blocks: dict[int, bytes], buf: bytes) -> bool:
    need = required_ta_block_count(buf)
    if need < 1 or need > DMRA_BLOCK_COUNT:
        return False
    if not all(i in blocks and len(blocks[i]) >= DMRA_PAYLOAD_LEN for i in range(need)):
        return False
    return talker_alias_decode_complete(buf)


def passthrough_complete(blocks: dict[int, bytes]) -> bool:
    """True when required TA blocks (1–4) are present and fully decode."""
    if not blocks:
        return False
    buf = buffer_from_wire_blocks(blocks)
    if _passthrough_buf_ready(blocks, buf):
        return True
    if blocks.get(0) and is_ta_header_byte(blocks[0][0]):
        return _passthrough_buf_ready(blocks, buffer_from_blocks(blocks))
    return False


def passthrough_packets_from_blocks(rf_src: bytes, blocks: dict[int, bytes]) -> list[bytes]:
    """Rebuild DMRA packets from buffered wire payloads (only blocks needed for TA)."""
    if passthrough_complete(blocks):
        buf = buffer_from_wire_blocks(blocks)
        if not talker_alias_decode_complete(buf) and blocks.get(0) and is_ta_header_byte(blocks[0][0]):
            buf = buffer_from_blocks(blocks)
        count = required_ta_block_count(buf)
        return [
            build_dmra_packet(rf_src, block_id, blocks[block_id])
            for block_id in range(count)
            if block_id in blocks
        ]
    return []


class TalkerAliasUseCases:
    """Orchestrate inject / passthrough for bridge forwarding."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        ta_emblc_encoder: TalkerAliasEmblcEncoder,
    ) -> None:
        self._config = config
        self._ta_emblc = ta_emblc_encoder
        self._sent_streams: set[tuple[str, bytes]] = set()
        self._embed_logged: set[tuple[str, bytes]] = set()

    def clear_stream(self, system_name: str, stream_id: bytes) -> None:
        self._sent_streams.discard((system_name, stream_id))
        self._embed_logged.discard((system_name, stream_id))

    def should_send_on_vhead(self, target_system: str, stream_id: bytes) -> bool:
        return (target_system, stream_id) not in self._sent_streams

    def mark_dmra_sent(self, target_system: str, stream_id: bytes) -> None:
        self._sent_streams.add((target_system, stream_id))

    def packets_for_stream(
        self,
        source_system: str,
        rf_src: bytes,
        stream_id: bytes,
        get_passthrough_blocks: Any,
        *,
        target_system: str | None = None,
        fallback_inject: bool = False,
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
            text = decode_ta_from_blocks(blocks)
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
            return build_dmra_packets(rf_src, text, settings["text_formats"][0])
        # both: prefer the source's own TA. If a valid MMDVM DMRA buffer arrived,
        # relay it. Otherwise the source's embedded LC (e.g. MMDVM voice) is passed
        # through unchanged in the DMRD voice, so do NOT inject a template here.
        if have_passthrough:
            text = decode_ta_from_blocks(blocks)
            logger.debug(
                "(%s) *TALKER ALIAS* passthrough '%s' via %s -> %s stream %s",
                source_system, text, via, target, int_id(stream_id),
            )
            return passthrough_packets_from_blocks(rf_src, blocks)
        # Legacy resolve_ta (both): inject template when no DMRA buffer yet (VHEAD).
        text = format_talker_alias_text(self._config, rf_src)
        suffix = " (no source TA yet)" if fallback_inject else ""
        logger.debug(
            "(%s) *TALKER ALIAS* inject '%s'%s via %s -> %s stream %s",
            source_system, text, suffix, via, target, int_id(stream_id),
        )
        return build_dmra_packets(rf_src, text, settings["text_formats"][0])

    def embedded_emblc_for_stream(
        self,
        source_system: str,
        rf_src: bytes,
        stream_id: bytes,
        get_passthrough_blocks: Any,
        *,
        target_system: str | None = None,
        fallback_inject: bool = False,
    ) -> tuple[list[dict[int, Any]], int] | None:
        """Return (encode_emblc dicts, block count 1–4) for the embedded TA to overlay, or None.

        The group LC is rewritten separately for the destination TG; this only supplies the
        Talker Alias overlaid on alternate superframes:

        - **passthrough / both with source TA:** re-encode the source's decoded TA blocks
          (round-trips losslessly via the fixed ``encode_emblc``).
        - **inject / both fallback:** the configured template.
        - otherwise (no TA available yet): ``None`` — only the destination group LC is sent.
        """
        settings = talker_alias_settings(self._config, source_system)
        if not settings["enabled"]:
            return None
        mode = settings["mode"]
        target = target_system or source_system
        via = "repeat" if source_system == target else "bridge"
        log_key = (source_system, stream_id)

        def _log(text: str, suffix: str) -> None:
            if log_key in self._embed_logged:
                return
            self._embed_logged.add(log_key)
            logger.debug(
                "(%s) *TALKER ALIAS* embed inject '%s'%s via %s -> %s stream %s",
                source_system, text, suffix, via, target, int_id(stream_id),
            )

        blocks = get_passthrough_blocks(source_system, stream_id) if get_passthrough_blocks else None
        if mode in ("passthrough", "both") and blocks and passthrough_complete(blocks):
            _log(decode_ta_from_blocks(blocks), " (source TA)")
            return self._ta_emblc.encode_blocks(blocks)
        if mode in ("inject", "both") or fallback_inject:
            suffix = "" if mode == "inject" else " (no source TA yet)"
            text = format_talker_alias_text(self._config, rf_src)
            _log(text, suffix)
            return self._ta_emblc.encode_text(text, text_formats=settings["text_formats"])
        return None
