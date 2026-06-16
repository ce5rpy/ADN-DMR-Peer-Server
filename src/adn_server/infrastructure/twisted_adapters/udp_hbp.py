# ADN DMR Peer Server - UDP HBP protocol
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
# Derived from ADN DMR Server / FreeDMR  / HBlink. Original license:
###############################################################################
# Copyright (C) 2026 Joaquin Madrid Belando, EA5GVK <ea5gvk@gmail.com>
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
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
# Source of truth: adn-dmr-server hblink.py master_datagramReceived / HBSYSTEM.

"""UDP HBP: direct port from hblink.py. MASTER uses same logic, log strings and packet handling as legacy."""

from __future__ import annotations

import logging
import time
from binascii import a2b_hex as bhex
from collections import deque
from hashlib import sha256
from random import randint
from typing import Any, Callable

from ...domain.dmr import decode
from ...domain.dmr.const import LC_OPT
from twisted.internet import reactor, task
from twisted.internet.protocol import DatagramProtocol

from ...application.routing.helpers import (
    clear_peer_rx_status_slots,
    clear_peer_ua_sessions,
    is_special_tg,
    is_unit_data_ingress,
    parse_dmrd_route_fields,
    peer_matches_rf_source,
    peer_should_receive_group_voice,
    remap_dmrd_to_peer_static_slot,
    peer_single_exclusive_tgid,
    register_peer_ua_session,
    seed_peer_ua_session_from_status,
    tg4000_reset_on_vhead,
)
from ...application.routing.peer_downlink_index import (
    build_peer_downlink_index,
    count_connected_peers,
    invalidate_peer_options_cache,
)
from ...application.proxy.deployment import is_proxy_inject_only
from ...domain import bytes_4, int_id
from ...domain.talker_alias import (
    DMRA_PACKET_LEN,
    decode_ta_from_blocks,
    parse_dmra_packet,
    store_ta_block,
    try_buffer_ta_from_voice_fragments,
)
from ...domain.mesh_routing import MeshEgress, MeshIngress, PeerMeshConfig
from ..mesh.dmre_v5 import parse_dmre_trailer
from ..mesh.registry import MeshCodecRegistry
from ..config_push_throttle import ConfigPushThrottle
from ..mesh.obp_v1 import (
    build_bcka,
    build_bcve,
    build_bcsq,
    verify_bcka,
    verify_bcsq,
    verify_bcst,
    verify_bcve,
)
from ..hbp_constants import (
    BC,
    BCKA,
    BCSQ,
    BCST,
    BCVE,
    DMR,
    DMRA,
    DMRD,
    DMRE,
    EOBP,
    HBPF_DATA_SYNC,
    HBPF_SLT_VHEAD,
    HBPF_SLT_VTERM,
    MSTC,
    MSTCL,
    MSTN,
    MSTNAK,
    MSTP,
    MSTPONG,
    PRBL,
    PRIN,
    RPTA,
    RPTACK,
    RPTC,
    RPTCL,
    RPTK,
    RPTL,
    RPTO,
    RPTP,
    RPTPING,
    VER,
)

logger = logging.getLogger(__name__)

_DEFAULT_MESH_REGISTRY = MeshCodecRegistry()


def get_user_password(radio_id: int):
    """Legacy get_user_password (hblink.py). Stub: returns None (no individual passwords)."""
    return None


def _get_passphrase_bytes(sys_cfg: dict) -> bytes:
    """PASSPHRASE as bytes (legacy config has bytes)."""
    p = sys_cfg.get("PASSPHRASE") or b""
    return p if isinstance(p, bytes) else p.encode("utf-8")


def _calc_hash(salt_str: bytes, password: bytes) -> bytes:
    """Same as legacy: bhex(sha256(salt_str + password).hexdigest())."""
    return bhex(sha256(salt_str + password).hexdigest())


def _make_slot_status() -> dict[str, Any]:
    """One slot STATUS dict (legacy routerHBP.STATUS[1] or [2])."""
    now = time.time()
    return {
        "RX_START": now,
        "TX_START": now,
        "RX_SEQ": 0,
        "RX_RFS": b"\x00",
        "TX_RFS": b"\x00",
        "RX_PEER": b"\x00",
        "TX_PEER": b"\x00",
        "RX_STREAM_ID": b"\x00",
        "TX_STREAM_ID": b"\x00",
        "RX_TGID": b"\x00\x00\x00",
        "TX_TGID": b"\x00\x00\x00",
        "RX_TIME": now,
        "TX_TIME": now,
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_LC": b"\x00",
        "TX_H_LC": b"\x00",
        "TX_T_LC": b"\x00",
        "TX_EMB_LC": {1: b"\x00", 2: b"\x00", 3: b"\x00", 4: b"\x00"},
        "lastSeq": False,
        "lastData": False,
        "packets": 0,
        "crcs": set(),
    }


