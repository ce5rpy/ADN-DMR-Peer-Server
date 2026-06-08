"""In-process deterministic harness for BridgeUseCases.

Inject at ``BridgeUseCases.dmrd_received()`` and capture outbound
``send_to_system`` calls without UDP or Twisted.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from adn_server.application.bridge_use_cases import BridgeUseCases
from adn_server.application.reporting_use_cases import ReportingUseCases
from adn_server.domain.dmr.bptc import encode_emblc
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder
from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import (
    HBPF_DATA_SYNC,
    HBPF_SLT_VHEAD,
    HBPF_SLT_VTERM,
    HBPF_VOICE,
)
from adn_server.infrastructure.bridge_router_impl import InMemoryBridgeRouter
from adn_server.infrastructure.hbp_constants import DMRD

ID_MAX = 16776415
PEER_MAX = 4294967295


def acl_permit_all(max_id: int = ID_MAX) -> tuple[bool, list[tuple[int, int]]]:
    return True, [(1, max_id)]


def hbp_bits(slot: int, call_type: str, frame_type: int, dtype_vseq: int) -> int:
    bits = ((frame_type & 0x3) << 4) | (dtype_vseq & 0xF)
    if slot == 2:
        bits |= 0x80
    if call_type == "unit":
        bits |= 0x40
    return bits


def parse_dmr_fields(packet: bytes) -> dict[str, Any]:
    if len(packet) < 20 or packet[:4] != DMRD:
        return {"raw": packet}

    bits = packet[15]
    if bits & 0x40:
        call_type = "unit"
    elif (bits & 0x23) == 0x23:
        call_type = "vcsbk"
    else:
        call_type = "group"

    return {
        "opcode": packet[:4],
        "seq": packet[4],
        "rf_src": packet[5:8],
        "dst_id": packet[8:11],
        "peer_id": packet[11:15],
        "bits": bits,
        "slot": 2 if bits & 0x80 else 1,
        "call_type": call_type,
        "frame_type": (bits & 0x30) >> 4,
        "dtype_vseq": bits & 0xF,
        "stream_id": packet[16:20],
        "dmr_payload": packet[20:53] if len(packet) >= 53 else b"",
        "ber": packet[53:54] if len(packet) >= 54 else b"",
        "rssi": packet[54:55] if len(packet) >= 55 else b"",
    }


@dataclass(frozen=True)
class PacketSpec:
    peer_id: int | bytes = 1001
    rf_src: int | bytes = 3120001
    dst_id: int | bytes = 91
    slot: int = 2
    stream_id: int | bytes = 0x01020304
    seq: int = 0
    call_type: str = "group"
    frame_type: int = HBPF_VOICE
    dtype_vseq: int = 0
    payload: bytes = b"\x00" * 33
    ber: bytes = b"\x00"
    rssi: bytes = b"\x00"

    def data(self) -> bytes:
        if len(self.payload) != 33:
            raise ValueError("DMR payload must be exactly 33 bytes")
        return b"".join(
            [
                DMRD,
                bytes([self.seq & 0xFF]),
                bytes_3(self.rf_src),
                bytes_3(self.dst_id),
                bytes_4(self.peer_id),
                bytes([hbp_bits(self.slot, self.call_type, self.frame_type, self.dtype_vseq)]),
                bytes_4(self.stream_id),
                self.payload,
                self.ber,
                self.rssi,
            ]
        )

    def decoded_hbp_args(self) -> dict[str, Any]:
        return {
            "peer_id": bytes_4(self.peer_id),
            "rf_src": bytes_3(self.rf_src),
            "dst_id": bytes_3(self.dst_id),
            "seq": self.seq & 0xFF,
            "slot": self.slot,
            "call_type": self.call_type,
            "frame_type": self.frame_type,
            "dtype_vseq": self.dtype_vseq,
            "stream_id": bytes_4(self.stream_id),
            "data": self.data(),
        }


@dataclass
class CapturedPacket:
    target_system: str
    packet: bytes
    hops: bytes | None = None
    ber: bytes = b"\x00"
    rssi: bytes = b"\x00"
    source_server: bytes = b"\x00\x00\x00\x00"
    source_rptr: bytes = b"\x00\x00\x00\x00"
    fields: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.fields = parse_dmr_fields(self.packet)


class PacketCapture:
    def __init__(self) -> None:
        self.packets: list[CapturedPacket] = []

    def recorder(self, target_system: str):
        def record(
            packet: bytes,
            hops: bytes | None = b"",
            ber: bytes = b"\x00",
            rssi: bytes = b"\x00",
            source_server: bytes = b"\x00\x00\x00\x00",
            source_rptr: bytes = b"\x00\x00\x00\x00",
        ) -> None:
            self.packets.append(
                CapturedPacket(
                    target_system=target_system,
                    packet=packet,
                    hops=hops,
                    ber=ber,
                    rssi=rssi,
                    source_server=source_server,
                    source_rptr=source_rptr,
                )
            )

        return record

    def for_system(self, system: str) -> list[CapturedPacket]:
        return [p for p in self.packets if p.target_system == system]


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = float(start)

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


class FakeHbpProtocol:
    """Minimal MASTER/PEER STATUS keyed by slot."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.STATUS: dict[int, dict[str, Any]] = {1: {}, 2: {}}


