# ADN DMR Peer Server - tests support hbp repeat stack
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

"""HBP MASTER + RoutingUseCases stack for REPEAT / talker-alias integration tests."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from adn_server.application.routing_use_cases import RoutingUseCases
from adn_server.application.reporting_use_cases import ReportingUseCases
from adn_server.domain.dmr.bptc import encode_emblc
from adn_server.infrastructure.acl_router import InMemoryAclRouter
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from adn_server.infrastructure.config_normalizer import (
    apply_talker_alias_defaults,
    ensure_system_runtime_config,
)
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol

from tests.harness.deterministic import FakeReportFactory, FakeReportSender, PacketSpec
from tests.harness.scenarios import talker_alias_config


class RecordingTransport:
    """Capture MASTER downlink UDP writes (REPEAT and DMRA)."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def for_addr(self, addr: tuple[str, int]) -> list[bytes]:
        return [pkt for pkt, target in self.sent if target == addr]

    def clear(self) -> None:
        self.sent.clear()


class _AclRouter:
    def acl_check(self, _value: bytes, _acl: object) -> bool:
        return True


@dataclass
class HbpRepeatStack:
    system_name: str
    config: dict[str, Any]
    hbp: HBPProtocol
    bridge: RoutingUseCases
    transport: RecordingTransport
    report_factory: FakeReportFactory
    dmra_capture: list[tuple[list[bytes], bytes | None]] = field(default_factory=list)

    def register_peer(
        self,
        peer_id: bytes,
        sockaddr: tuple[str, int],
        *,
        options: str | bytes | None = None,
        simplex: bool | None = None,
    ) -> None:
        peer: dict[str, Any] = {
            "CONNECTION": "YES",
            "CONNECTED": 1_700_000_000.0,
            "LAST_PING": 1_700_000_000.0,
            "SOCKADDR": sockaddr,
            "CALLSIGN": b"CE5RPY  ",
            "RADIO_ID": str(int.from_bytes(peer_id, "big")),
        }
        if simplex is True:
            peer["SLOTS"] = b"4"
            peer["RX_FREQ"] = b"145500000"
            peer["TX_FREQ"] = b"145500000"
        elif simplex is False:
            peer["SLOTS"] = b"3"
            peer["RX_FREQ"] = b"145625000"
            peer["TX_FREQ"] = b"145125000"
        if options is not None:
            peer["OPTIONS"] = options.encode("utf-8") if isinstance(options, str) else options
        from adn_server.application.routing.helpers import apply_peer_rf_mode

        apply_peer_rf_mode(peer)
        self.hbp._peers[peer_id] = peer
        self.config["SYSTEMS"][self.system_name].setdefault("PEERS", {})[peer_id] = (
            self.hbp._peers[peer_id]
        )
        self.hbp._refresh_connected_peer_count()
        self.hbp._mark_downlink_index_dirty()

    def inject(self, packet: bytes, sockaddr: tuple[str, int]) -> None:
        self.hbp.datagramReceived(packet, sockaddr)

    def inject_spec(self, spec: PacketSpec, sockaddr: tuple[str, int]) -> None:
        self.inject(spec.data(), sockaddr)


def build_hbp_repeat_stack(
    *,
    talker_alias: bool = True,
    system_name: str = "MASTER-A",
) -> HbpRepeatStack:
    """Real HBPProtocol with RoutingUseCases TA callbacks (not FakeHbpProtocol)."""
    config = copy.deepcopy(talker_alias_config())
    if not talker_alias:
        config["GLOBAL"]["TALKER_ALIAS"] = False
    apply_talker_alias_defaults(config)
    ensure_system_runtime_config(config)
    sys_cfg = config["SYSTEMS"][system_name]
    sys_cfg["REPEAT"] = True
    sys_cfg["MAX_PEERS"] = 8
    sys_cfg["USE_ACL"] = False

    transport = RecordingTransport()
    report_factory = FakeReportFactory()
    hbp = HBPProtocol(system_name, config, report_factory=report_factory, router=_AclRouter())
    hbp.transport = transport  # type: ignore[assignment]

    protocols: dict[str, Any] = {system_name: hbp}
    dmra_capture: list[tuple[list[bytes], bytes | None]] = []

    def _send_dmra(
        target_system: str,
        packets: list[bytes],
        exclude_peer: bytes | None = None,
        *,
        slot: int | None = None,
        tgid: int | None = None,
    ) -> int:
        proto = protocols[target_system]
        dmra_capture.append((list(packets), exclude_peer))
        return proto.send_dmra_to_peers(
            packets, exclude_peer=exclude_peer, slot=slot, tgid=tgid,
        )

    def _get_dmra_blocks(_system: str, stream_id: bytes) -> dict[int, bytes] | None:
        return hbp.get_dmra_blocks(stream_id)

    bridge = RoutingUseCases(
        InMemoryAclRouter(),
        config,
        InMemorySubscriptionStore(),
        send_to_system=lambda *_a, **_k: None,
        get_protocols=lambda: protocols,
        reporting=ReportingUseCases(FakeReportSender(report_factory), config),
        send_dmra_to_system=_send_dmra,
        get_dmra_blocks=_get_dmra_blocks,
        encode_emblc=encode_emblc,
        ta_emblc_encoder=default_ta_emblc_encoder,
    )
    hbp._dmrd_received = bridge.dmrd_received
    hbp._on_talker_alias_repeat_prepare = bridge.prepare_talker_alias_local_repeat
    hbp._on_talker_alias_repeat_burst = bridge.rewrite_repeat_voice_burst
    hbp._on_talker_alias_stream_end = bridge.clear_talker_alias_stream

    return HbpRepeatStack(
        system_name=system_name,
        config=config,
        hbp=hbp,
        bridge=bridge,
        transport=transport,
        report_factory=report_factory,
        dmra_capture=dmra_capture,
    )
