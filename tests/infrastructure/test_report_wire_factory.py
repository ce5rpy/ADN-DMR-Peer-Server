"""Report wire encoder factory."""

from __future__ import annotations

from adn_server.infrastructure.twisted_adapters.report import ReportWire, create_report_wire


def test_create_report_wire_returns_encoder() -> None:
    wire = create_report_wire({"REPORTS": {}})
    assert isinstance(wire, ReportWire)