class FakeReportSender:
    """ReportSender port adapter for harness (events land in FakeReportFactory)."""

    def __init__(self, factory: FakeReportFactory) -> None:
        self._factory = factory

    def send_config(self, systems: dict[str, Any], *, incremental: bool = False) -> None:
        pass

    def send_bridge(self, bridges: dict[str, Any], *, incremental: bool = False) -> None:
        pass

    def send_bridge_event(self, event: str) -> None:
        self._factory.send_bridge_event(event)


class FakeReportFactory:
    """Minimal report sink so OBP VTERM sets ``_fin``."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def send_bridge_event(self, msg: str) -> None:
        self.events.append(msg)


class FakeObpProtocol:
    """Minimal OPENBRIDGE STATUS keyed by stream_id."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.STATUS: dict[bytes, dict[str, Any]] = {}


def minimal_config(system_names: tuple[str, ...] = ("MASTER-A", "MASTER-B")) -> dict[str, Any]:
    config: dict[str, Any] = {
        "GLOBAL": {
            "SERVER_ID": bytes_4(9990),
            "USE_ACL": False,
            "TG1_ACL": acl_permit_all(),
            "TG2_ACL": acl_permit_all(),
            "SUB_ACL": acl_permit_all(),
            "GEN_STAT_BRIDGES": False,
            "VALIDATE_SERVER_IDS": False,
            "TALKER_ALIAS": False,
        },
        "REPORTS": {"REPORT": False},
        "ALIASES": {"PATH": "./", "SUB_MAP_FILE": ""},
        "SYSTEMS": {},
    }
    for name in system_names:
        config["SYSTEMS"][name] = {
            "MODE": "MASTER",
            "ENABLED": True,
            "REPEAT": True,
            "MAX_PEERS": 1,
            "IP": "127.0.0.1",
            "PORT": 0,
            "PASSPHRASE": b"",
            "GROUP_HANGTIME": 0,
            "USE_ACL": False,
            "REG_ACL": acl_permit_all(PEER_MAX),
            "SUB_ACL": acl_permit_all(),
            "TG1_ACL": acl_permit_all(),
            "TG2_ACL": acl_permit_all(),
            "DEFAULT_UA_TIMER": 1,
            "SINGLE_MODE": True,
            "VOICE_IDENT": False,
            "TS1_STATIC": "",
            "TS2_STATIC": "",
            "DEFAULT_REFLECTOR": 0,
            "GENERATOR": 0,
            "ALLOW_UNREG_ID": True,
            "PEERS": {},
        }
    return config


