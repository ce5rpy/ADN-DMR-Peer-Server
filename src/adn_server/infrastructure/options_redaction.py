"""Shared OPTIONS text redaction for logging (mask ``PASS=`` secrets)."""

from __future__ import annotations

import re
from typing import Any

_PASS_RE = re.compile(r"(?i)(PASS=)[^;]*")


def redact_pass_in_options(options: Any) -> str:
    """OPTIONS text for logging with ``PASS=`` secret replaced by ``PASS=*******``."""
    if options is None:
        return ""
    if isinstance(options, (bytes, bytearray)):
        text = bytes(options).decode("utf-8", errors="replace")
    else:
        text = str(options)
    return _PASS_RE.sub(r"\1*******", text)