class HBPProtocol(DatagramProtocol):
    """Port of HBSYSTEM (hblink.py). MASTER: same master_datagramReceived logic and logs."""

    def __init__(
        self,
        system_name: str,
        config: dict[str, Any],
        report_factory: Any = None,
        router: Any = None,
        dmrd_received: Callable[..., None] | None = None,
        get_user_password_callback: Callable[[int], bytes | None] | None = None,
        on_play_file_request: Callable[[str, str], None] | None = None,
        on_handle_recording: Callable[..., None] | None = None,
        on_in_band_signalling: Callable[[str, int, bytes, float], None] | None = None,
        on_options_received: Callable[..., None] | None = None,
        on_deactivate_dynamic_relays: Callable[[str], None] | None = None,
        on_obp_bcsq_received: Callable[[str, bytes, bytes], None] | None = None,
        on_talker_alias_local_repeat: Callable[[str, bytes, bytes, bytes], None] | None = None,
        on_talker_alias_repeat_prepare: Callable[[str, bytes, bytes, bytes, int, bytes], None] | None = None,
        on_talker_alias_repeat_burst: Callable[[str, int, bytes, int, bytes], bytes] | None = None,
        on_talker_alias_stream_end: Callable[[str, bytes], None] | None = None,
        on_dmra_fragment_stored: Callable[[str, bytes, bytes, bytes], None] | None = None,
        routing_table_for_report: Callable[[], dict[str, Any]] | None = None,
        get_subscription_store: Callable[[], Any] | None = None,
        mesh_registry: MeshCodecRegistry | None = None,
    ) -> None:
        self._CONFIG = config
        self._system = system_name
        self._report = report_factory
        self._router = router
        self._routing_table_for_report = routing_table_for_report
        self._get_subscription_store = get_subscription_store
        self._dmrd_received = dmrd_received
        self._get_user_password = get_user_password_callback if get_user_password_callback is not None else get_user_password
        self._on_play_file_request = on_play_file_request
        self._on_handle_recording = on_handle_recording
        self._on_in_band_signalling = on_in_band_signalling
        self._on_options_received = on_options_received
        self._on_deactivate_dynamic_relays = on_deactivate_dynamic_relays
        self._on_obp_bcsq_received = on_obp_bcsq_received
        self._on_talker_alias_local_repeat = on_talker_alias_local_repeat
        self._on_talker_alias_repeat_prepare = on_talker_alias_repeat_prepare
        self._on_talker_alias_repeat_burst = on_talker_alias_repeat_burst
        self._on_talker_alias_stream_end = on_talker_alias_stream_end
        self._on_dmra_fragment_stored = on_dmra_fragment_stored
        self._mesh_registry = mesh_registry if mesh_registry is not None else _DEFAULT_MESH_REGISTRY
        self._config = config.get("SYSTEMS", {}).get(system_name, {})
        if self._config.get("MODE") == "OPENBRIDGE":
            self._laststrid = deque([], 20)
            # Legacy parity: routerOBP.__init__ uses a flat dict keyed by stream_id
            # only (bridge_master.py:1911). The trimmer iterates the whole dict so
            # every entry seeded by to_target / sendDataToOBP / pvt_call_received is
            # cleaned uniformly. No pre-seed of slot keys here.
            self.STATUS: dict[Any, Any] = {}
            self._bcsq_log_once: deque = deque(maxlen=1024)
        else:
            self._laststrid = {1: b"", 2: b""}
            self.STATUS = {1: _make_slot_status(), 2: _make_slot_status()}
        if self._config.get("MODE") == "MASTER":
            self._peers = self._config.setdefault("PEERS", {})
            self._downlink_index_dirty = True
            self._downlink_index = None
            self._connected_peer_count = 0
            self._config_push_delayed = None
            self._config_push_throttle = ConfigPushThrottle()
            self._refresh_connected_peer_count()
        else:
            self._peers = {}
        if self._config.get("MODE") in ("MASTER", "OPENBRIDGE"):
            self._dmra_by_stream: dict[bytes, dict[str, Any]] = {}
            self._dmra_rf_stream: dict[tuple[bytes, bytes], bytes] = {}
            self._ta_voice_acc: dict[bytes, dict[int, Any]] = {}
            self._ta_decoded_logged: set[bytes] = set()
        else:
            self._dmra_by_stream = {}
            self._dmra_rf_stream = {}
            self._ta_voice_acc = {}
            self._ta_decoded_logged = set()
        if self._config.get("MODE") == "PEER":
            self._dmra_downlink: dict[bytes, dict[str, Any]] = {}
        if self._config.get("MODE") == "PEER":
            self._stats = self._config.get("STATS", {})
        else:
            self._stats = {}

    def startProtocol(self) -> None:
        if self._config.get("MODE") == "OPENBRIDGE":
            logger.info(
                "(%s) Starting OBP. TARGET_IP: %s, TARGET_PORT: %s",
                self._system,
                self._config.get("TARGET_IP", ""),
                self._config.get("TARGET_PORT", ""),
            )
            # bridge_master.routerOBP.to_target skips ENHANCED targets when '_bcka' not in SYSTEMS[name].
            # Seed so cross-OBP forwarding works before the first inbound BCKA/DMR on *this* leg.
            self._config["_bcka"] = time.time()
            if self._config.get("ENHANCED_OBP"):
                self._bcka_loop = task.LoopingCall(self._obp_send_bcka)
                _bcka_d = self._bcka_loop.start(10)
                _bcka_d.addErrback(self._looping_err_handle)
                self._bcve_loop = task.LoopingCall(self._obp_send_bcve)
                _bcve_d = self._bcve_loop.start(60)
                _bcve_d.addErrback(self._looping_err_handle)
        elif self._config.get("MODE") == "MASTER":
            ping_time = self._CONFIG.get("GLOBAL", {}).get("PING_TIME", 10)
            self._maintenance_loop = task.LoopingCall(self._master_maintenance_loop)
            _maint_d = self._maintenance_loop.start(ping_time)
            _maint_d.addErrback(self._looping_err_handle)
        elif self._config.get("MODE") == "PEER":
            ping_time = self._CONFIG.get("GLOBAL", {}).get("PING_TIME", 10)
            self._maintenance_loop = task.LoopingCall(self._peer_maintenance_loop)
            _maint_d = self._maintenance_loop.start(ping_time)
            _maint_d.addErrback(self._looping_err_handle)

    def apply_system_config(self, config: dict[str, Any]) -> None:
        """Hot-reload: refresh system dict from live CONFIG (keeps STATUS / streams)."""
        self._CONFIG = config
        sys_cfg = config.get("SYSTEMS", {}).get(self._system, {})
        self._config = sys_cfg
        if sys_cfg.get("MODE") == "MASTER":
            self._peers = sys_cfg.setdefault("PEERS", {})
            self._refresh_connected_peer_count()
            self._mark_downlink_index_dirty()

    # ── Exact port of hblink.py send_peers / send_peer / send_master / send_system ──

    def send_peers(self, _packet: bytes, _hops: bytes = b"", _ber: bytes = b"\x00", _rssi: bytes = b"\x00", _source_server: bytes = b"\x00\x00\x00\x00", _source_rptr: bytes = b"\x00\x00\x00\x00") -> None:
        if len(_packet) < 54:
            _packet = b"".join([_packet, _ber, _rssi])
        for _peer in self._iter_downlink_peers(_packet):
            self.send_peer(_peer, _packet)

    def _inject_multi_peer_options_filter(self) -> bool:
        """Inject-only proxy: always filter downlink by each peer's own OPTIONS."""
        return is_proxy_inject_only(self._CONFIG, self._system)

    def _mark_downlink_index_dirty(self) -> None:
        self._downlink_index_dirty = True

    def _refresh_connected_peer_count(self) -> None:
        self._connected_peer_count = count_connected_peers(self._peers)

    def _cached_connected_peer_count(self) -> int:
        """Return cached count; refresh once if cache is zero but peers exist."""
        n = self._connected_peer_count
        if n <= 0 and self._peers:
            self._refresh_connected_peer_count()
            n = self._connected_peer_count
        return n

    def _ensure_downlink_index(self):
        if not self._downlink_index_dirty and self._downlink_index is not None:
            return self._downlink_index
        self._downlink_index = build_peer_downlink_index(self._peers, self._config)
        self._downlink_index_dirty = False
        return self._downlink_index

    def _iter_downlink_peers(self, packet: bytes):
        """Peer ids to consider for MASTER downlink / REPEAT (indexed when inject-only)."""
        if not self._inject_multi_peer_options_filter():
            return self._peers.keys()
        parsed = parse_dmrd_route_fields(packet)
        if parsed is None:
            return self._peers.keys()
        slot, tgid, call_type = parsed
        if call_type not in ("group", "vcsbk"):
            return self._peers.keys()
        if is_special_tg(str(tgid)):
            return self._peers.keys()
        connected = self._cached_connected_peer_count()
        if connected <= 0:
            return ()
        index = self._ensure_downlink_index()
        return index.candidates(slot, tgid, connected_count=connected)

    def _peer_mesh_config(self) -> PeerMeshConfig:
        _global = self._CONFIG.get("GLOBAL", {})
        _sid = _global.get("SERVER_ID", b"\x00\x00\x00\x00")
        _server_id = (
            _sid
            if isinstance(_sid, bytes) and len(_sid) >= 4
            else bytes_4(int(_sid) & 0xFFFFFFFF if isinstance(_sid, int) else 0)
        )
        _ver_cfg = self._config.get("VER")
        wire_ver = int(_ver_cfg) if _ver_cfg is not None else None
        return PeerMeshConfig(
            passphrase=_get_passphrase_bytes(self._config),
            server_id=_server_id,
            wire_ver=wire_ver,
        )

    def _mesh_session_codec(self) -> str | None:
        codec = self._config.get("_mesh_session_codec")
        return codec if isinstance(codec, str) else None

    def _note_mesh_ingress(self, ingress: MeshIngress) -> None:
        self._config["_mesh_session_codec"] = ingress.codec
        if ingress.embedded_ver is not None:
            self._config["VER"] = ingress.embedded_ver

    def _try_decode_mesh_ingress(self, datagram: bytes) -> MeshIngress | None:
        ingress = self._mesh_registry.decode_auto(datagram, self._peer_mesh_config())
        if ingress is not None:
            self._note_mesh_ingress(ingress)
        return ingress

    def _encode_mesh_egress(
        self,
        inner_packet: bytes,
        *,
        hops: bytes,
        ber: bytes,
        rssi: bytes,
        source_server: bytes,
        source_rptr: bytes,
    ) -> bytes | None:
        mesh_protocol = str(self._config.get("MESH_PROTOCOL", "auto"))
        egress = MeshEgress(
            inner_packet=inner_packet,
            hops=hops or b"\x01",
            ber=ber,
            rssi=rssi,
            source_server=source_server,
            source_rptr=source_rptr,
        )
        return self._mesh_registry.encode(
            mesh_protocol,
            egress,
            self._peer_mesh_config(),
            session_codec=self._mesh_session_codec(),
        )

    def _apply_tg4000_reset(self, peer_id: bytes, slot: int, call_type: str) -> None:
        """Clear per-peer UA dynamics; legacy bridge reset only outside inject-only."""
        peer = self._peers.get(peer_id, {})
        clear_peer_ua_sessions(peer, self._config, peer_id, slot=slot)
        _kind = "Private call to ID" if call_type == "unit" else "Group call to TG"
        if self._inject_multi_peer_options_filter():
            self._push_config_to_monitor()
            logger.info(
                "(%s) %s 4000 received on TS %s — clearing dynamic TGs for peer %s",
                self._system, _kind, slot, int_id(peer_id),
            )
            return
        if self._on_deactivate_dynamic_relays:
            logger.info(
                "(%s) %s 4000 received on TS %s — deactivating all dynamic bridges",
                self._system, _kind, slot,
            )
            self._on_deactivate_dynamic_relays(self._system)

    def _handle_tg4000_packet(
        self,
        peer_id: bytes,
        slot: int,
        int_dst_id: int,
        call_type: str,
        frame_type: int,
        dtype_vseq: int,
    ) -> bool:
        """Legacy early return for TG/ID 4000; reset once per PTT on voice header only."""
        if int_dst_id != 4000:
            return False
        if tg4000_reset_on_vhead(int_dst_id, frame_type, dtype_vseq):
            self._apply_tg4000_reset(peer_id, slot, call_type)
        return True

    def _peer_should_receive_dmrd(self, peer_id: bytes, packet: bytes) -> bool:
        if not self._inject_multi_peer_options_filter():
            return True
        if peer_id not in self._peers:
            return False
        parsed = parse_dmrd_route_fields(packet)
        if parsed is None:
            return self._cached_connected_peer_count() <= 1
        slot, tgid, call_type = parsed
        if call_type not in ("group", "vcsbk"):
            return True
        # Parrot / echo (9990–9999): not in per-hotspot OPTIONS; deliver to last RX peer on slot.
        if is_special_tg(str(tgid)):
            slot_st = self.STATUS.get(slot, {})
            if int_id(slot_st.get("RX_TGID", b"\x00\x00\x00")) == tgid:
                rx_peer = slot_st.get("RX_PEER", b"")
                if rx_peer and rx_peer != b"\x00\x00\x00\x00":
                    return bytes_4(int_id(peer_id)) == bytes_4(int_id(rx_peer))
            if len(packet) >= 8 and peer_matches_rf_source(peer_id, packet[5:8], self._peers):
                return True
            return self._cached_connected_peer_count() == 1
        connected = self._cached_connected_peer_count()
        store = self._get_subscription_store() if self._get_subscription_store else None
        return peer_should_receive_group_voice(
            self._peers[peer_id],
            slot,
            tgid,
            peer_id=peer_id,
            system=self._system,
            bridges=None,
            subscription_store=store,
            connected_count=connected,
            sys_cfg=self._config,
        )

    def send_peer(self, _peer: bytes, _packet: bytes) -> None:
        if _packet[:4] == DMRD:
            if not self._peer_should_receive_dmrd(_peer, _packet):
                return
            peer = self._peers.get(_peer)
            if peer is not None:
                _packet = remap_dmrd_to_peer_static_slot(_packet, peer)
            _packet = b"".join([_packet[:11], _peer, _packet[15:]])
        self.transport.write(_packet, self._peers[_peer]["SOCKADDR"])

    def _ta_buffer_enabled(self) -> bool:
        return self._config.get("MODE") in ("MASTER", "OPENBRIDGE")

    def note_dmrd_stream(self, peer_id: bytes, rf_src: bytes, stream_id: bytes) -> None:
        """Associate active stream with source for DMRA pass-through buffering."""
        if not self._ta_buffer_enabled() or not stream_id:
            return
        self._dmra_rf_stream[(peer_id, rf_src)] = stream_id
        self._promote_dmra_provisional_key(rf_src, stream_id)

    def _promote_dmra_provisional_key(self, provisional: bytes, stream_id: bytes) -> None:
        """Move TA blocks buffered under ``rf_src`` (pre-VHEAD) to the real stream id."""
        if provisional == stream_id:
            return
        entry = self._dmra_by_stream.pop(provisional, None)
        if not entry:
            return
        target = self._dmra_by_stream.setdefault(
            stream_id,
            {
                "blocks": {},
                "rf_src": entry.get("rf_src", b""),
                "peer": entry.get("peer", b""),
                "last": entry.get("last", time.time()),
            },
        )
        target["blocks"].update(entry.get("blocks", {}))
        target["last"] = max(float(target.get("last", 0)), float(entry.get("last", 0)))
        if entry.get("rf_src"):
            target["rf_src"] = entry["rf_src"]
        if entry.get("peer"):
            target["peer"] = entry["peer"]

    def store_dmra_packet(self, peer_id: bytes, data: bytes) -> None:
        """Buffer one DMRA block from a hotspot (MASTER receive path)."""
        parsed = parse_dmra_packet(data)
        if not parsed:
            return
        rf_src, block_id, payload = parsed
        stream_id = self._dmra_rf_stream.get((peer_id, rf_src))
        if not stream_id:
            # Legacy hblink: DMRA may arrive before the first DMRD; key by rf_src until then.
            stream_id = rf_src
        now = time.time()
        entry = self._dmra_by_stream.setdefault(
            stream_id,
            {"blocks": {}, "rf_src": rf_src, "peer": peer_id, "last": now},
        )
        if not store_ta_block(entry["blocks"], block_id, payload):
            return
        entry["last"] = now
        entry["rf_src"] = rf_src
        if self._on_dmra_fragment_stored:
            self._on_dmra_fragment_stored(self._system, peer_id, rf_src, stream_id)

    def store_ta_from_voice_burst(
        self,
        peer_id: bytes,
        rf_src: bytes,
        stream_id: bytes,
        vseq: int,
        dmrpkt: bytes,
    ) -> None:
        """Buffer TA from embedded LC in voice bursts B–E (MMDVM DMRSlot path)."""
        if not self._ta_buffer_enabled() or not stream_id:
            return
        if not self._CONFIG.get("GLOBAL", {}).get("TALKER_ALIAS", False):
            return
        entry = self._dmra_by_stream.setdefault(
            stream_id,
            {"blocks": {}, "rf_src": rf_src, "peer": peer_id, "last": time.time()},
        )
        acc = self._ta_voice_acc.setdefault(stream_id, {})
        if try_buffer_ta_from_voice_fragments(acc, vseq, dmrpkt, entry["blocks"]):
            entry["last"] = time.time()
            entry["rf_src"] = rf_src
            entry["peer"] = peer_id
            if stream_id not in self._ta_decoded_logged:
                text = decode_ta_from_blocks(entry["blocks"])
                if text:
                    self._ta_decoded_logged.add(stream_id)
                    logger.debug(
                        "(%s) *TALKER ALIAS* decoded '%s' from embedded voice (src %s stream %s)",
                        self._system, text, int_id(rf_src), int_id(stream_id),
                    )
            if self._on_dmra_fragment_stored:
                self._on_dmra_fragment_stored(self._system, peer_id, rf_src, stream_id)

    def clear_ta_stream_buffer(self, stream_id: bytes) -> None:
        self._dmra_by_stream.pop(stream_id, None)
        self._ta_voice_acc.pop(stream_id, None)
        self._ta_decoded_logged.discard(stream_id)

    def copy_ta_stream_buffer(self, from_stream: bytes, to_stream: bytes) -> None:
        """Carry decoded TA blocks from recording stream to echo playback stream."""
        entry = self._dmra_by_stream.get(from_stream)
        if not entry or not entry.get("blocks"):
            return
        self._dmra_by_stream[to_stream] = {
            "blocks": dict(entry["blocks"]),
            "rf_src": entry.get("rf_src", b""),
            "peer": entry.get("peer", b""),
            "last": time.time(),
        }

    def get_dmra_blocks(self, stream_id: bytes) -> dict[int, bytes] | None:
        """Return buffered DMRA block payloads for a stream, if any."""
        entry = self._dmra_by_stream.get(stream_id)
        if not entry:
            return None
        blocks = entry.get("blocks")
        return dict(blocks) if isinstance(blocks, dict) else None

    def trim_dmra_streams(self, max_age: float = 180.0) -> None:
        """Drop stale DMRA buffers (same order of magnitude as stream trimmer)."""
        if not self._ta_buffer_enabled():
            return
        now = time.time()
        cutoff = now - max_age
        for stream_id in list(self._dmra_by_stream):
            if self._dmra_by_stream[stream_id].get("last", 0) < cutoff:
                del self._dmra_by_stream[stream_id]
                self._ta_voice_acc.pop(stream_id, None)
                self._ta_decoded_logged.discard(stream_id)

    def send_dmra_to_peers(self, packets: list[bytes], exclude_peer: bytes | None = None) -> int:
        """Send DMRA packets to logged-in peers (MASTER downlink). Returns peer count."""
        if self._config.get("MODE") != "MASTER":
            return 0
        sent = 0
        for peer in self._peers:
            if exclude_peer and peer == exclude_peer:
                continue
            for pkt in packets:
                self.send_peer(peer, pkt)
            sent += 1
        return sent

    def send_dmra_system(self, packets: list[bytes], exclude_peer: bytes | None = None) -> int:
        """Send DMRA on this system link (MASTER → peers, PEER → upstream master)."""
        if self._config.get("MODE") == "MASTER":
            return self.send_dmra_to_peers(packets, exclude_peer=exclude_peer)
        if self._config.get("MODE") == "PEER":
            for pkt in packets:
                self.send_master(pkt)
        return 0

    def send_master(self, _packet: bytes, _hops: bytes = b"", _ber: bytes = b"\x00", _rssi: bytes = b"\x00", _source_server: bytes = b"\x00\x00\x00\x00", _source_rptr: bytes = b"\x00\x00\x00\x00") -> None:
        if _packet[:4] == DMRD:
            if len(_packet) < 54:
                _packet = b"".join([_packet[:11], self._config["RADIO_ID"], _packet[15:], _ber, _rssi])
            else:
                _packet = b"".join([_packet[:11], self._config["RADIO_ID"], _packet[15:]])
        self.transport.write(_packet, self._config["MASTER_SOCKADDR"])

    def send_system(
        self,
        _packet: bytes,
        _hops: bytes = b"",
        _ber: bytes = b"\x00",
        _rssi: bytes = b"\x00",
        _source_server: bytes = b"\x00\x00\x00\x00",
        _source_rptr: bytes = b"\x00\x00\x00\x00",
    ) -> None:
        if self._config.get("MODE") == "MASTER":
            self.send_peers(_packet, _hops, _ber, _rssi, _source_server, _source_rptr)
        elif self._config.get("MODE") == "OPENBRIDGE":
            # Global STUN (config) or per-system BCST (hblink sets _config['_STUN'] on BCST RX)
            if "STUN" in self._CONFIG or self._config.get("_STUN"):
                logger.info("(%s) Bridge STUNned, discarding", self._system)
                return
            if not _hops:
                _hops = (1).to_bytes(1, "big")
            if _packet[:3] == DMR and self._config.get("TARGET_IP"):
                _target_addr = (self._config["TARGET_IP"], self._config["TARGET_PORT"])
                _ver_cfg = self._config.get("VER")
                if "VER" in self._config and _ver_cfg in (2, 3):
                    logger.error("(%s) protocol version %s no longer supported", self._system, _ver_cfg)
                else:
                    _wire = self._encode_mesh_egress(
                        _packet,
                        hops=_hops,
                        ber=_ber,
                        rssi=_rssi,
                        source_server=_source_server,
                        source_rptr=_source_rptr,
                    )
                    if _wire is not None:
                        self.transport.write(_wire, _target_addr)
            else:
                if not self._config.get("TARGET_IP"):
                    logger.debug("(%s) Not sent packet as TARGET_IP not currently known", self._system)
                else:
                    logger.error("(%s) OpenBridge system was asked to send non DMR packet with send_system(): %s", self._system, _packet)
        elif self._config.get("MODE") == "PEER":
            self.send_master(_packet, _hops, _ber, _rssi, _source_server, _source_rptr)

    def send_voice_packet(
        self, pkt: bytes, _source_id: bytes, _dest_id: bytes, _slot: dict[str, Any]
    ) -> None:
        """Legacy sendVoicePacket: update STATUS for stream/slot then send_system(pkt)."""
        _stream_id = pkt[16:20]
        _pkt_time = time.time()
        if _stream_id not in self.STATUS:
            self.STATUS[_stream_id] = {
                "START": _pkt_time,
                "CONTENTION": False,
                "RFS": _source_id,
                "TGID": _dest_id,
                "LAST": _pkt_time,
            }
            _slot["TX_TGID"] = _dest_id
        else:
            self.STATUS[_stream_id]["LAST"] = _pkt_time
            _slot["TX_TIME"] = _pkt_time
        self.send_system(pkt)

    def dereg(self) -> None:
        """Graceful de-registration (legacy hblink.py dereg / master_dereg / peer_dereg)."""
        mode = self._config.get("MODE")
        if mode == "MASTER":
            for _peer in self._peers:
                self.send_peer(_peer, b"".join([MSTCL, _peer]))
                logger.info("(%s) De-Registration sent to Peer: %s (%s)", self._system, self._peers[_peer].get("CALLSIGN", b""), self._peers[_peer].get("RADIO_ID", b""))
        elif mode == "PEER":
            self.send_master(b"".join([RPTCL, self._config.get("RADIO_ID", b"\x00\x00\x00\x00")]))
            logger.info("(%s) De-Registration sent to Master: %s:%s", self._system, self._config.get("MASTER_SOCKADDR", ("?", "?"))[0], self._config.get("MASTER_SOCKADDR", ("?", "?"))[1])
        else:
            logger.info("(%s) is mode %s. No De-Registration required, continuing shutdown", self._system, mode)

    def validate_id(self, _peer_id: bytes):
        """Legacy validate_id (hblink.py lines 862-883). Returns True or callsign string or False."""
        if "ALLOW_UNREG_ID" not in self._config:
            return True
        if self._config.get("ALLOW_UNREG_ID"):
            return True
        _int_peer_id = int_id(_peer_id)
        _int_peer_id = int(str(_int_peer_id)[:7])
        _subscriber_ids = self._CONFIG.get("_SUB_IDS", {})
        _peer_ids = self._CONFIG.get("_PEER_IDS", {})
        _local_subscriber_ids = self._CONFIG.get("_LOCAL_SUBSCRIBER_IDS", {})
        if _int_peer_id in _local_subscriber_ids:
            return _local_subscriber_ids[_int_peer_id]
        if _int_peer_id in _subscriber_ids:
            return _subscriber_ids[_int_peer_id]
        if _int_peer_id in _peer_ids:
            return _peer_ids[_int_peer_id]
        return False

    def proxy_IPBlackList(self, peer_id: bytes, sockaddr: tuple[str, int]) -> None:
        """Legacy hblink.py proxy_IPBlackList: send PRBL to proxy to blacklist a peer's IP for 5 min."""
        _bltime = str(time.time() + 300)
        _prpacket = b"".join([PRBL, peer_id, _bltime.encode("UTF-8")])
        self.transport.write(_prpacket, sockaddr)

    def proxy_bad_peer(self) -> None:
        """Legacy hblink.py proxy_BadPeer: blacklist all current peer IPs (called on rate-limit violations)."""
        for _pi in getattr(self, "_peers", {}):
            self.proxy_IPBlackList(_pi, self._peers[_pi]["SOCKADDR"])

    def _push_config_to_monitor(self) -> None:
        """Schedule debounced CONFIG_SND when MASTER peer list or OPTIONS change."""
        if self._config_push_delayed is not None:
            return
        delay = self._config_push_throttle.debounce_seconds()
        self._config_push_delayed = reactor.callLater(delay, self._flush_config_to_monitor)

    def _flush_config_to_monitor(self) -> None:
        self._config_push_delayed = None
        report = self._report
        if report is None:
            return
        if not self._CONFIG.get("REPORTS", {}).get("REPORT", True):
            return
        systems = self._CONFIG.get("SYSTEMS", {})
        if hasattr(report, "set_systems"):
            report.set_systems(systems)
        if hasattr(report, "send_config"):
            report.send_config(systems)
            logger.debug("(REPORT) Pushed CONFIG_SND after peer state change on %s", self._system)

    def datagramReceived(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) < 4:
            return
        mode = self._config.get("MODE")
        if mode == "MASTER":
            self._master_datagram_received(data, addr)
        elif mode == "PEER":
            self._peer_datagram_received(data, addr)
        elif mode == "OPENBRIDGE":
            self._obp_datagram_received(data, addr)
        else:
            logger.debug("(%s) UDP received %d bytes from %s", self._system, len(data), addr)

    def _master_maintenance_loop(self) -> None:
        """Legacy master_maintenance_loop (hblink.py lines 731-755). Removes timed-out peers."""
        _global = self._CONFIG.get("GLOBAL", {})
        ping_time = _global.get("PING_TIME", 10)
        max_missed = _global.get("MAX_MISSED", 3)
        remove_list = deque()
        for peer in self._peers:
            _this_peer = self._peers[peer]
            if _this_peer.get("LAST_PING", 0) + (ping_time * max_missed) < time.time():
                remove_list.append(peer)
        for peer in remove_list:
            logger.info(
                "(%s) Peer %s (%s) has timed out and is being removed",
                self._system, self._peers[peer].get("CALLSIGN", b""), self._peers[peer].get("RADIO_ID", b""),
            )
            self.transport.write(b"".join([MSTCL, peer]), self._peers[peer]["SOCKADDR"])
            self._remove_peer(peer)
            if not self._peers:
                sys_cfg = self._CONFIG["SYSTEMS"][self._system]
                if "OPTIONS" in sys_cfg:
                    if "_default_options" in sys_cfg:
                        logger.info("(%s) Setting default Options: %s", self._system, sys_cfg["_default_options"])
                        sys_cfg["OPTIONS"] = sys_cfg["_default_options"]
                    else:
                        del sys_cfg["OPTIONS"]
                        logger.info("(%s) Deleting HBP Options", self._system)
                sys_cfg["_reset"] = True
        if remove_list:
            self._push_config_to_monitor()

    def _on_peer_disconnected(self, peer_id: bytes) -> None:
        """Drop SINGLE/UA session and stale slot STATUS when a hotspot leaves or re-logs in."""
        peer = self._peers.get(peer_id)
        sys_cfg = self._config
        if peer is not None:
            clear_peer_ua_sessions(peer, sys_cfg, peer_id)
        else:
            clear_peer_ua_sessions({}, sys_cfg, peer_id)
        clear_peer_rx_status_slots(self.STATUS, peer_id)

    def _remove_peer(self, peer_id: bytes) -> None:
        self._on_peer_disconnected(peer_id)
        self._peers.pop(peer_id, None)
        self._refresh_connected_peer_count()
        self._mark_downlink_index_dirty()

    def _master_datagram_received(self, _data: bytes, _sockaddr: tuple[str, int]) -> None:
        """Direct port of hblink.py master_datagramReceived (lines 888-1146)."""
        _command = _data[:4]
        _global = self._CONFIG.get("GLOBAL", {})

        if _command == DMRD:
            _peer_id = _data[11:15]
            if _peer_id not in self._peers:
                logger.info(
                    "(%s) DMRD ignored: peer %s not in peers (peers: %s)",
                    self._system, int_id(_peer_id), [int_id(p) for p in self._peers],
                )
            elif self._peers[_peer_id]["CONNECTION"] != "YES":
                logger.info(
                    "(%s) DMRD ignored: peer %s not CONNECTION=YES (state=%s)",
                    self._system, int_id(_peer_id), self._peers[_peer_id].get("CONNECTION", "?"),
                )
            elif self._peers[_peer_id]["SOCKADDR"] != _sockaddr:
                logger.info(
                    "(%s) DMRD ignored: peer %s SOCKADDR mismatch",
                    self._system, int_id(_peer_id),
                )
            if _peer_id in self._peers and self._peers[_peer_id]["CONNECTION"] == "YES" and self._peers[_peer_id]["SOCKADDR"] == _sockaddr:
                _seq = _data[4]
                _rf_src = _data[5:8]
                _dst_id = _data[8:11]
                _bits = _data[15]
                _slot = 2 if (_bits & 0x80) else 1
                if _bits & 0x40:
                    _call_type = "unit"
                elif (_bits & 0x23) == 0x23:
                    _call_type = "vcsbk"
                else:
                    _call_type = "group"
                _frame_type = (_bits & 0x30) >> 4
                _dtype_vseq = _bits & 0xF
                _stream_id = _data[16:20]
                if not int_id(_stream_id):
                    logger.warning("(%s) CALL DROPPED AS STREAM ID IS NULL FROM SUBSCRIBER %s", self._system, int_id(_rf_src))
                    return
                pkt_time = time.time()
                _int_dst_id = int_id(_dst_id)
                # ACL (legacy order and _laststrid)
                if self._router and _global.get("USE_ACL"):
                    if not self._router.acl_check(_rf_src, _global.get("SUB_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY GLOBAL ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 1 and not self._router.acl_check(_dst_id, _global.get("TG1_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS1 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 2 and not self._router.acl_check(_dst_id, _global.get("TG2_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS2 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                if self._router and self._config.get("USE_ACL"):
                    if not self._router.acl_check(_rf_src, self._config.get("SUB_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY SYSTEM ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 1 and not self._router.acl_check(_dst_id, self._config.get("TG1_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY SYSTEM TS1 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 2 and not self._router.acl_check(_dst_id, self._config.get("TG2_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY SYSTEM TS2 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                # SUB_MAP update (legacy routerHBP.dmrd_received)
                sub_map = self._CONFIG.get("_SUB_MAP")
                if sub_map is not None:
                    sub_map[_rf_src] = (self._system, _slot, pkt_time)
                self.note_dmrd_stream(_peer_id, _rf_src, _stream_id)
                if (
                    _call_type in ("group", "vcsbk")
                    and _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VHEAD
                ):
                    _prev_single_tg = peer_single_exclusive_tgid(
                        self._peers[_peer_id],
                        _slot,
                        self._config,
                        peer_id=_peer_id,
                        now=pkt_time,
                    )
                    if _int_dst_id != 4000:
                        register_peer_ua_session(
                            self._peers[_peer_id],
                            _peer_id,
                            _slot,
                            _int_dst_id,
                            self._config,
                            now=pkt_time,
                        )
                        self._mark_downlink_index_dirty()
                        if _prev_single_tg != _int_dst_id:
                            self._push_config_to_monitor()
                if (
                    _call_type in ("group", "vcsbk")
                    and _frame_type != HBPF_DATA_SYNC
                    and _dtype_vseq in (1, 2, 3, 4)
                    and len(_data) >= 53
                ):
                    self.store_ta_from_voice_burst(
                        _peer_id, _rf_src, _stream_id, _dtype_vseq, _data[20:53],
                    )
                if (
                    self._config.get("REPEAT", True)
                    and _call_type in ("group", "vcsbk")
                    and _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VHEAD
                ):
                    if self._on_talker_alias_repeat_prepare:
                        self._on_talker_alias_repeat_prepare(
                            self._system, _peer_id, _rf_src, _dst_id, _slot, _stream_id,
                        )
                    elif self._on_talker_alias_local_repeat:
                        self._on_talker_alias_local_repeat(
                            self._system, _peer_id, _rf_src, _stream_id,
                        )
                if self._config.get("REPEAT", True) and _call_type in ("group", "vcsbk"):
                    _repeat_tail = _data[15:]
                    if (
                        _dtype_vseq in (1, 2, 3, 4)
                        and len(_data) >= 53
                        and self._on_talker_alias_repeat_burst
                    ):
                        _dmrpkt_out = self._on_talker_alias_repeat_burst(
                            self._system, _slot, _stream_id, _dtype_vseq, _data[20:53],
                        )
                        _repeat_tail = b"".join([_data[15:20], _dmrpkt_out, _data[53:]])
                    _repeat_pkt = b"".join([_data[:11], _peer_id, _repeat_tail])
                    for _peer in self._iter_downlink_peers(_repeat_pkt):
                        if _peer != _peer_id:
                            self.send_peer(_peer, _repeat_pkt)
                # TG 4000: reset after REPEAT so peers see the packet (legacy order)
                if self._handle_tg4000_packet(
                    _peer_id, _slot, _int_dst_id, _call_type, _frame_type, _dtype_vseq,
                ):
                    return
                if _call_type == "group" and _frame_type == HBPF_DATA_SYNC and _dtype_vseq == HBPF_SLT_VHEAD:
                    logger.info(
                        "(%s) CALL RX peer %s src %s -> TG %s slot %s",
                        self._system, int_id(_peer_id), int_id(_rf_src), int_id(_dst_id), _slot,
                    )
                # Legacy parity (bridge_master.py:3270-3310, routerHBP.dmrd_received):
                # the HBP source path only writes per-slot state. The full LC is stored
                # in STATUS[_slot]['RX_LC'] (decoded from the voice-header LC), and
                # routing_use_cases.py:2080 reads exactly that. Never write STATUS[stream_id]
                # for HBP — that pattern is only legal for routerOBP (flat dict).
                dmrpkt = _data[20:53] if len(_data) >= 53 else b""
                _unit_data = is_unit_data_ingress(
                    _call_type, _dtype_vseq, _stream_id,
                    self.STATUS.get(_slot, {}).get("RX_STREAM_ID") if _slot in self.STATUS else None,
                )
                if _slot in self.STATUS and not _unit_data:
                    if _stream_id != self.STATUS[_slot].get("RX_STREAM_ID"):
                        self.STATUS[_slot]["RX_START"] = pkt_time
                        if _frame_type == HBPF_DATA_SYNC and _dtype_vseq == HBPF_SLT_VHEAD and len(dmrpkt) >= 33:
                            try:
                                decoded_slot = decode.voice_head_term(dmrpkt)
                                self.STATUS[_slot]["RX_LC"] = decoded_slot["LC"]
                            except Exception:
                                self.STATUS[_slot]["RX_LC"] = LC_OPT + _dst_id + _rf_src
                        else:
                            self.STATUS[_slot]["RX_LC"] = LC_OPT + _dst_id + _rf_src
                _accepted = False
                if self._dmrd_received:
                    _accepted = self._dmrd_received(
                        self._system, _peer_id, _rf_src, _dst_id, _seq, _slot,
                        _call_type, _frame_type, _dtype_vseq, _stream_id, _data,
                        ingress_pkt_time=pkt_time,
                    )
                _voice = self._CONFIG.get("VOICE", {})
                if _accepted and self._on_handle_recording and _voice.get("RECORDING_ENABLED") and int_id(_dst_id) == _voice.get("RECORDING_TG") and _slot == _voice.get("RECORDING_TIMESLOT", 2):
                    dmrpkt = _data[20:53] if len(_data) >= 53 else _data[20:]
                    self._on_handle_recording(dmrpkt, _frame_type, _dtype_vseq, _stream_id, pkt_time, _rf_src, _int_dst_id, _slot)
                if (
                    _call_type == "unit"
                    and _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VTERM
                    and 9991 <= _int_dst_id <= 9999
                    and self._on_play_file_request
                ):
                    reactor.callInThread(self._on_play_file_request, str(_int_dst_id), self._system)
                if (
                    _call_type in ("group", "vcsbk")
                    and _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VTERM
                    and _slot in self.STATUS
                    and self.STATUS[_slot].get("RX_TYPE") != HBPF_SLT_VTERM
                    and self._on_in_band_signalling
                ):
                    self._on_in_band_signalling(self._system, _slot, _dst_id, pkt_time)
                if (
                    _call_type in ("group", "vcsbk")
                    and _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VTERM
                    and self._on_talker_alias_stream_end
                ):
                    self._on_talker_alias_stream_end(self._system, _stream_id)
                # Legacy routerHBP: unit data (_data_call) does not mark slot RX busy.
                if _slot in self.STATUS and not _unit_data:
                    self.STATUS[_slot]["RX_PEER"] = _peer_id
                    self.STATUS[_slot]["RX_SEQ"] = _seq
                    self.STATUS[_slot]["RX_RFS"] = _rf_src
                    self.STATUS[_slot]["RX_TYPE"] = _dtype_vseq
                    self.STATUS[_slot]["RX_TGID"] = _dst_id
                    self.STATUS[_slot]["RX_TIME"] = pkt_time
                    self.STATUS[_slot]["RX_STREAM_ID"] = _stream_id

        elif _command == RPTL:
            _peer_id = _data[4:8]
            if len(self._peers) < self._config.get("MAX_PEERS", 1) or _peer_id in self._peers:
                if _peer_id == b"\xff\xff\xff\xff" or (
                    self._router
                    and self._router.acl_check(_peer_id, _global.get("REG_ACL", (True, [])))
                    and self._router.acl_check(_peer_id, self._config.get("REG_ACL", (True, [])))
                    and self.validate_id(_peer_id)
                ):
                    self._on_peer_disconnected(_peer_id)
                    self._peers[_peer_id] = {
                        "CONNECTION": "RPTL-RECEIVED",
                        "CONNECTED": time.time(),
                        "PINGS_RECEIVED": 0,
                        "LAST_PING": time.time(),
                        "SOCKADDR": _sockaddr,
                        "IP": _sockaddr[0],
                        "PORT": _sockaddr[1],
                        "SALT": randint(0, 0xFFFFFFFF),
                        "RADIO_ID": str(int_id(_peer_id)),
                        "CALLSIGN": "",
                        "RX_FREQ": "",
                        "TX_FREQ": "",
                        "TX_POWER": "",
                        "COLORCODE": "",
                        "LATITUDE": "",
                        "LONGITUDE": "",
                        "HEIGHT": "",
                        "LOCATION": "",
                        "DESCRIPTION": "",
                        "SLOTS": "",
                        "URL": "",
                        "SOFTWARE_ID": "",
                        "PACKAGE_ID": "",
                    }
                    if _peer_id == b"\xff\xff\xff\xff":
                        logger.info("(%s) Server Status Probe Logging in with Radio ID: %s, %s:%s", self._system, int_id(_peer_id), _sockaddr[0], _sockaddr[1])
                    else:
                        logger.info("(%s) Repeater Logging in with Radio ID: %s, %s:%s", self._system, int_id(_peer_id), _sockaddr[0], _sockaddr[1])
                    _salt_str = bytes_4(self._peers[_peer_id]["SALT"])
                    self.send_peer(_peer_id, b"".join([RPTACK, _salt_str]))
                    self._peers[_peer_id]["CONNECTION"] = "CHALLENGE_SENT"
                    logger.info("(%s) Sent Challenge Response to %s for login: %s", self._system, int_id(_peer_id), self._peers[_peer_id]["SALT"])
                else:
                    self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                    if self._config.get("PROXY_CONTROL"):
                        self.proxy_IPBlackList(_peer_id, _sockaddr)
                    logger.warning("(%s) Invalid Login from %s Radio ID: %s Denied by Registation ACL or not registered ID", self._system, _sockaddr[0], int_id(_peer_id))
                    if self._CONFIG.get("SYSTEMS", {}).get(self._system):
                        self._CONFIG["SYSTEMS"][self._system]["_reset"] = True
            else:
                self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                logger.warning("(%s) Registration denied from Radio ID: %s Maximum number of peers exceeded", self._system, int_id(_peer_id))

        elif _command == RPTK:
            _peer_id = _data[4:8]
            if _peer_id in self._peers and self._peers[_peer_id]["CONNECTION"] == "CHALLENGE_SENT" and self._peers[_peer_id]["SOCKADDR"] == _sockaddr:
                _this_peer = self._peers[_peer_id]
                _this_peer["LAST_PING"] = time.time()
                _sent_hash = _data[8:]
                _salt_str = bytes_4(_this_peer["SALT"])
                _radio_id_int = int_id(_peer_id)
                _individual_password = self._get_user_password(_radio_id_int)
                _passphrase = _get_passphrase_bytes(self._config)
                if _individual_password is not None:
                    _calc_hash_val = _calc_hash(_salt_str, _individual_password)
                    if _sent_hash == _calc_hash_val:
                        _this_peer["CONNECTION"] = "WAITING_CONFIG"
                        self.send_peer(_peer_id, b"".join([RPTACK, _peer_id]))
                        logger.info("(%s) Peer %s has completed the login exchange successfully (individual password)", self._system, _this_peer["RADIO_ID"])
                    else:
                        logger.warning("(%s) Peer %s has FAILED the login exchange (wrong individual password)", self._system, _this_peer["RADIO_ID"])
                        self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                        self._remove_peer(_peer_id)
                elif len(_passphrase) > 0:
                    _calc_hash_val = _calc_hash(_salt_str, _passphrase)
                    if _sent_hash == _calc_hash_val:
                        _this_peer["CONNECTION"] = "WAITING_CONFIG"
                        self.send_peer(_peer_id, b"".join([RPTACK, _peer_id]))
                        logger.info("(%s) Peer %s has completed the login exchange successfully (global passphrase)", self._system, _this_peer["RADIO_ID"])
                    else:
                        logger.warning("(%s) Peer %s has FAILED the login exchange (wrong global passphrase)", self._system, _this_peer["RADIO_ID"])
                        self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                        self._remove_peer(_peer_id)
                else:
                    logger.warning("(%s) Peer %s has FAILED - no individual password configured and no global passphrase", self._system, _this_peer["RADIO_ID"])
                    self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                    self._remove_peer(_peer_id)
            else:
                self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                logger.info("(%s) Login challenge from Radio ID that has not logged in: %s", self._system, int_id(_peer_id))

        elif _command == RPTC:
            if _data[:5] == RPTCL:
                _peer_id = _data[5:9]
                if _peer_id in self._peers and self._peers[_peer_id]["CONNECTION"] == "YES" and self._peers[_peer_id]["SOCKADDR"] == _sockaddr:
                    logger.info("(%s) Peer is closing down: %s (%s)", self._system, self._peers[_peer_id]["CALLSIGN"], int_id(_peer_id))
                    self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                    self._remove_peer(_peer_id)
                    sys_cfg = self._CONFIG.get("SYSTEMS", {}).get(self._system, {})
                    if "OPTIONS" in sys_cfg:
                        if "_default_options" in sys_cfg:
                            sys_cfg["OPTIONS"] = sys_cfg["_default_options"]
                            logger.info("(%s) Setting default Options: %s", self._system, sys_cfg["_default_options"])
                        else:
                            logger.info("(%s) Deleting HBP Options", self._system)
                            del sys_cfg["OPTIONS"]
                    sys_cfg["_reset"] = True
                    self._push_config_to_monitor()
            else:
                _peer_id = _data[4:8]
                if _peer_id in self._peers and self._peers[_peer_id]["CONNECTION"] == "WAITING_CONFIG" and self._peers[_peer_id]["SOCKADDR"] == _sockaddr:
                    _this_peer = self._peers[_peer_id]
                    _this_peer["CONNECTION"] = "YES"
                    _this_peer["CONNECTED"] = time.time()
                    _this_peer["LAST_PING"] = time.time()
                    _this_peer["CALLSIGN"] = _data[8:16]
                    _this_peer["RX_FREQ"] = _data[16:25]
                    _this_peer["TX_FREQ"] = _data[25:34]
                    _this_peer["TX_POWER"] = _data[34:36]
                    _this_peer["COLORCODE"] = _data[36:38]
                    _this_peer["LATITUDE"] = _data[38:46]
                    _this_peer["LONGITUDE"] = _data[46:55]
                    _this_peer["HEIGHT"] = _data[55:58]
                    _this_peer["LOCATION"] = _data[58:78]
                    _this_peer["DESCRIPTION"] = _data[78:97]
                    _this_peer["SLOTS"] = _data[97:98]
                    _this_peer["URL"] = _data[98:222]
                    _this_peer["SOFTWARE_ID"] = _data[222:262]
                    _this_peer["PACKAGE_ID"] = _data[262:302]
                    if ("ALLOW_UNREG_ID" in self._config and not self._config["ALLOW_UNREG_ID"]) and _this_peer["CALLSIGN"].decode("utf8", errors="replace").rstrip() != self.validate_id(_peer_id):
                        self._remove_peer(_peer_id)
                        if self._config.get("PROXY_CONTROL"):
                            self.proxy_IPBlackList(_peer_id, _sockaddr)
                        self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                        self._CONFIG.setdefault("SYSTEMS", {}).setdefault(self._system, {})["_reset"] = True
                        logger.info("(%s) Callsign does not match subscriber database: ID: %s, Sent Call: %s, DB call %s", self._system, int_id(_peer_id), _this_peer["CALLSIGN"].decode("utf8", errors="replace").rstrip(), self.validate_id(_peer_id))
                    else:
                        self.send_peer(_peer_id, b"".join([RPTACK, _peer_id]))
                        logger.info("(%s) Peer %s (%s) has sent repeater configuration, Package ID: %s, Software ID: %s, Desc: %s", self._system, _this_peer["CALLSIGN"], _this_peer["RADIO_ID"], self._peers[_peer_id]["PACKAGE_ID"].decode("utf8", errors="replace").rstrip(), self._peers[_peer_id]["SOFTWARE_ID"].decode("utf8", errors="replace").rstrip(), self._peers[_peer_id]["DESCRIPTION"].decode("utf8", errors="replace").rstrip())
                        self._refresh_connected_peer_count()
                        self._mark_downlink_index_dirty()
                        self._config_push_throttle.note_peer_connected()
                        self._push_config_to_monitor()
                else:
                    self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                    logger.info("(%s) Peer info from Radio ID that has not logged in: %s", self._system, int_id(_peer_id))

        elif _command == RPTO:
            _peer_id = _data[4:8]
            if _peer_id in self._peers and self._peers[_peer_id]["SOCKADDR"] == _sockaddr:
                _this_peer = self._peers[_peer_id]
                _this_peer["OPTIONS"] = _data[8:]
                invalidate_peer_options_cache(_this_peer)
                self._mark_downlink_index_dirty()
                self.send_peer(_peer_id, b"".join([RPTACK, _peer_id]))
                logger.info("(%s) Peer %s has sent options %s", self._system, _this_peer["CALLSIGN"], _this_peer["OPTIONS"])
                if is_proxy_inject_only(self._CONFIG, self._system):
                    for _slot in (1, 2):
                        if _slot in self.STATUS:
                            seed_peer_ua_session_from_status(
                                _this_peer,
                                _peer_id,
                                _slot,
                                self.STATUS[_slot],
                                self._config,
                            )
                # Inject-only multi-hotspot: OPTIONS live on each peer; do not let last RPTO
                # overwrite the shared SYSTEM row (legacy had one peer per virtual master).
                if not is_proxy_inject_only(self._CONFIG, self._system):
                    self._CONFIG.setdefault("SYSTEMS", {}).setdefault(self._system, {})[
                        "OPTIONS"
                    ] = _this_peer["OPTIONS"].decode("utf8", errors="replace")
                if self._on_options_received:
                    try:
                        self._on_options_received(self._system, _this_peer["OPTIONS"])
                    except Exception:
                        pass
                self._push_config_to_monitor()
            else:
                self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                logger.info("(%s) Options from Radio ID that is not logged: %s", self._system, int_id(_peer_id))

        elif _command == RPTP:
            _peer_id = _data[7:11]
            if _peer_id in self._peers and self._peers[_peer_id]["CONNECTION"] == "YES" and self._peers[_peer_id]["SOCKADDR"] == _sockaddr:
                self._peers[_peer_id]["PINGS_RECEIVED"] += 1
                self._peers[_peer_id]["LAST_PING"] = time.time()
                self.send_peer(_peer_id, b"".join([MSTPONG, _peer_id]))
                logger.log(logging.TRACE if hasattr(logging, "TRACE") else logging.DEBUG, "(%s) Received and answered RPTPING from peer %s (%s)", self._system, self._peers[_peer_id]["CALLSIGN"], int_id(_peer_id))
            else:
                self.transport.write(b"".join([MSTNAK, _peer_id]), _sockaddr)
                logger.info("(%s) Ping from Radio ID that is not logged in: %s", self._system, int_id(_peer_id))

        elif _command == DMRA:
            _peer_id = None
            for pid, peer in self._peers.items():
                if peer.get("SOCKADDR") == _sockaddr:
                    _peer_id = pid
                    break
            if _peer_id is not None and len(_data) >= DMRA_PACKET_LEN:
                if parse_dmra_packet(_data):
                    logger.debug("(%s) Peer has sent Talker Alias packet %s", self._system, _data)
                    self.store_dmra_packet(_peer_id, _data)
                else:
                    logger.debug(
                        "(%s) Peer DMRA ignored (MMDVM expects byte7=0-3, got %s); raw %s",
                        self._system,
                        _data[7],
                        _data,
                    )

        elif _command == PRIN:
            logger.info("(%s) *ProxyInfo* Connection from IP:Port: %s", self._system, _data.decode("utf8", errors="replace")[4:])

        else:
            logger.error("(%s) Unrecognized command. Raw HBP PDU: %s", self._system, _data)

    def _peer_update_sockaddr(self, ip: str) -> None:
        """Legacy updateSockaddr: update MASTER_IP and MASTER_SOCKADDR after DNS resolve."""
        self._config["MASTER_IP"] = ip
        self._config["MASTER_SOCKADDR"] = (ip, self._config["MASTER_PORT"])
        logger.info("(%s) hostname resolution performed: %s", self._system, ip)

    def _peer_update_sockaddr_errback(self, failure) -> None:
        logger.info("(%s) hostname resolution error: %s", self._system, failure)

    def _peer_maintenance_loop(self) -> None:
        """Legacy peer_maintenance_loop (hblink.py lines 757-780)."""
        _global = self._CONFIG.get("GLOBAL", {})
        max_missed = _global.get("MAX_MISSED", 3)
        if self._stats.get("PING_OUTSTANDING"):
            self._stats["NUM_OUTSTANDING"] = self._stats.get("NUM_OUTSTANDING", 0) + 1
        if self._stats.get("CONNECTION") != "YES" or self._stats.get("NUM_OUTSTANDING", 0) >= max_missed:
            self._stats["PINGS_SENT"] = 0
            self._stats["PINGS_ACKD"] = 0
            self._stats["NUM_OUTSTANDING"] = 0
            self._stats["PING_OUTSTANDING"] = False
            self._stats["CONNECTION"] = "RPTL_SENT"
            if self._stats.get("DNS_TIME", 0) < (time.time() - 600):
                self._stats["DNS_TIME"] = time.time()
                _master_ip = self._config.get("_MASTER_IP", "")
                if _master_ip:
                    d = reactor.resolve(_master_ip)
                    d.addCallback(self._peer_update_sockaddr)
                    d.addErrback(self._peer_update_sockaddr_errback)
            self.send_master(b"".join([RPTL, self._config["RADIO_ID"]]))
            logger.info("(%s) Sending login request to master %s:%s", self._system, self._config.get("MASTER_IP"), self._config.get("MASTER_PORT"))
        if self._stats.get("CONNECTION") == "YES":
            self.send_master(b"".join([RPTPING, self._config["RADIO_ID"]]))
            self._stats["PINGS_SENT"] = self._stats.get("PINGS_SENT", 0) + 1
            self._stats["PING_OUTSTANDING"] = True

    def _peer_datagram_received(self, _data: bytes, _sockaddr: tuple[str, int]) -> None:
        """Direct port of hblink.py peer_datagramReceived (lines 1149-1313)."""
        if self._config.get("MASTER_SOCKADDR") != _sockaddr:
            return
        _command = _data[:4]
        if _command == DMRD:
            _peer_id = _data[11:15]
            if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                _seq = _data[4]
                _rf_src = _data[5:8]
                _dst_id = _data[8:11]
                _bits = _data[15]
                _slot = 2 if (_bits & 0x80) else 1
                if _bits & 0x40:
                    _call_type = "unit"
                elif (_bits & 0x23) == 0x23:
                    _call_type = "vcsbk"
                else:
                    _call_type = "group"
                _frame_type = (_bits & 0x30) >> 4
                _dtype_vseq = _bits & 0xF
                _stream_id = _data[16:20]
                if not int_id(_stream_id):
                    logger.warning("(%s) CALL DROPPED AS STREAM ID IS NULL FROM SUBSCRIBER %s", self._system, int_id(_rf_src))
                    return
                pkt_time = time.time()
                _int_dst_id = int_id(_dst_id)
                _global = self._CONFIG.get("GLOBAL", {})
                if self._router and _global.get("USE_ACL"):
                    if not self._router.acl_check(_rf_src, _global.get("SUB_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY GLOBAL ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 1 and not self._router.acl_check(_dst_id, _global.get("TG1_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS1 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 2 and not self._router.acl_check(_dst_id, _global.get("TG2_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS2 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                if self._router and self._config.get("USE_ACL"):
                    if not self._router.acl_check(_rf_src, self._config.get("SUB_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY SYSTEM ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 1 and not self._router.acl_check(_dst_id, self._config.get("TG1_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY SYSTEM TS1 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                    if _slot == 2 and not self._router.acl_check(_dst_id, self._config.get("TG2_ACL", (True, []))):
                        if self._laststrid[_slot] != _stream_id:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY SYSTEM TS2 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._laststrid[_slot] = _stream_id
                        return
                # SUB_MAP update (legacy routerHBP.dmrd_received)
                sub_map = self._CONFIG.get("_SUB_MAP")
                if sub_map is not None:
                    sub_map[_rf_src] = (self._system, _slot, pkt_time)
                # TG 4000: reset after ACL/SUB_MAP (legacy order — routerHBP.dmrd_received)
                if self._handle_tg4000_packet(
                    _peer_id, _slot, _int_dst_id, _call_type, _frame_type, _dtype_vseq,
                ):
                    return
                if _call_type == "group" and _frame_type == HBPF_DATA_SYNC and _dtype_vseq == HBPF_SLT_VHEAD:
                    logger.info(
                        "(%s) CALL RX (from master) src %s -> TG %s slot %s",
                        self._system, int_id(_rf_src), int_id(_dst_id), _slot,
                    )
                # Legacy parity (bridge_master.py:3270-3310, routerHBP.dmrd_received):
                # PEER source path only writes per-slot state. Full LC stored in
                # STATUS[_slot]['RX_LC'] (decoded voice-header LC). routing_use_cases
                # reads STATUS[_slot]['RX_LC'] for HBP sources. Never write
                # STATUS[stream_id] for HBP — that pattern is only legal for routerOBP.
                dmrpkt = _data[20:53] if len(_data) >= 53 else b""
                _unit_data = is_unit_data_ingress(
                    _call_type, _dtype_vseq, _stream_id,
                    self.STATUS.get(_slot, {}).get("RX_STREAM_ID") if _slot in self.STATUS else None,
                )
                if _slot in self.STATUS and not _unit_data:
                    if _stream_id != self.STATUS[_slot].get("RX_STREAM_ID"):
                        self.STATUS[_slot]["RX_START"] = pkt_time
                        if _frame_type == HBPF_DATA_SYNC and _dtype_vseq == HBPF_SLT_VHEAD and len(dmrpkt) >= 33:
                            try:
                                decoded_slot = decode.voice_head_term(dmrpkt)
                                self.STATUS[_slot]["RX_LC"] = decoded_slot["LC"]
                            except Exception:
                                self.STATUS[_slot]["RX_LC"] = LC_OPT + _dst_id + _rf_src
                        else:
                            self.STATUS[_slot]["RX_LC"] = LC_OPT + _dst_id + _rf_src
                _accepted = False
                if self._dmrd_received:
                    _accepted = self._dmrd_received(
                        self._system, _peer_id, _rf_src, _dst_id, _seq, _slot,
                        _call_type, _frame_type, _dtype_vseq, _stream_id, _data,
                        ingress_pkt_time=pkt_time,
                    )
                _voice = self._CONFIG.get("VOICE", {})
                if _accepted and self._on_handle_recording and _voice.get("RECORDING_ENABLED") and int_id(_dst_id) == _voice.get("RECORDING_TG") and _slot == _voice.get("RECORDING_TIMESLOT", 2):
                    dmrpkt = _data[20:53] if len(_data) >= 53 else _data[20:]
                    self._on_handle_recording(dmrpkt, _frame_type, _dtype_vseq, _stream_id, pkt_time, _rf_src, _int_dst_id, _slot)
                if (
                    _call_type == "unit"
                    and _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VTERM
                    and 9991 <= _int_dst_id <= 9999
                    and self._on_play_file_request
                ):
                    reactor.callInThread(self._on_play_file_request, str(_int_dst_id), self._system)
                if (
                    _call_type in ("group", "vcsbk")
                    and
                    _frame_type == HBPF_DATA_SYNC
                    and _dtype_vseq == HBPF_SLT_VTERM
                    and _slot in self.STATUS
                    and self.STATUS[_slot].get("RX_TYPE") != HBPF_SLT_VTERM
                    and self._on_in_band_signalling
                ):
                    self._on_in_band_signalling(self._system, _slot, _dst_id, pkt_time)
                if _slot in self.STATUS and not _unit_data:
                    if _stream_id != self.STATUS[_slot].get("RX_STREAM_ID"):
                        self.STATUS[_slot]["RX_START"] = pkt_time
                    self.STATUS[_slot]["RX_PEER"] = _peer_id
                    self.STATUS[_slot]["RX_SEQ"] = _seq
                    self.STATUS[_slot]["RX_RFS"] = _rf_src
                    self.STATUS[_slot]["RX_TYPE"] = _dtype_vseq
                    self.STATUS[_slot]["RX_TGID"] = _dst_id
                    self.STATUS[_slot]["RX_TIME"] = pkt_time
                    self.STATUS[_slot]["RX_STREAM_ID"] = _stream_id

        elif _command == DMRA:
            if len(_data) >= DMRA_PACKET_LEN:
                parsed = parse_dmra_packet(_data)
                if parsed:
                    rf_src, block_id, payload = parsed
                    if block_id <= 3:
                        now = time.time()
                        entry = self._dmra_downlink.setdefault(
                            rf_src,
                            {"blocks": {}, "last": now},
                        )
                        entry["blocks"][block_id] = payload
                        entry["last"] = now
                logger.debug("(%s) Talker Alias from master (downlink)", self._system)

        elif _command == MSTN:
            _peer_id = _data[6:10]
            if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                logger.warning("(%s) MSTNAK Received. Resetting connection to the Master.", self._system)
                self._stats["CONNECTION"] = "NO"
                self._stats["CONNECTED"] = time.time()

        elif _command == RPTA:
            if self._stats.get("CONNECTION") == "RPTL_SENT":
                _login_int32 = _data[6:10]
                logger.info("(%s) Repeater Login ACK Received with 32bit ID: %s", self._system, int_id(_login_int32))
                _pass_hash = bhex(sha256(b"".join([_login_int32, self._config.get("PASSPHRASE", b"")])).hexdigest())
                self.send_master(b"".join([RPTK, self._config["RADIO_ID"], _pass_hash]))
                self._stats["CONNECTION"] = "AUTHENTICATED"
            elif self._stats.get("CONNECTION") == "AUTHENTICATED":
                _peer_id = _data[6:10]
                if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                    logger.info("(%s) Repeater Authentication Accepted", self._system)
                    _config_packet = b"".join([
                        self._config["RADIO_ID"],
                        self._config.get("CALLSIGN", b""),
                        self._config.get("RX_FREQ", b""),
                        self._config.get("TX_FREQ", b""),
                        self._config.get("TX_POWER", b""),
                        self._config.get("COLORCODE", b""),
                        self._config.get("LATITUDE", b""),
                        self._config.get("LONGITUDE", b""),
                        self._config.get("HEIGHT", b""),
                        self._config.get("LOCATION", b""),
                        self._config.get("DESCRIPTION", b""),
                        self._config.get("SLOTS", b""),
                        self._config.get("URL", b""),
                        self._config.get("SOFTWARE_ID", b""),
                        self._config.get("PACKAGE_ID", b""),
                    ])
                    self.send_master(b"".join([RPTC, _config_packet]))
                    self._stats["CONNECTION"] = "CONFIG-SENT"
                    logger.info("(%s) Repeater Configuration Sent", self._system)
                else:
                    self._stats["CONNECTION"] = "NO"
                    logger.error("(%s) Master ACK Contained wrong ID - Connection Reset", self._system)
            elif self._stats.get("CONNECTION") == "CONFIG-SENT":
                _peer_id = _data[6:10]
                if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                    logger.info("(%s) Repeater Configuration Accepted", self._system)
                    if self._config.get("OPTIONS"):
                        self.send_master(b"".join([RPTO, self._config["RADIO_ID"], self._config["OPTIONS"]]))
                        self._stats["CONNECTION"] = "OPTIONS-SENT"
                        logger.info("(%s) Sent options: (%s)", self._system, self._config["OPTIONS"])
                    else:
                        self._stats["CONNECTION"] = "YES"
                        self._stats["CONNECTED"] = time.time()
                        logger.info("(%s) Connection to Master Completed", self._system)
                else:
                    self._stats["CONNECTION"] = "NO"
                    logger.error("(%s) Master ACK Contained wrong ID - Connection Reset", self._system)
            elif self._stats.get("CONNECTION") == "OPTIONS-SENT":
                _peer_id = _data[6:10]
                if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                    logger.info("(%s) Repeater Options Accepted", self._system)
                    self._stats["CONNECTION"] = "YES"
                    self._stats["CONNECTED"] = time.time()
                    logger.info("(%s) Connection to Master Completed with options", self._system)
                else:
                    self._stats["CONNECTION"] = "NO"
                    logger.error("(%s) Master ACK Contained wrong ID - Connection Reset", self._system)

        elif _command == MSTP:
            _peer_id = _data[7:11]
            if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                self._stats["PING_OUTSTANDING"] = False
                self._stats["NUM_OUTSTANDING"] = 0
                self._stats["PINGS_ACKD"] = self._stats.get("PINGS_ACKD", 0) + 1

        elif _command == MSTC:
            _peer_id = _data[5:9]
            if self._config.get("LOOSE") or _peer_id == self._config.get("RADIO_ID"):
                self._stats["CONNECTION"] = "NO"
                logger.info("(%s) MSTCL Recieved", self._system)

        else:
            logger.error("(%s) Received an invalid command in packet: %s", self._system, _data.hex() if hasattr(_data, "hex") else _data)

    def _looping_err_handle(self, failure) -> None:
        """Legacy loopingErrHandle: log-only (hblink.py ~202/~720)."""
        logger.error("(%s) Unhandled error in timed loop.\n %s", self._system, failure)

    def _obp_send_bcka(self) -> None:
        """Legacy send_bcka: BCKA + HMAC-SHA1 to TARGET. Uses TARGET_SOCK (IP only; hostnames resolved at startup or on first peer packet)."""
        _addr = self._config.get("TARGET_SOCK")
        if _addr and _addr[0]:
            self.transport.write(build_bcka(_get_passphrase_bytes(self._config)), _addr)
        else:
            logger.debug("(%s) *BridgeControl* not sending KeepAlive, TARGET not currently known", self._system)

    def _obp_send_bcve(self) -> None:
        """Legacy send_bcve: BCVE + VER byte + HMAC-SHA1. Uses TARGET_SOCK (IP only)."""
        _addr = self._config.get("TARGET_SOCK")
        if self._config.get("ENHANCED_OBP") and _addr and _addr[0]:
            self.transport.write(build_bcve(VER, _get_passphrase_bytes(self._config)), _addr)
        else:
            logger.debug("(%s) *BridgeControl* not sending BCVE, TARGET not currently known", self._system)

    def _obp_sync_target_sock_from_peer(self, _sockaddr: tuple[str, int]) -> None:
        """If RELAX_CHECKS accepted traffic from a different IP:port than TARGET_SOCK, sync (same idea as BCKA).
        Ensures BCSQ and outbound DMR go to the peer address we actually receive from."""
        if self._config.get("MODE") != "OPENBRIDGE" or not self._config.get("RELAX_CHECKS"):
            return
        if not _sockaddr or not _sockaddr[0]:
            return
        cur = self._config.get("TARGET_SOCK")
        if cur == _sockaddr:
            return
        h, p = _sockaddr[0], int(_sockaddr[1])
        logger.info(
            "(%s) *BridgeControl* OBP peer address sync to %s:%s (RELAX_CHECKS; was %s:%s)",
            self._system,
            h,
            p,
            (cur[0] if cur and cur[0] else "?"),
            (cur[1] if cur and len(cur) > 1 else "?"),
        )
        self._config["TARGET_IP"] = h
        self._config["TARGET_PORT"] = p
        self._config["TARGET_SOCK"] = (h, p)

    def _obp_send_bcsq(self, _tgid: bytes, _stream_id: bytes) -> None:
        """Legacy send_bcsq: BCSQ + tgid + stream_id + HMAC-SHA1. Uses TARGET_SOCK (IP only)."""
        _addr = self._config.get("TARGET_SOCK")
        if not _addr or not _addr[0]:
            tip = self._config.get("TARGET_IP")
            tport = int(self._config.get("TARGET_PORT", 62044))
            if tip:
                _addr = (tip, tport)
                self._config["TARGET_SOCK"] = _addr
        if _addr and _addr[0]:
            self.transport.write(
                build_bcsq(_tgid, _stream_id, _get_passphrase_bytes(self._config)),
                _addr,
            )
        else:
            logger.warning(
                "(%s) *BridgeControl* BCSQ not sent: no TARGET_SOCK/TARGET_IP — peer cannot be quenched",
                self._system,
            )

    def _obp_datagram_received(self, _packet: bytes, _sockaddr: tuple[str, int]) -> None:
        """Port of hblink.py OPENBRIDGE.datagramReceived: DMRD v1 (53+HMAC), BCKA, BCVE."""
        if _packet[:3] == DMR and _packet[:4] == DMRD and len(_packet) >= 73:
            _data = _packet[:53]
            _stream_id = _data[16:20]
            if self._config.get("VER", 5) > 1:
                if _stream_id not in self._laststrid:
                    logger.warning("(%s) *ProtoControl* Version 1 protocol prohibited by PROTO_VER, Ver: %s", self._system, self._config.get("VER"))
                    self._laststrid.append(_stream_id)
                self._obp_send_bcve()
                return
            _ingress = self._try_decode_mesh_ingress(_packet)
            if _ingress is not None and _ingress.codec == "obp_v1" and (_sockaddr == self._config.get("TARGET_SOCK") or self._config.get("RELAX_CHECKS")):
                _data = _ingress.voice_frame
                self._obp_sync_target_sock_from_peer(_sockaddr)
                _peer_id = _data[11:15]
                if self._config.get("NETWORK_ID") != _peer_id:
                    if _stream_id not in self._laststrid:
                        logger.error("(%s) OpenBridge packet discarded because NETWORK_ID: %s Does not match sent Peer ID: %s", self._system, int_id(self._config.get("NETWORK_ID", b"")), int_id(_peer_id))
                        self._laststrid.append(_stream_id)
                    return
                _seq = _data[4]
                _rf_src = _data[5:8]
                _dst_id = _data[8:11]
                _bits = _data[15]
                _slot = 2 if (_bits & 0x80) else 1
                if _bits & 0x40:
                    _call_type = "unit"
                elif (_bits & 0x23) == 0x23:
                    _call_type = "vcsbk"
                else:
                    _call_type = "group"
                _frame_type = (_bits & 0x30) >> 4
                _dtype_vseq = _bits & 0xF
                if _slot != 1:
                    logger.error("(%s) OpenBridge packet discarded because it was not received on slot 1. SID: %s, TGID %s", self._system, int_id(_rf_src), int_id(_dst_id))
                    return
                if "STUN" in self._CONFIG:
                    if _stream_id not in self._laststrid:
                        logger.warning("(%s) Bridge STUNned, discarding", self._system)
                        self._laststrid.append(_stream_id)
                    return
                _int_dst_id = int_id(_dst_id)
                if _call_type != "unit":
                    if _int_dst_id <= 79 or (_int_dst_id >= 9990 and _int_dst_id <= 9999) or (_int_dst_id >= 92 and _int_dst_id <= 199) or _int_dst_id == 900999:
                        if _stream_id not in self._laststrid:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY GLOBAL TG FILTER", self._system, int_id(_stream_id), _int_dst_id)
                            self._obp_send_bcsq(_dst_id, _stream_id)
                            self._laststrid.append(_stream_id)
                        return
                _global = self._CONFIG.get("GLOBAL", {})
                if self._router and _global.get("USE_ACL"):
                    if not self._router.acl_check(_rf_src, _global.get("SUB_ACL", (True, []))):
                        if _stream_id not in self._laststrid:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS1 ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                            self._obp_send_bcsq(_dst_id, _stream_id)
                            self._laststrid.append(_stream_id)
                        return
                    if _slot == 1 and not self._router.acl_check(_dst_id, _global.get("TG1_ACL", (True, []))):
                        if _stream_id not in self._laststrid:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS1 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._obp_send_bcsq(_dst_id, _stream_id)
                            self._laststrid.append(_stream_id)
                        return
                if self._router and self._config.get("USE_ACL"):
                    if not self._router.acl_check(_rf_src, self._config.get("SUB_ACL", (True, []))):
                        if _stream_id not in self._laststrid:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY SYSTEM ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                            self._obp_send_bcsq(_dst_id, _stream_id)
                            self._laststrid.append(_stream_id)
                        return
                    if not self._router.acl_check(_dst_id, self._config.get("TG1_ACL", (True, []))):
                        if _stream_id not in self._laststrid:
                            logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY SYSTEM ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                            self._obp_send_bcsq(_dst_id, _stream_id)
                            self._laststrid.append(_stream_id)
                        return
                if _call_type == "group" and _frame_type == HBPF_DATA_SYNC and _dtype_vseq == HBPF_SLT_VHEAD:
                    logger.info(
                        "(%s) CALL RX (OBP) src %s -> TG %s slot %s",
                        self._system, int_id(_rf_src), int_id(_dst_id), _slot,
                    )
                self.note_dmrd_stream(_peer_id, _rf_src, _stream_id)
                if (
                    _call_type in ("group", "vcsbk")
                    and _frame_type != HBPF_DATA_SYNC
                    and _dtype_vseq in (1, 2, 3, 4)
                    and len(_data) >= 53
                ):
                    self.store_ta_from_voice_burst(
                        _peer_id, _rf_src, _stream_id, _dtype_vseq, _data[20:53],
                    )
                # Group/vcsbk stream state, LC, duplicates: routing_use_cases._obp_group_voice_router_obp (legacy routerOBP.dmrd_received)
                if self._dmrd_received:
                    # Legacy hblink DMRD v1: SERVER_ID + default rptr/hops/ber/rssi (`hblink.py` ~338–345, ~416)
                    _global = self._CONFIG.get("GLOBAL", {})
                    _sid = _global.get("SERVER_ID", b"\x00\x00\x00\x00")
                    _obp_ss = (
                        _sid
                        if isinstance(_sid, bytes) and len(_sid) >= 4
                        else bytes_4(int(_sid) & 0xFFFFFFFF if isinstance(_sid, int) else 0)
                    )
                    self._dmrd_received(
                        self._system,
                        _peer_id,
                        _rf_src,
                        _dst_id,
                        _seq,
                        _slot,
                        _call_type,
                        _frame_type,
                        _dtype_vseq,
                        _stream_id,
                        _data,
                        obp_use_parsed=True,
                        obp_hops=b"",
                        obp_source_server=_obp_ss,
                        obp_ber=b"\x00",
                        obp_rssi=b"\x00",
                        obp_source_rptr=b"\x00\x00\x00\x00",
                    )
                self._config["_bcka"] = time.time()
            else:
                logger.warning("(%s) OpenBridge HMAC failed, packet discarded - OPCODE: %s SRC: %s", self._system, _packet[:4], _sockaddr)
        elif _packet[:4] == DMRE:
            # Legacy hblink.py OPENBRIDGE: DMRE (v5) incoming – 89-byte or 85-byte format, BLAKE2b
            _ingress = self._try_decode_mesh_ingress(_packet)
            if _ingress is None or _ingress.codec != "dmre_v5":
                return
            if not (_sockaddr == self._config.get("TARGET_SOCK") or self._config.get("RELAX_CHECKS")):
                logger.warning("(%s) OpenBridge DMRE BLAKE2b failed, packet discarded - SRC: %s", self._system, _sockaddr)
                return
            _data = _ingress.voice_frame
            _ber = _ingress.ber
            _rssi = _ingress.rssi
            _embedded_version = _ingress.embedded_ver if _ingress.embedded_ver is not None else self._config.get("VER", 5)
            _source_server = _ingress.source_server
            _source_rptr = _ingress.source_rptr
            _hops = _ingress.hops
            _trailer = parse_dmre_trailer(_packet)
            _timestamp = _trailer.timestamp if _trailer is not None else b"\x00" * 8
            _stream_id = _data[16:20]
            self._obp_sync_target_sock_from_peer(_sockaddr)
            _peer_id = _data[11:15]
            if self._config.get("NETWORK_ID") != _peer_id:
                if _stream_id not in self._laststrid:
                    logger.error("(%s) OpenBridge DMRE discarded because NETWORK_ID: %s Does not match sent Peer ID: %s", self._system, int_id(self._config.get("NETWORK_ID", b"")), int_id(_peer_id))
                    self._laststrid.append(_stream_id)
                return
            _seq = _data[4]
            _rf_src = _data[5:8]
            _dst_id = _data[8:11]
            _int_dst_id = int_id(_dst_id)
            _bits = _data[15]
            _slot = 2 if (_bits & 0x80) else 1
            if self._config.get("MODE") == "OPENBRIDGE":
                # Legacy bridge_master: OpenBridge streams are effectively TS1 (DMRD v1 rejects slot != 1).
                # DMRE can still carry TS2 in bits; BRIDGES use TS:1 for OBP — normalize before STATUS/dmrd.
                _slot = 1
            if _bits & 0x40:
                _call_type = "unit"
            elif (_bits & 0x23) == 0x23:
                _call_type = "vcsbk"
            else:
                _call_type = "group"
            _frame_type = (_bits & 0x30) >> 4
            _dtype_vseq = _bits & 0xF
            if "STUN" in self._CONFIG:
                if _stream_id not in self._laststrid:
                    logger.warning("(%s) Bridge STUNned, discarding", self._system)
                    self._laststrid.append(_stream_id)
                return
            _ts_sec = int.from_bytes(_timestamp, "big") / 1_000_000_000
            if _ts_sec < (time.time() - 5):
                if _stream_id not in self._laststrid:
                    logger.warning("(%s) Packet from server %s more than 5s old!, discarding", self._system, int.from_bytes(_source_server, "big"))
                    self._obp_send_bcsq(_dst_id, _stream_id)
                    self._laststrid.append(_stream_id)
                return
            _src_srv_int = int.from_bytes(_source_server, "big")
            _src_srv_str = str(_src_srv_int)
            _src_srv_len = len(_src_srv_str)
            if _src_srv_len < 4 or _src_srv_len > 7:
                if _stream_id not in self._laststrid:
                    logger.warning("(%s) Source Server should be between 4 and 7 digits, discarding Src: %s", self._system, _src_srv_int)
                    self._obp_send_bcsq(_dst_id, _stream_id)
                    self._laststrid.append(_stream_id)
                return
            _global = self._CONFIG.get("GLOBAL", {})
            _server_ids = self._CONFIG.get("_SERVER_IDS", set())
            if _global.get("VALIDATE_SERVER_IDS") and _src_srv_len in (4, 5) and (_src_srv_str[:4] not in _server_ids):
                if _stream_id not in self._laststrid:
                    logger.warning("(%s) Source Server ID is 4 or 5 digits but not in list: %s", self._system, _src_srv_int)
                    self._obp_send_bcsq(_dst_id, _stream_id)
                    self._laststrid.append(_stream_id)
                return
            if _src_srv_len > 5 and not self.validate_id(_source_server):
                if _stream_id not in self._laststrid:
                    logger.warning("(%s) Source Server 6 or 7 digits but not a valid DMR ID, discarding Src: %s", self._system, _src_srv_int)
                    self._obp_send_bcsq(_dst_id, _stream_id)
                    self._laststrid.append(_stream_id)
                return
            _inthops = (_hops if isinstance(_hops, int) else int.from_bytes(_hops, "big")) + 1
            if _inthops > 10:
                logger.debug(
                    "(%s) MAX HOPS exceed, dropping. Hops: %s, DST: %s, SRC: %s",
                    self._system,
                    _inthops,
                    _int_dst_id,
                    _src_srv_int,
                )
                self._obp_send_bcsq(_dst_id, _stream_id)
                return
            if _call_type != "unit":
                if _int_dst_id <= 79:
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s BY GLOBAL TG FILTER (local to repeater)", self._system, int_id(_stream_id), _int_dst_id)
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
                if (_int_dst_id >= 9990 and _int_dst_id <= 9999) or _int_dst_id == 900999:
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s BY GLOBAL TG FILTER (local to server)", self._system, int_id(_stream_id), _int_dst_id)
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
                _sid = _global.get("SERVER_ID", 0)
                _our_srv = int(str(_sid)[:4]) if isinstance(_sid, int) else int(str(int.from_bytes(_sid, "big"))[:4])
                if (_int_dst_id >= 92 and _int_dst_id <= 199) and int(_src_srv_str[:4]) != _our_srv:
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s BY GLOBAL TG FILTER (local to server main ID)", self._system, int_id(_stream_id), _int_dst_id)
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
                if ((_int_dst_id >= 80 and _int_dst_id <= 89) or (_int_dst_id >= 800 and _int_dst_id <= 899)) and int(_src_srv_str[:3]) != int(str(_our_srv)[:3]):
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s BY GLOBAL TG FILTER (local to MCC)", self._system, int_id(_stream_id), _int_dst_id)
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
            if _global.get("USE_ACL") and self._router:
                if not self._router.acl_check(_rf_src, _global.get("SUB_ACL", (True, []))):
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS1 ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
                if _slot == 1 and not self._router.acl_check(_dst_id, _global.get("TG1_ACL", (True, []))):
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY GLOBAL TS1 ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
            if self._config.get("USE_ACL") and self._router:
                if not self._router.acl_check(_rf_src, self._config.get("SUB_ACL", (True, []))):
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s FROM SUBSCRIBER %s BY SYSTEM ACL", self._system, int_id(_stream_id), int_id(_rf_src))
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
                if not self._router.acl_check(_dst_id, self._config.get("TG1_ACL", (True, []))):
                    if _stream_id not in self._laststrid:
                        logger.info("(%s) CALL DROPPED WITH STREAM ID %s ON TGID %s BY SYSTEM ACL", self._system, int_id(_stream_id), int_id(_dst_id))
                        self._obp_send_bcsq(_dst_id, _stream_id)
                        self._laststrid.append(_stream_id)
                    return
            if _call_type == "group" and _frame_type == HBPF_DATA_SYNC and _dtype_vseq == HBPF_SLT_VHEAD:
                logger.info("(%s) CALL RX (OBP DMRE) src %s -> TG %s slot %s", self._system, int_id(_rf_src), int_id(_dst_id), _slot)
            self.note_dmrd_stream(_peer_id, _rf_src, _stream_id)
            if (
                _call_type in ("group", "vcsbk")
                and _frame_type != HBPF_DATA_SYNC
                and _dtype_vseq in (1, 2, 3, 4)
                and len(_data) >= 53
            ):
                self.store_ta_from_voice_burst(
                    _peer_id, _rf_src, _stream_id, _dtype_vseq, _data[20:53],
                )
            _data_dmrd = DMRD + _data[4:]
            _hops_out = _inthops.to_bytes(1, "big")
            if self._dmrd_received:
                # Legacy hblink DMRE: same fields passed to dmrd_received as after increment (`hblink.py` ~592–596)
                self._dmrd_received(
                    self._system,
                    _peer_id,
                    _rf_src,
                    _dst_id,
                    _seq,
                    _slot,
                    _call_type,
                    _frame_type,
                    _dtype_vseq,
                    _stream_id,
                    _data_dmrd,
                    obp_use_parsed=True,
                    obp_hops=_hops_out,
                    obp_source_server=_source_server,
                    obp_ber=_ber,
                    obp_rssi=_rssi,
                    obp_source_rptr=_source_rptr,
                )
            self._config["_bcka"] = time.time()
        elif _packet[:4] == EOBP:
            logger.warning("(%s) *ProtoControl* KF7EEL EOBP protocol not supported", self._system)
        elif self._config.get("ENHANCED_OBP") and _packet[:2] == BC:
            _passphrase = _get_passphrase_bytes(self._config)
            if _packet[:4] == BCKA and len(_packet) >= 24:
                if verify_bcka(_packet, _passphrase):
                    self._config["_bcka"] = time.time()
                    if _sockaddr != self._config.get("TARGET_SOCK"):
                        logger.info("(%s) *BridgeControl* Source IP and Port has changed for OBP from %s:%s to %s:%s, updating", self._system, self._config.get("TARGET_IP"), self._config.get("TARGET_PORT"), _sockaddr[0], _sockaddr[1])
                        self._config["TARGET_IP"] = _sockaddr[0]
                        self._config["TARGET_PORT"] = _sockaddr[1]
                        self._config["TARGET_SOCK"] = _sockaddr
                    self._config.pop("_no_target_log_time", None)  # reset so next "no target" logs once
                else:
                    logger.info("(%s) *BridgeControl* BCKA invalid KeepAlive, packet discarded", self._system)
            # Source quench — legacy hblink.py OPENBRIDGE ~629-639 (sets CONFIG['_bcsq'][tgid]=stream_id)
            if _packet[:4] == BCSQ and len(_packet) >= 31:
                _bcsq = verify_bcsq(_packet, _passphrase)
                if _bcsq is not None:
                    _tgid_bcsq = _bcsq.tgid
                    _stream_bcsq = _bcsq.stream_id
                    if "_bcsq" not in self._config:
                        self._config["_bcsq"] = {}
                    self._config["_bcsq"][_tgid_bcsq] = _stream_bcsq
                    if self._config.get("MODE") == "OPENBRIDGE":
                        _key = (_stream_bcsq, _tgid_bcsq)
                        _once = getattr(self, "_bcsq_log_once", None)
                        if isinstance(_once, deque) and _key not in _once:
                            _once.append(_key)
                            logger.info(
                                "(%s) *BridgeControl* BCSQ accepted: stream_id=%s TGID=%s (peer quenched; forwarding on this OBP stops for this stream/TG)",
                                self._system,
                                int_id(_stream_bcsq),
                                int_id(_tgid_bcsq),
                            )
                        cb = self._on_obp_bcsq_received
                        if cb is not None:
                            try:
                                cb(self._system, _tgid_bcsq, _stream_bcsq)
                            except Exception:
                                logger.exception("(%s) on_obp_bcsq_received failed", self._system)
                else:
                    logger.warning(
                        "(%s) *BridgeControl* BCSQ invalid Source Quench, packet discarded - SRC: %s",
                        self._system,
                        _sockaddr,
                    )
            # STUN — must match send_bcst: HMAC-SHA1 over opcode only (hblink.py ~282-285). RX used _packet[4:] in ~647 but that does not match TX.
            if _packet[:4] == BCST and len(_packet) >= 24:
                if verify_bcst(_packet, _passphrase):
                    logger.trace("(%s) *BridgeControl* BCST STUN request received", self._system)
                    self._config["_STUN"] = True
                else:
                    logger.warning(
                        "(%s) *BridgeControl* BCST invalid STUN, packet discarded - SRC: %s",
                        self._system,
                        _sockaddr,
                    )
            if _packet[:4] == BCVE and len(_packet) >= 25:
                _bcve_ok, _ver = verify_bcve(_packet, _passphrase)
                if _bcve_ok and _ver is not None:
                    if _ver in (2, 3) or _ver > 5:
                        logger.info("(%s) *ProtoControl* BCVE Version not supported, Ver: %s", self._system, _ver)
                    elif _ver > self._config.get("VER", 5):
                        logger.info("(%s) *ProtoControl* BCVE Version upgrade, Ver: %s", self._system, _ver)
                        self._config["VER"] = _ver
                    elif _ver == self._config.get("VER", 5):
                        pass
                    else:
                        logger.warning("(%s) *ProtoControl* BCVE Version downgrade not allowed, Ver: %s", self._system, _ver)
                else:
                    logger.warning("(%s) *ProtoControl* BCVE invalid, packet discarded", self._system)


def HBPProtocolFactory(
    system_name: str,
    config: dict[str, Any],
    report_factory: Any = None,
    router: Any = None,
    dmrd_received: Callable[..., None] | None = None,
    get_user_password_callback: Callable[[int], bytes | None] | None = None,
    on_play_file_request: Callable[[str, str], None] | None = None,
    on_handle_recording: Callable[..., None] | None = None,
    on_in_band_signalling: Callable[[str, int, bytes, float], None] | None = None,
    on_options_received: Callable[..., None] | None = None,
    on_deactivate_dynamic_relays: Callable[[str], None] | None = None,
    on_obp_bcsq_received: Callable[[str, bytes, bytes], None] | None = None,
    on_talker_alias_local_repeat: Callable[[str, bytes, bytes, bytes], None] | None = None,
    on_talker_alias_repeat_prepare: Callable[[str, bytes, bytes, bytes, int, bytes], None] | None = None,
    on_talker_alias_repeat_burst: Callable[[str, int, bytes, int, bytes], bytes] | None = None,
    on_talker_alias_stream_end: Callable[[str, bytes], None] | None = None,
    on_dmra_fragment_stored: Callable[[str, bytes, bytes, bytes], None] | None = None,
    routing_table_for_report: Callable[[], dict[str, Any]] | None = None,
    get_subscription_store: Callable[[], Any] | None = None,
    mesh_registry: MeshCodecRegistry | None = None,
) -> HBPProtocol:
    """Create HBP protocol instance (legacy: one HBSYSTEM per system)."""
    return HBPProtocol(
        system_name,
        config,
        report_factory,
        router,
        dmrd_received,
        get_user_password_callback=get_user_password_callback,
        on_play_file_request=on_play_file_request,
        on_handle_recording=on_handle_recording,
        on_in_band_signalling=on_in_band_signalling,
        on_options_received=on_options_received,
        on_deactivate_dynamic_relays=on_deactivate_dynamic_relays,
        on_obp_bcsq_received=on_obp_bcsq_received,
        on_talker_alias_local_repeat=on_talker_alias_local_repeat,
        on_talker_alias_repeat_prepare=on_talker_alias_repeat_prepare,
        on_talker_alias_repeat_burst=on_talker_alias_repeat_burst,
        on_talker_alias_stream_end=on_talker_alias_stream_end,
        on_dmra_fragment_stored=on_dmra_fragment_stored,
        routing_table_for_report=routing_table_for_report,
        get_subscription_store=get_subscription_store,
        mesh_registry=mesh_registry,
    )
