# ADN DMR Peer Server - TTS to AMBE stub
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""TTS to AMBE file (legacy tts_engine.ensure_tts_ambe). Stub until ported."""

from __future__ import annotations

from typing import Any


def ensure_tts_ambe(text: str, lang: str, out_path: str, config: dict[str, Any]) -> str | None:
    """
    Generate TTS audio and convert to AMBE file; return output path or None.
    Legacy: tts_engine.ensure_tts_ambe. Full implementation to be ported when needed.
    """
    return None