def add_openbridge_system(
    config: dict[str, Any],
    name: str = "OBP-CL",
    *,
    enhanced: bool = False,
) -> None:
    config["SYSTEMS"][name] = {
        "MODE": "OPENBRIDGE",
        "ENABLED": True,
        "NETWORK_ID": bytes_4(1),
        "IP": "127.0.0.1",
        "PORT": 0,
        "PASSPHRASE": b"test-passphrase\x00\x00\x00\x00\x00\x00",
        "TARGET_IP": "127.0.0.1",
        "TARGET_PORT": 0,
        "TARGET_SOCK": ("127.0.0.1", 0),
        "USE_ACL": False,
        "SUB_ACL": acl_permit_all(),
        "TG1_ACL": acl_permit_all(),
        "TG2_ACL": acl_permit_all(),
        "RELAX_CHECKS": True,
        "ENHANCED_OBP": enhanced,
        "VER": 5,
    }


@dataclass
class CapturedDmra:
    target_system: str
    packets: list[bytes]
    exclude_peer: bytes | None = None


@dataclass
class CapturedBcsq:
    system_name: str
    tgid: bytes
    stream_id: bytes


@contextmanager
def patch_bridge_wall_time(clock: FakeClock):
    """Patch ``bridge_use_cases.time.time`` to the harness clock (OBP path)."""
    import adn_server.application.bridge_use_cases as buc

    original = buc.time.time
    buc.time.time = clock.time
    try:
        yield
    finally:
        buc.time.time = original


def active_bridge(
    tg_id: int,
    entries: tuple[tuple[str, int], ...],
    timeout_minutes: int = 1,
) -> dict[str, list[dict[str, Any]]]:
    tg_bytes = bytes_3(tg_id)
    key = str(tg_id)
    return {
        key: [
            {
                "SYSTEM": system,
                "TS": slot,
                "TGID": tg_bytes,
                "ACTIVE": True,
                "TIMEOUT": timeout_minutes * 60,
                "TO_TYPE": "ON",
                "OFF": [],
                "ON": [tg_bytes],
                "RESET": [],
                "TIMER": 0,
            }
            for system, slot in entries
        ]
    }


