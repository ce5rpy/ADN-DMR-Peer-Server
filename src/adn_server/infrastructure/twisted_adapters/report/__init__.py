"""Report wire encoder (infrastructure).

Layering:
  application/report/payloads.py  — JSON dicts from SYSTEMS/BRIDGES/CSV
  application/ports.ReportWireEncoder — outbound port
  wire.py — sole implementation
"""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import ReportWireEncoder

from .opcodes import REPORT_OPCODES
from .wire import ReportWire

__all__ = [
    "REPORT_OPCODES",
    "ReportWire",
    "create_report_wire",
]


def create_report_wire(config: dict[str, Any]) -> ReportWireEncoder:
    """Return the report wire encoder (``config`` reserved for future options)."""
    del config
    return ReportWire()
