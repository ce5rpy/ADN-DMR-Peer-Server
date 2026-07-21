"""Shared OPTIONS text redaction for logging (mask ``PASS=`` secrets)."""

from __future__ import annotations

import re
from typing import Any

from adn_server.domain.hbp_protocol import normalize_fixed_width_ascii

_PASS_RE = re.compile(r"(?i)(PASS=)[^;]*")


def normalize_options_text(options: Any) -> str:
    """Decode OPTIONS and strip fixed-width NUL/space padding (e.g. ipsc2hbp RPTO)."""
    return normalize_fixed_width_ascii(options)


def redact_pass_in_options(options: Any) -> str:
    """OPTIONS text for logging with ``PASS=`` secret replaced by ``PASS=*******``."""
    text = normalize_options_text(options)
    if not text:
        return ""
    return _PASS_RE.sub(r"\1*******", text)