class DeterministicScenario:
    """Wires BridgeUseCases with fake protocols and outbound capture."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        bridges: dict[str, list[dict[str, Any]]] | None = None,
        *,
        enable_reporting: bool = False,
    ) -> None:
        self.config = copy.deepcopy(config or minimal_config())
        if enable_reporting:
            self.config.setdefault("REPORTS", {})["REPORT"] = True
        self.clock = FakeClock()
        self.capture = PacketCapture()
        self.dmra_capture: list[CapturedDmra] = []
        self.bcsq_capture: list[CapturedBcsq] = []
        self.report_factory = FakeReportFactory() if enable_reporting else None
        self.reporting = (
            ReportingUseCases(FakeReportSender(self.report_factory), self.config)
            if self.report_factory
            else None
        )
        self.router = InMemoryBridgeRouter()
        self.router.set_bridges(copy.deepcopy(bridges or {}))
        self.protocols: dict[str, FakeHbpProtocol | FakeObpProtocol] = {}
        self._wire_protocols_from_config()
        self.bridge = BridgeUseCases(
            self.router,
            self.config,
            send_to_system=self._send_capture,
            get_protocols=lambda: self.protocols,
            reporting=self.reporting,
            send_bcsq=self._send_bcsq_capture,
            send_dmra_to_system=self._send_dmra_capture,
            get_dmra_blocks=lambda _sys, _sid: None,
            encode_emblc=encode_emblc,
            ta_emblc_encoder=default_ta_emblc_encoder,
        )

    def _wire_protocols_from_config(self) -> None:
        self.protocols.clear()
        for name, syscfg in self.config.get("SYSTEMS", {}).items():
            if syscfg.get("MODE") == "OPENBRIDGE":
                self.protocols[name] = FakeObpProtocol(name)
            else:
                self.protocols[name] = FakeHbpProtocol(name)

    def _send_capture(self, target_system: str, packet: bytes, **kwargs: Any) -> None:
        self.capture.recorder(target_system)(
            packet,
            hops=kwargs.get("_hops", kwargs.get("hops", b"")),
            ber=kwargs.get("_ber", kwargs.get("ber", b"\x00")),
            rssi=kwargs.get("_rssi", kwargs.get("rssi", b"\x00")),
            source_server=kwargs.get("_source_server", kwargs.get("source_server", b"\x00\x00\x00\x00")),
            source_rptr=kwargs.get("_source_rptr", kwargs.get("source_rptr", b"\x00\x00\x00\x00")),
        )

    def _send_bcsq_capture(self, system_name: str, tgid: bytes, stream_id: bytes) -> None:
        self.bcsq_capture.append(CapturedBcsq(system_name, tgid, stream_id))

    def _send_dmra_capture(
        self,
        target_system: str,
        packets: list[bytes],
        exclude_peer: bytes | None = None,
    ) -> int:
        self.dmra_capture.append(
            CapturedDmra(target_system, list(packets), exclude_peer=exclude_peer)
        )
        return 0 if exclude_peer else len(packets)

    def seed_obp_stream(
        self,
        system_name: str,
        stream_id: int | bytes,
        *,
        tgid: int | bytes = 52090,
        rf_src: int | bytes = 3120001,
        peer_id: int | bytes = 1001,
        first_at: float | None = None,
    ) -> None:
        """Pre-populate OBP STATUS for loop-control scenarios."""
        proto = self.protocols[system_name]
        if not isinstance(proto, FakeObpProtocol):
            raise TypeError(f"{system_name} is not OPENBRIDGE")
        sid = bytes_4(stream_id)
        t0 = self.clock.time() if first_at is None else first_at
        proto.STATUS[sid] = {
            "START": t0,
            "CONTENTION": False,
            "RFS": bytes_3(rf_src),
            "TGID": bytes_3(tgid),
            "1ST": perf_counter() - 1.0,
            "lastSeq": False,
            "lastData": False,
            "RX_PEER": bytes_4(peer_id),
            "packets": 1,
            "loss": 0,
            "crcs": set(),
            "LC": b"\x00\x00\x00" + bytes_3(tgid) + bytes_3(rf_src),
        }

    def seed_hbp_slot_stream(
        self,
        system_name: str,
        slot: int,
        stream_id: int | bytes,
        *,
        tgid: int | bytes = 91,
        rf_src: int | bytes = 3120001,
        peer_id: int | bytes = 1001,
    ) -> None:
        """Pre-populate competing HBP slot STATUS for loop-control scenarios."""
        proto = self.protocols[system_name]
        if not isinstance(proto, FakeHbpProtocol):
            raise TypeError(f"{system_name} is not HBP")
        proto.STATUS[slot] = {
            "RX_STREAM_ID": bytes_4(stream_id),
            "RX_PEER": bytes_4(peer_id),
            "RX_RFS": bytes_3(rf_src),
            "RX_TGID": bytes_3(tgid),
            "RX_TIME": self.clock.time(),
            "RX_START": self.clock.time(),
            "packets": 1,
        }

    def _sync_hbp_slot(self, system_name: str, args: dict[str, Any]) -> None:
        """Mirror udp_hbp STATUS[slot] updates after an accepted HBP packet."""
        proto = self.protocols.get(system_name)
        if not isinstance(proto, FakeHbpProtocol):
            return
        slot = args["slot"]
        st = proto.STATUS.setdefault(slot, {})
        st["RX_PEER"] = args["peer_id"]
        st["RX_SEQ"] = args["seq"]
        st["RX_RFS"] = args["rf_src"]
        st["RX_TYPE"] = args["dtype_vseq"]
        st["RX_TGID"] = args["dst_id"]
        st["RX_TIME"] = self.clock.time()
        st["RX_STREAM_ID"] = args["stream_id"]
        if args["frame_type"] == HBPF_DATA_SYNC and args["dtype_vseq"] == HBPF_SLT_VHEAD:
            st["RX_LC"] = bytes_3(0) + args["dst_id"] + args["rf_src"]

    def inject_hbp(
        self,
        system_name: str,
        spec: PacketSpec,
        *,
        ingress_pkt_time: float | None = None,
    ) -> bool | None:
        args = spec.decoded_hbp_args()
        pkt_time = self.clock.time() if ingress_pkt_time is None else ingress_pkt_time
        ok = self.bridge.dmrd_received(system_name, ingress_pkt_time=pkt_time, **args)
        if ok is not False:
            self._sync_hbp_slot(system_name, args)
        return ok

    def inject_unit(
        self,
        system_name: str,
        spec: PacketSpec,
    ) -> bool | None:
        """Inject a unit (private) call packet; patches bridge wall time to harness clock."""
        args = spec.decoded_hbp_args()
        with patch_bridge_wall_time(self.clock):
            ok = self.bridge.dmrd_received(system_name, **args)
        if ok is not False:
            self._sync_hbp_slot(system_name, args)
        return ok

    def inject_obp(
        self,
        system_name: str,
        spec: PacketSpec,
        *,
        obp_hops: bytes = b"\x00\x00\x00\x00",
        obp_source_server: bytes | None = None,
    ) -> bool | None:
        args = spec.decoded_hbp_args()
        return self.bridge.dmrd_received(
            system_name,
            obp_use_parsed=True,
            obp_hops=obp_hops,
            obp_source_server=obp_source_server or bytes_4(9990),
            **args,
        )

    @staticmethod
    def voice_head_spec(base: PacketSpec) -> PacketSpec:
        return PacketSpec(
            peer_id=base.peer_id,
            rf_src=base.rf_src,
            dst_id=base.dst_id,
            slot=base.slot,
            stream_id=base.stream_id,
            seq=0,
            call_type=base.call_type,
            frame_type=HBPF_DATA_SYNC,
            dtype_vseq=HBPF_SLT_VHEAD,
            payload=base.payload,
        )

    @staticmethod
    def voice_burst_spec(base: PacketSpec, seq: int, dtype_vseq: int = 0) -> PacketSpec:
        return PacketSpec(
            peer_id=base.peer_id,
            rf_src=base.rf_src,
            dst_id=base.dst_id,
            slot=base.slot,
            stream_id=base.stream_id,
            seq=seq,
            call_type=base.call_type,
            frame_type=HBPF_VOICE,
            dtype_vseq=dtype_vseq,
            payload=base.payload,
        )

    @staticmethod
    def voice_term_spec(base: PacketSpec, seq: int = 99) -> PacketSpec:
        return PacketSpec(
            peer_id=base.peer_id,
            rf_src=base.rf_src,
            dst_id=base.dst_id,
            slot=base.slot,
            stream_id=base.stream_id,
            seq=seq,
            call_type=base.call_type,
            frame_type=HBPF_DATA_SYNC,
            dtype_vseq=HBPF_SLT_VTERM,
            payload=base.payload,
        )

    @staticmethod
    def unit_voice_head_spec(
        base: PacketSpec,
        *,
        dst_id: int | bytes | None = None,
        rf_src: int | bytes | None = None,
    ) -> PacketSpec:
        return PacketSpec(
            peer_id=base.peer_id,
            rf_src=rf_src if rf_src is not None else base.rf_src,
            dst_id=dst_id if dst_id is not None else base.dst_id,
            slot=base.slot,
            stream_id=base.stream_id,
            seq=0,
            call_type="unit",
            frame_type=HBPF_DATA_SYNC,
            dtype_vseq=HBPF_SLT_VHEAD,
            payload=base.payload,
        )

    @staticmethod
    def unit_voice_burst_spec(base: PacketSpec, seq: int, dtype_vseq: int = 1) -> PacketSpec:
        return PacketSpec(
            peer_id=base.peer_id,
            rf_src=base.rf_src,
            dst_id=base.dst_id,
            slot=base.slot,
            stream_id=base.stream_id,
            seq=seq,
            call_type="unit",
            frame_type=HBPF_VOICE,
            dtype_vseq=dtype_vseq,
            payload=base.payload,
        )

    @staticmethod
    def unit_data_header_spec(
        base: PacketSpec,
        *,
        dst_id: int | bytes | None = None,
        dtype_vseq: int = 6,
    ) -> PacketSpec:
        return PacketSpec(
            peer_id=base.peer_id,
            rf_src=base.rf_src,
            dst_id=dst_id if dst_id is not None else base.dst_id,
            slot=base.slot,
            stream_id=base.stream_id,
            seq=0,
            call_type="unit",
            frame_type=HBPF_DATA_SYNC,
            dtype_vseq=dtype_vseq,
            payload=base.payload,
        )
