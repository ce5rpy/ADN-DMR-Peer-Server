# ADN DMR Peer Server - bridge use cases
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

"""Conference bridge facade: dmrd_received and unit/private paths.

Routing helpers live in application/bridge/ (timers, OBP/HBP forward, LC/TA, BRIDGES table).
"""

from __future__ import annotations

import logging
import time
from time import perf_counter
from typing import Any

from .reporting_use_cases import ReportingUseCases

from bitarray import bitarray
from ..domain.dmr import bptc

from ..domain import HBPF_DATA_SYNC, HBPF_SLT_VHEAD, HBPF_SLT_VTERM, STREAM_TO, bytes_3, bytes_4, int_id
from .ports import BridgeRouter, DmrEmbeddedLcEncoder, SubscriptionStore, TalkerAliasEmblcEncoder
from .talker_alias_use_cases import TalkerAliasUseCases
from .bridge.helpers import obp_target_bcsq_quenches_stream, resolve_voice_peer_id
from .bridge.timers import BridgeTimerMixin
from .bridge.obp_forward import BridgeObpForwardMixin
from .bridge.hbp_forward import BridgeHbpForwardMixin
from .bridge.lc_ta import BridgeLcTaMixin
from .bridge.bridge_table import BridgeTableMixin
from .bridge.store_authority_mixin import StoreAuthorityMixin
from .bridge.voice_subscription import VoiceSubscriptionMixin

logger = logging.getLogger(__name__)


class BridgeUseCases(
    BridgeTimerMixin,
    BridgeObpForwardMixin,
    BridgeHbpForwardMixin,
    BridgeLcTaMixin,
    BridgeTableMixin,
    StoreAuthorityMixin,
    VoiceSubscriptionMixin,
):
    """Use cases for conference bridge state (BRIDGES)."""

    def __init__(
        self,
        bridge_router: BridgeRouter,
        config: dict[str, Any],
        send_to_system: Any = None,
        get_protocols: Any = None,
        reporting: ReportingUseCases | None = None,
        on_bridge_deactivated: Any = None,
        send_bcsq: Any = None,
        send_dmra_to_system: Any = None,
        get_dmra_blocks: Any = None,
        call_later: Any = None,
        encode_emblc: DmrEmbeddedLcEncoder | None = None,
        ta_emblc_encoder: TalkerAliasEmblcEncoder | None = None,
        subscription_store: SubscriptionStore | None = None,
    ) -> None:
        self._router = bridge_router
        self._config = config
        self._subscription_store = subscription_store
        self._subscription_router = None
        self._bridges_legacy_view = None
        self._send_to_system = send_to_system  # (system_name, packet, **kwargs) -> None
        self._get_protocols = get_protocols  # () -> dict[str, protocol]
        self._reporting = reporting
        self._on_bridge_deactivated = on_bridge_deactivated  # (system_name: str) -> None; legacy disconnectedVoice
        self._send_bcsq = send_bcsq  # (system_name, tgid, stream_id) -> None; legacy OBP send_bcsq from router
        self._send_dmra_to_system = send_dmra_to_system
        self._get_dmra_blocks = get_dmra_blocks
        self._call_later = call_later
        if encode_emblc is None or ta_emblc_encoder is None:
            raise TypeError("encode_emblc and ta_emblc_encoder are required (wire from main.py)")
        self._encode_emblc = encode_emblc
        self._talker_alias = TalkerAliasUseCases(config, ta_emblc_encoder=ta_emblc_encoder)
        # (source_system, stream_id) -> {rf_src, peer, targets, timer}
        self._both_ta_wait: dict[tuple[str, bytes], dict[str, Any]] = {}
        # Passthrough DMRA/embed relay already applied for this source stream.
        self._passthrough_relayed: set[tuple[str, bytes]] = set()

    def _send_bridge_event(self, event: str | bytes) -> bool:
        """Send BRDG_EVENT via ReportingUseCases when REPORT is enabled."""
        if not self._config.get("REPORTS", {}).get("REPORT", True):
            return False
        if not self._reporting:
            return False
        if isinstance(event, bytes):
            event = event.decode("utf-8", "ignore")
        try:
            self._reporting.send_bridge_event(event)
            return True
        except Exception:
            return False

    def _send_bridge_snapshot(self, *, incremental: bool = True) -> None:
        """Push BRIDGES / routing_table to report clients (monitor SINGLE_TS chips)."""
        if not self._config.get("REPORTS", {}).get("REPORT", True):
            return
        if not self._reporting:
            return
        try:
            self._reporting.send_bridge(self._bridges_for_report(), incremental=incremental)
        except Exception:
            pass

    def _sync_subscription_store(self) -> None:
        """Mirror BRIDGES into the subscription store after OPTIONS/static mutations."""
        self._finalize_bridges_state()

    def get_bridges(self) -> dict[str, list[dict[str, Any]]]:
        """Return current BRIDGES (export shim when store authority is enabled)."""
        return self._bridges_for_report()

    def acl_check(self, id_val: bytes | int, acl: tuple[bool, list[tuple[int, int]]]) -> bool:
        """Check ID against ACL. Legacy acl_check."""
        return self._router.acl_check(id_val, acl)


    def dmrd_received(
        self,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        seq: int,
        slot: int,
        call_type: str,
        frame_type: int,
        dtype_vseq: int,
        stream_id: bytes,
        data: bytes,
        *,
        ingress_pkt_time: float | None = None,
        obp_use_parsed: bool = False,
        obp_hops: bytes = b"",
        obp_source_server: bytes | None = None,
        obp_ber: bytes = b"\x00",
        obp_rssi: bytes = b"\x00",
        obp_source_rptr: bytes = b"\x00\x00\x00\x00",
    ) -> bool:
        """Called by UDP when DMRD is received. Forward to other systems in same bridge (to_target).

        Returns True if the packet was accepted (passed ingress controls), False/None if dropped.
        Legacy `hblink.dmrd_received` passes `_hash,_hops,_source_server,_ber,_rssi,_source_rptr` after
        parsing OPENBRIDGE DMRD v1 / DMRE (`hblink.py` ~309–416, ~592–596). When `obp_use_parsed` is True,
        the OBP path uses those values (1:1 with `bridge.py` `routerOBP.dmrd_received` → `send_system`).
        HBP sources should pass ``ingress_pkt_time`` from UDP receive (legacy single ``pkt_time`` at router entry).
        """
        if not self._send_to_system:
            return
        # Legacy routerHBP.dmrd_received ~3015-3020: log once on first packet after _reset.
        # Only applies to HBP sources (routerOBP has no _reset gate).
        sys_cfg = self._config.get("SYSTEMS", {}).get(system_name, {})
        if sys_cfg.get("MODE") != "OPENBRIDGE" and sys_cfg.get("_reset") and not sys_cfg.get("_resetlog"):
            logger.info("(%s) disallow transmission until reset cycle is complete", system_name)
            sys_cfg["_resetlog"] = True
            return
        # Legacy bridge_master 3080–3085: private call to ID 4000 only disconnects dynamics; do not route as PC.
        if call_type == "unit" and int_id(dst_id) == 4000:
            return
        if call_type == "unit":
            if dtype_vseq in (6, 7, 8) or (dtype_vseq == 3 and not self._is_stream_known(system_name, stream_id, slot)):
                self._unit_data_received(
                    system_name, peer_id, rf_src, dst_id, seq, slot,
                    frame_type, dtype_vseq, stream_id, data,
                    obp_use_parsed=obp_use_parsed, obp_hops=obp_hops,
                    obp_source_server=obp_source_server,
                    obp_ber=obp_ber, obp_rssi=obp_rssi, obp_source_rptr=obp_source_rptr,
                )
            elif len(str(int_id(dst_id))) == 7:
                self._pvt_call_received(system_name, peer_id, rf_src, dst_id, seq, slot, frame_type, dtype_vseq, stream_id, data)
            return True
        systems_cfg = self._config.get("SYSTEMS", {})
        source_is_obp = systems_cfg.get(system_name, {}).get("MODE") == "OPENBRIDGE"
        pkt_time = ingress_pkt_time if ingress_pkt_time is not None else time.time()
        if not source_is_obp and call_type in ("group", "vcsbk"):
            if not self._hbp_group_voice_ingress_controls(
                system_name, peer_id, rf_src, dst_id, seq, slot, stream_id, data, pkt_time,
            ):
                return
        bridge_key = str(int_id(dst_id))
        bridges = self._router.get_bridges()
        dst_int = int_id(dst_id)
        # Legacy bridge_master to_target: OpenBridge clears TS bit — "all OpenBridge streams are
        # effectively on TS1". DMRD v1 rejects slot != 1; DMRE v5 can still set slot 2 from bits.
        # BRIDGES entries for OBP use TS:1 (make_single_bridge / make_stat_bridge). Match that.
        bridge_match_slot = 1 if source_is_obp else slot
        if bridge_key not in bridges:
            if dst_int < 5 or dst_int == 9 or dst_int == 4000 or dst_int == 5000:
                logger.debug(
                    "(ROUTER) No bridge for TG %s (excluded TGID), not creating",
                    dst_int,
                )
            elif source_is_obp and self._config.get("GLOBAL", {}).get("GEN_STAT_BRIDGES"):
                logger.debug("(%s) Bridge for STAT TG %s does not exist. Creating", system_name, dst_int)
                self.make_stat_bridge(dst_id)
                self.apply_static_tg_to_bridge(dst_int)
                bridges = self._router.get_bridges()
            else:
                tmout = self._ua_timer_minutes_for_peer(system_name, peer_id)
                logger.info(
                    "(%s) Bridge for TG %s does not exist. Creating as User Activated. Timeout %s",
                    system_name, dst_int, tmout,
                )
                self.make_single_bridge(dst_id, system_name, slot, float(tmout))
                self.apply_static_tg_to_bridge(dst_int)
                self._send_bridge_snapshot(incremental=True)
                bridges = self._router.get_bridges()
        # Legacy bridge_master routerOBP ~2413-2418: scan every BRIDGES[_bridge] table; forward only within
        # a table that contains a matching ACTIVE source row (not a flat merge of TG + #TG only).
        dst_id_b = dst_id if isinstance(dst_id, bytes) and len(dst_id) >= 3 else bytes_3(dst_int)

        if source_is_obp:
            self._ensure_obp_source_for_tg(system_name, bridge_key, dst_id_b, dst_int)
            bridges = self._router.get_bridges()
        if source_is_obp and call_type in ("group", "vcsbk"):
            if not self._obp_group_voice_router_obp(
                system_name,
                peer_id,
                rf_src,
                dst_id,
                seq,
                slot,
                call_type,
                frame_type,
                dtype_vseq,
                stream_id,
                data,
                obp_hops if obp_use_parsed else b"",
            ):
                return
        has_source = bool(
            self._voice_bridge_tables_with_active_source(system_name, bridge_match_slot, dst_int)
        )
        if not has_source and systems_cfg.get(system_name, {}).get("MODE") == "MASTER":
            self.options_config_for_system(system_name)
            bridges = self._router.get_bridges()
            has_source = bool(
                self._voice_bridge_tables_with_active_source(system_name, bridge_match_slot, dst_int)
            )
        # Do not call make_single_bridge here for 9990–9999 when BRIDGES["9990"] already exists:
        # make_single_bridge replaces the whole table and only sets the source MASTER ACTIVE; every
        # other system (including ECHO with TO_TYPE NONE) becomes ACTIVE False — to_target then has
        # no active target for the parrot path (legacy _make_echo_bridges / make_bridges keeps ECHO
        # ACTIVE True; activation of the source row is via in-band ON on VTERM, bridge_master ~3465).
        if not has_source:
            logger.debug(
                "(ROUTER) No matching source rule for TG %s from %s slot %s (ACTIVE), not forwarding",
                bridge_key, system_name, bridge_match_slot,
            )
            return True

        # Legacy bridge.py: BRDG_EVENT (OBP group/vcsbk START/END handled in _obp_group_voice_router_obp / post-forward VTERM)
        _obp_grp = source_is_obp and call_type in ("group", "vcsbk")
        if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
            if not _obp_grp:
                _rx_report_peer = peer_id
                if not source_is_obp:
                    _rx_report_peer = resolve_voice_peer_id(
                        peer_id,
                        rf_src,
                        system_name,
                        systems_cfg,
                    )
                self._send_bridge_event(
                    "GROUP VOICE,START,RX,{},{},{},{},{},{}".format(
                        system_name,
                        int_id(stream_id),
                        int_id(_rx_report_peer),
                        int_id(rf_src),
                        slot,
                        int_id(dst_id),
                    )
                )
        elif frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM:
            if not _obp_grp:
                duration = 0.0
                protocols = self._get_protocols() if self._get_protocols else {}
                src_proto = protocols.get(system_name) if protocols else None
                if src_proto and getattr(src_proto, "STATUS", None):
                    st = src_proto.STATUS
                    ent = st.get(stream_id)
                    start = ent.get("START") if isinstance(ent, dict) else None
                    if start is None and slot in st:
                        start = st.get(slot, {}).get("RX_START")
                    if start is not None:
                        duration = pkt_time - start
                _rx_report_peer = peer_id
                if not source_is_obp:
                    _rx_report_peer = resolve_voice_peer_id(
                        peer_id,
                        rf_src,
                        system_name,
                        systems_cfg,
                    )
                self._send_bridge_event(
                    "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                        system_name,
                        int_id(stream_id),
                        int_id(_rx_report_peer),
                        int_id(rf_src),
                        slot,
                        int_id(dst_id),
                        duration,
                    )
                )
        # ── Exact port of legacy bridge.py routerOBP/routerHBP forwarding to targets ──
        pkt_time = time.time()
        dmrpkt = data[20:53] if len(data) >= 53 else b""
        _bits = data[15] if len(data) > 15 else 0
        protocols = self._get_protocols() if self._get_protocols else {}
        src_proto = protocols.get(system_name) if protocols else None
        # Legacy `bridge.py` `routerOBP.dmrd_received` forwards `_hops,_ber,_rssi,_source_server,_source_rptr`
        # exactly as received from `hblink` (`bridge.py` ~486). Values are set in `hblink`:
        # - DMRD v1 OBP: SERVER_ID, zeros rptr, empty hops (`hblink.py` ~338–345)
        # - DMRE v5: packet fields + incremented hops (`hblink.py` ~592–596)
        # Legacy `bridge_master` `routerHBP.dmrd_received`: ber/rssi from payload, SERVER_ID + peer as rptr (~2936–2940).
        if source_is_obp and obp_use_parsed:
            _hops = obp_hops
            _ber = obp_ber
            _rssi = obp_rssi
            _sid = self._config.get("GLOBAL", {}).get("SERVER_ID")
            if obp_source_server is not None:
                _source_server = obp_source_server
            elif isinstance(_sid, bytes) and len(_sid) >= 4:
                _source_server = _sid
            elif _sid is not None:
                _source_server = bytes_4(int(_sid) & 0xFFFFFFFF)
            else:
                _source_server = b"\x00\x00\x00\x00"
            _source_rptr = obp_source_rptr
        elif source_is_obp:
            _ber = b"\x00"
            _rssi = b"\x00"
            _hops = b""
            _sid = self._config.get("GLOBAL", {}).get("SERVER_ID")
            if isinstance(_sid, bytes) and len(_sid) >= 4:
                _source_server = _sid
            elif _sid is not None:
                _source_server = bytes_4(int(_sid) & 0xFFFFFFFF)
            else:
                _source_server = b"\x00\x00\x00\x00"
            _source_rptr = b"\x00\x00\x00\x00"
        else:
            _ber = data[53:54] if len(data) > 53 else b"\x00"
            _rssi = data[54:55] if len(data) > 54 else b"\x00"
            _hops = b""
            _sid = self._config.get("GLOBAL", {}).get("SERVER_ID")
            if isinstance(_sid, bytes) and len(_sid) >= 4:
                _source_server = _sid
            elif _sid is not None:
                _source_server = bytes_4(int(_sid) & 0xFFFFFFFF)
            else:
                _source_server = b"\x00\x00\x00\x00"
            _source_rptr = peer_id
        # Legacy: source LC — routerOBP uses self.STATUS[_stream_id]['LC'], routerHBP uses self.STATUS[_slot]['RX_LC']
        source_lc = None
        if src_proto and getattr(src_proto, "STATUS", None):
            st = src_proto.STATUS
            if source_is_obp:
                ent = st.get(stream_id)
                source_lc = ent.get("LC") if isinstance(ent, dict) else None
            else:
                source_lc = st.get(slot, {}).get("RX_LC")
        if not source_lc or len(source_lc) < 9:
            source_lc = b"\x00\x00\x20" + dst_id_b + rf_src
        # Legacy bridge_master routerOBP: _sysIgnore accumulates across each to_target(BRIDGES[_bridge])
        # pass; dedupe (SYSTEM, TS) for OpenBridge targets so the same leg is not sent twice per packet.
        # SubscriptionRouter.resolve() already applies OBP dedup — skip sys_ignore_obp when using leg filter.
        forward_tables, forward_leg_key_set = self._voice_forward_plan(
            system_name=system_name,
            peer_id=peer_id,
            rf_src=rf_src,
            dst_id=dst_id,
            slot=slot,
            call_type=call_type,
            stream_id=stream_id,
            source_is_obp=source_is_obp,
            bridge_match_slot=bridge_match_slot,
            dst_int=dst_int,
        )
        use_subscription_legs = forward_leg_key_set is not None
        sys_ignore_obp: set[tuple[str, int]] = set()
        forwarded = []
        for _bridge_table_name in forward_tables:
            # Legacy: routerOBP/routerHBP to_target — if BRIDGES[_bridge] was removed mid-routing, skip
            if _bridge_table_name not in bridges:
                continue
            _bridge_rows = bridges[_bridge_table_name]
            for entry in _bridge_rows:
                if entry.get("SYSTEM") == system_name:
                    continue
                if not entry.get("ACTIVE", False):
                    continue
                if forward_leg_key_set is not None:
                    entry_key = (
                        entry["SYSTEM"],
                        int(entry.get("TS") or 1),
                        int_id(entry.get("TGID") or b"\x00\x00\x00"),
                    )
                    if entry_key not in forward_leg_key_set:
                        continue
                if not systems_cfg.get(entry["SYSTEM"], {}).get("ENABLED", True):
                    continue
                _target_system = systems_cfg.get(entry["SYSTEM"], {})
                target_mode = _target_system.get("MODE")
                tgt_proto = protocols.get(entry["SYSTEM"]) if protocols else None
                _target_status = getattr(tgt_proto, "STATUS", None) if tgt_proto else None

                if target_mode == "OPENBRIDGE":
                    # ── bridge_master.routerOBP.to_target OPENBRIDGE branch (~1850-1959) ──
                    entry_ts_obp = entry.get("TS")
                    if entry_ts_obp is None:
                        entry_ts_obp = 1
                    if not use_subscription_legs:
                        _obp_key = (entry["SYSTEM"], int(entry_ts_obp))
                        if _obp_key in sys_ignore_obp:
                            continue
                        sys_ignore_obp.add(_obp_key)
                    target_tgid = entry.get("TGID")
                    if isinstance(target_tgid, int):
                        target_tgid = bytes_3(target_tgid)
                    # If target has quenched us, don't send (~1856-1859).
                    if obp_target_bcsq_quenches_stream(systems_cfg, entry["SYSTEM"], dst_id_b, stream_id):
                        continue
                    # If target has missed keepalives (ENHANCED_OBP), don't send (~1861-1863)
                    if _target_system.get("ENHANCED_OBP") and (
                        "_bcka" not in _target_system or _target_system["_bcka"] < pkt_time - 60
                    ):
                        continue
                    # Talkgroup ACL (global + per-system TG1) (~1865-1873)
                    _global_cfg = self._config.get("GLOBAL", {})
                    if _global_cfg.get("USE_ACL"):
                        if not self.acl_check(target_tgid, _global_cfg.get("TG1_ACL", (True, []))):
                            continue
                        if not self.acl_check(target_tgid, _target_system.get("TG1_ACL", (True, []))):
                            continue
                    if _target_status is not None:
                        if stream_id not in _target_status:
                            _target_status[stream_id] = {
                                "START": pkt_time,
                                "CONTENTION": False,
                                "RFS": rf_src,
                                "TGID": dst_id_b,
                                "RX_PEER": peer_id,
                                "EMB_LC": {1: b"\x00", 2: b"\x00", 3: b"\x00", 4: b"\x00"},
                                "H_LC": b"\x00",
                                "T_LC": b"\x00",
                            }
                            try:
                                dst_lc = source_lc[0:3] + target_tgid + rf_src
                            except Exception:
                                logger.exception("(to_target) caught exception")
                                _target_status[stream_id]["LAST"] = pkt_time
                                return
                            _target_status[stream_id]["H_LC"] = bptc.encode_header_lc(dst_lc)
                            _target_status[stream_id]["T_LC"] = bptc.encode_terminator_lc(dst_lc)
                            _target_status[stream_id]["EMB_LC"] = self._encode_emblc(dst_lc)
                            self._init_talker_alias_embed(
                                _target_status[stream_id],
                                system_name,
                                entry["SYSTEM"],
                                rf_src,
                                stream_id,
                            )
                            logger.debug(
                                "(%s) Conference Bridge: %s, Call Bridged to OBP System: %s TS: %s, TGID: %s",
                                system_name, _bridge_table_name, entry["SYSTEM"], entry.get("TS", 1), int_id(target_tgid),
                            )
                            self._send_bridge_event(
                                "GROUP VOICE,START,TX,{},{},{},{},{},{}".format(
                                    entry["SYSTEM"], int_id(stream_id), int_id(peer_id), int_id(rf_src), entry.get("TS", 1), int_id(target_tgid)
                                )
                            )
                        if "EMB_LC" not in _target_status[stream_id]:
                            try:
                                dst_lc = source_lc[0:3] + target_tgid + rf_src
                                _target_status[stream_id]["EMB_LC"] = self._encode_emblc(dst_lc)
                            except Exception:
                                logger.exception("(to_target) caught exception while creating EMB_LC")
                                return
                        if "H_LC" not in _target_status[stream_id]:
                            try:
                                dst_lc = source_lc[0:3] + target_tgid + rf_src
                                _target_status[stream_id]["H_LC"] = bptc.encode_header_lc(dst_lc)
                            except Exception:
                                logger.exception("(to_target) caught exception while creating H_LC")
                                return
                        if "T_LC" not in _target_status[stream_id]:
                            try:
                                dst_lc = source_lc[0:3] + target_tgid + rf_src
                                _target_status[stream_id]["T_LC"] = bptc.encode_terminator_lc(dst_lc)
                            except Exception:
                                logger.exception("(to_target) caught exception while creating T_LC")
                                return
                        _target_status[stream_id]["LAST"] = pkt_time
                        _tmp_bits = _bits & ~(1 << 7)
                        _tmp_data = b"".join([data[:8], target_tgid, data[11:15], bytes([_tmp_bits]), data[16:20]])
                        dmrbits = bitarray(endian="big")
                        dmrbits.frombytes(dmrpkt)
                        if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
                            dmrbits = _target_status[stream_id]["H_LC"][0:98] + dmrbits[98:166] + _target_status[stream_id]["H_LC"][98:197]
                        elif frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM:
                            dmrbits = _target_status[stream_id]["T_LC"][0:98] + dmrbits[98:166] + _target_status[stream_id]["T_LC"][98:197]
                            self._clear_talker_alias_embed(_target_status[stream_id])
                            call_duration = pkt_time - _target_status[stream_id].get("START", pkt_time)
                            self._send_bridge_event(
                                "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                                    entry["SYSTEM"], int_id(stream_id), int_id(peer_id), int_id(rf_src), entry.get("TS", 1), int_id(target_tgid), call_duration
                                )
                            )
                        elif dtype_vseq in (1, 2, 3, 4):
                            self._rewrite_embed_lc(
                                dmrbits, _target_status[stream_id], dtype_vseq, "EMB_LC",
                            )
                        dmrpkt_out = dmrbits.tobytes()
                        _tmp_data = b"".join([_tmp_data, dmrpkt_out])
                    else:
                        _tmp_bits = _bits & ~(1 << 7)
                        _tmp_data = b"".join([data[:8], target_tgid, data[11:15], bytes([_tmp_bits]), data[16:20]])
                        _tmp_data = b"".join([_tmp_data, dmrpkt])
                    try:
                        self._send_to_system(
                            entry["SYSTEM"], _tmp_data,
                            _hops=_hops, _ber=_ber, _rssi=_rssi,
                            _source_server=_source_server, _source_rptr=_source_rptr,
                        )
                        forwarded.append(entry["SYSTEM"])
                    except Exception as e:
                        logger.warning("(ROUTER) send_to_system %s failed: %s", entry.get("SYSTEM"), e)

                else:
                    # ── Exact port of legacy bridge.py HBP target (lines 403-486 / 720-803) ──
                    entry_ts = entry.get("TS")
                    if entry_ts is None:
                        continue
                    entry_tgid_b = entry.get("TGID")
                    if isinstance(entry_tgid_b, int):
                        entry_tgid_b = bytes_3(entry_tgid_b)
                    if _target_status is None or entry_ts not in _target_status:
                        continue
                    _ts_st = _target_status[entry_ts]
                    if source_is_obp:
                        _src_stream_st = getattr(src_proto, "STATUS", {}).get(stream_id, {}) if src_proto else {}
                    else:
                        _src_stream_st = getattr(src_proto, "STATUS", {}).get(slot, {}) if src_proto else {}
                    # Contention handling (exact port of legacy bridge_master.py ~2056-2075)
                    if (entry_tgid_b != _ts_st.get("RX_TGID", b"\x00\x00\x00")) and ((pkt_time - _ts_st.get("RX_TIME", 0)) < float(_target_system.get("GROUP_HANGTIME", 0))):
                        if not _src_stream_st.get("CONTENTION"):
                            _src_stream_st["CONTENTION"] = True
                            logger.info("(%s) Call not routed to TGID %s, target active or in group hangtime: HBSystem: %s, TS: %s, TGID: %s", system_name, int_id(entry_tgid_b), entry.get("SYSTEM"), entry_ts, int_id(_ts_st.get("RX_TGID", b"")))
                        continue
                    if (entry_tgid_b != _ts_st.get("TX_TGID", b"\x00\x00\x00")) and ((pkt_time - _ts_st.get("TX_TIME", 0)) < float(_target_system.get("GROUP_HANGTIME", 0))):
                        if not _src_stream_st.get("CONTENTION"):
                            _src_stream_st["CONTENTION"] = True
                            logger.info("(%s) Call not routed to TGID %s, target in group hangtime: HBSystem: %s, TS: %s, TGID: %s", system_name, int_id(entry_tgid_b), entry.get("SYSTEM"), entry_ts, int_id(_ts_st.get("TX_TGID", b"")))
                        continue
                    if (entry_tgid_b == _ts_st.get("RX_TGID", b"\x00\x00\x00")) and ((pkt_time - _ts_st.get("RX_TIME", 0)) < STREAM_TO):
                        if not _src_stream_st.get("CONTENTION"):
                            _src_stream_st["CONTENTION"] = True
                            logger.info("(%s) Call not routed to TGID %s, matching call already active on target: HBSystem: %s, TS: %s, TGID: %s", system_name, int_id(entry_tgid_b), entry.get("SYSTEM"), entry_ts, int_id(_ts_st.get("RX_TGID", b"")))
                        continue
                    if (entry_tgid_b == _ts_st.get("TX_TGID", b"\x00\x00\x00")) and (rf_src != _ts_st.get("TX_RFS", b"")) and ((pkt_time - _ts_st.get("TX_TIME", 0)) < STREAM_TO):
                        if not _src_stream_st.get("CONTENTION"):
                            _src_stream_st["CONTENTION"] = True
                            logger.info("(%s) Call not routed for subscriber %s, call route in progress on target: HBSystem: %s, TS: %s, TGID: %s, SUB: %s", system_name, int_id(rf_src), entry.get("SYSTEM"), entry_ts, int_id(_ts_st.get("TX_TGID", b"")), int_id(_ts_st.get("TX_RFS", b"")))
                        continue
                    # New stream detection — legacy OBP uses _target_status[TS]['TX_STREAM_ID'], legacy HBP uses self.STATUS[_slot]['RX_STREAM_ID']
                    if source_is_obp:
                        _is_new_stream = (_ts_st.get("TX_STREAM_ID") != stream_id)
                    else:
                        src_status = getattr(src_proto, "STATUS", None) if src_proto else None
                        _is_new_stream = (src_status.get(slot, {}).get("RX_STREAM_ID") if src_status else b"") != stream_id
                    if _is_new_stream:
                        _ts_st["TX_START"] = pkt_time
                        _ts_st["TX_TGID"] = entry_tgid_b
                        _ts_st["TX_STREAM_ID"] = stream_id
                        _ts_st["TX_RFS"] = rf_src
                        _ts_st["TX_PEER"] = peer_id
                        dst_lc = source_lc[0:3] + entry_tgid_b + rf_src
                        _ts_st["TX_H_LC"] = bptc.encode_header_lc(dst_lc)
                        _ts_st["TX_T_LC"] = bptc.encode_terminator_lc(dst_lc)
                        _ts_st["TX_EMB_LC"] = self._encode_emblc(dst_lc)
                        self._dispatch_talker_alias_on_bridge_open(
                            _ts_st,
                            system_name,
                            entry["SYSTEM"],
                            rf_src,
                            stream_id,
                            peer_id,
                        )
                        logger.info(
                            "(%s) Conference Bridge: %s, Call Bridged to HBP System: %s TS: %s, TGID: %s",
                            system_name, _bridge_table_name, entry["SYSTEM"], entry_ts, int_id(entry_tgid_b),
                        )
                        self._send_bridge_event(
                            "GROUP VOICE,START,TX,{},{},{},{},{},{}".format(
                                entry["SYSTEM"],
                                int_id(stream_id),
                                int_id(peer_id),
                                int_id(rf_src),
                                entry_ts,
                                int_id(entry_tgid_b),
                            )
                        )
                    _ts_st["TX_TIME"] = pkt_time
                    _ts_st["TX_TYPE"] = dtype_vseq
                    # Slot bit rewrite (legacy bridge.py 457-460 / 770-773)
                    _src_entry_ts = slot
                    if _src_entry_ts != entry_ts:
                        _tmp_bits = _bits ^ (1 << 7)
                    else:
                        _tmp_bits = _bits
                    _tmp_data = b"".join([data[:8], entry_tgid_b, data[11:15], bytes([_tmp_bits]), data[16:20]])
                    # LC rewrite (exact port of legacy bridge.py 468-482 / 781-799)
                    dmrbits = bitarray(endian="big")
                    dmrbits.frombytes(dmrpkt)
                    if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
                        dmrbits = _ts_st["TX_H_LC"][0:98] + dmrbits[98:166] + _ts_st["TX_H_LC"][98:197]
                    elif frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM:
                        dmrbits = _ts_st["TX_T_LC"][0:98] + dmrbits[98:166] + _ts_st["TX_T_LC"][98:197]
                        call_duration = pkt_time - _ts_st.get("TX_START", pkt_time)
                        _end_peer = _ts_st.get("TX_PEER", peer_id)
                        self._send_bridge_event(
                            "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                                entry["SYSTEM"],
                                int_id(stream_id),
                                int_id(_end_peer),
                                int_id(rf_src),
                                entry_ts,
                                int_id(entry_tgid_b),
                                call_duration,
                            )
                        )
                    elif dtype_vseq in (1, 2, 3, 4):
                        self._rewrite_embed_lc(
                            dmrbits, _ts_st, dtype_vseq, "TX_EMB_LC",
                        )
                    dmrpkt_out = dmrbits.tobytes()
                    # bridge_master.routerOBP.to_target HBP branch: _tmp_data + dmrpkt only (~2041-2042);
                    # HBP source adds BER/RSSI from payload (bridge.py routerHBP ~800).
                    if source_is_obp:
                        _tmp_data = b"".join([_tmp_data, dmrpkt_out])
                    else:
                        _tmp_data = b"".join([_tmp_data, dmrpkt_out, data[53:55]])
                    try:
                        self._send_to_system(
                            entry["SYSTEM"], _tmp_data,
                            _hops=_hops, _ber=_ber, _rssi=_rssi,
                            _source_server=_source_server, _source_rptr=_source_rptr,
                        )
                        forwarded.append(entry["SYSTEM"])
                    except Exception as e:
                        logger.warning("(ROUTER) send_to_system %s failed: %s", entry.get("SYSTEM"), e)
                    if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM:
                        self._clear_talker_alias_embed(_ts_st)
                        self._talker_alias.clear_stream(entry["SYSTEM"], stream_id)
        # Legacy bridge_master routerOBP ~2420-2434: after to_target, VTERM — CALL END log, END RX report, _fin, lastSeq
        if (
            source_is_obp
            and call_type in ("group", "vcsbk")
            and frame_type == HBPF_DATA_SYNC
            and dtype_vseq == HBPF_SLT_VTERM
        ):
            _src_p = protocols.get(system_name) if protocols else None
            # Legacy parity (bridge_master.py:1911): routerOBP.STATUS is the flat dict.
            _obp_st = getattr(_src_p, "STATUS", None) if _src_p else None
            _ost_candidate = _obp_st.get(stream_id) if isinstance(_obp_st, dict) else None
            if isinstance(_ost_candidate, dict):
                ost = _ost_candidate
                _end_t = time.time()
                call_duration = _end_t - ost.get("START", _end_t)
                packet_rate = (ost.get("packets", 0) / call_duration) if call_duration else 0.0
                loss_pct = ((ost.get("loss", 0) / ost["packets"]) * 100) if ost.get("packets") else 0.0
                logger.info(
                    "(%s) *CALL END*   STREAM ID: %s SUB: %s PEER: %s TGID %s, TS %s, Duration: %.2f, Packet rate: %.2f/s, Loss: %.2f%%",
                    system_name,
                    int_id(stream_id),
                    int_id(rf_src),
                    int_id(peer_id),
                    int_id(dst_id),
                    slot,
                    call_duration,
                    packet_rate,
                    loss_pct,
                )
                self._send_bridge_event(
                    "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                        system_name,
                        int_id(stream_id),
                        int_id(peer_id),
                        int_id(rf_src),
                        slot,
                        int_id(dst_id),
                        call_duration,
                    )
                )
                ost["_fin"] = True
                self._obp_emit_end_tx_for_forward_legs(stream_id, system_name, _end_t)
                ost["lastSeq"] = False
        if forwarded:
            if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
                logger.info(
                    "(ROUTER) Bridged TG %s from %s -> %s",
                    bridge_key, system_name, ", ".join(forwarded),
                )
        return True

    # ── Unit DATA path (SMS, GPS, CSBK) — legacy routerOBP/routerHBP unit data branch ──

    def _unit_data_received(
        self,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        seq: int,
        slot: int,
        frame_type: int,
        dtype_vseq: int,
        stream_id: bytes,
        data: bytes,
        *,
        obp_use_parsed: bool = False,
        obp_hops: bytes = b"",
        obp_source_server: bytes | None = None,
        obp_ber: bytes = b"\x00",
        obp_rssi: bytes = b"\x00",
        obp_source_rptr: bytes = b"\x00\x00\x00\x00",
    ) -> None:
        """Legacy routerOBP/routerHBP unit data branch: DATA-GATEWAY + OBP fan-out + SUB_MAP/hotspot."""
        pkt_time = time.time()
        dmrpkt = data[20:53] if len(data) >= 53 else b""
        _bits = data[15] if len(data) > 15 else 0
        _int_dst_id = int_id(dst_id)
        systems_cfg = self._config.get("SYSTEMS", {})
        source_is_obp = systems_cfg.get(system_name, {}).get("MODE") == "OPENBRIDGE"
        global_cfg = self._config.get("GLOBAL", {})
        if source_is_obp and obp_source_server is not None:
            _source_server = obp_source_server
        else:
            _sid = global_cfg.get("SERVER_ID", b"\x00\x00\x00\x00")
            if isinstance(_sid, bytes) and len(_sid) >= 4:
                _source_server = _sid
            elif _sid is not None:
                _source_server = bytes_4(int(_sid) & 0xFFFFFFFF)
            else:
                _source_server = b"\x00\x00\x00\x00"
        _source_rptr = peer_id if not source_is_obp else obp_source_rptr

        if source_is_obp:
            _hops = obp_hops
            _ber = obp_ber
            _rssi = obp_rssi
        else:
            _hops = b""
            _ber = data[53:54] if len(data) > 53 else b"\x00"
            _rssi = data[54:55] if len(data) > 54 else b"\x00"

        # OBP unit-data loop control (legacy routerOBP ~2201-2255)
        if source_is_obp:
            protocols = self._get_protocols() if self._get_protocols else {}
            src_proto = protocols.get(system_name)
            if src_proto:
                status = getattr(src_proto, "STATUS", None)
                if status is not None:
                    if stream_id not in status:
                        status[stream_id] = {
                            "START": pkt_time, "CONTENTION": False, "RFS": rf_src,
                            "TGID": dst_id, "1ST": perf_counter(), "lastSeq": False,
                            "lastData": False, "RX_PEER": peer_id, "packets": 0, "crcs": set(),
                        }
                    status[stream_id]["LAST"] = pkt_time
                    status[stream_id]["packets"] = status[stream_id].get("packets", 0) + 1
                    # HBP loop check: if any HBP already has this RX_STREAM_ID, drop
                    for other_name, proto in protocols.items():
                        omode = systems_cfg.get(other_name, {}).get("MODE")
                        if other_name != system_name and omode != "OPENBRIDGE":
                            ostatus = getattr(proto, "STATUS", None)
                            if not ostatus:
                                continue
                            for _sysslot in ostatus:
                                slot_st = ostatus.get(_sysslot)
                                if isinstance(slot_st, dict) and stream_id == slot_st.get("RX_STREAM_ID"):
                                    if not status[stream_id].get("LOOPLOG"):
                                        logger.debug(
                                            "(%s) OBP UNIT *LoopControl* FIRST HBP: %s, STREAM ID: %s, TG: %s, TS: %s, IGNORE THIS SOURCE",
                                            system_name, other_name, int_id(stream_id), int_id(dst_id), _sysslot,
                                        )
                                        status[stream_id]["LOOPLOG"] = True
                                    return
                    # OBP earliest-wins: compare 1ST across OBP systems
                    hr_times: dict[str, float] = {}
                    for other_name, proto in protocols.items():
                        omode = systems_cfg.get(other_name, {}).get("MODE")
                        if omode == "OPENBRIDGE":
                            obp_st = getattr(proto, "STATUS", None)
                            if obp_st and stream_id in obp_st and "1ST" in obp_st[stream_id]:
                                if obp_st[stream_id].get("TGID") == dst_id:
                                    hr_times[other_name] = obp_st[stream_id]["1ST"]
                    fi = min(hr_times, key=hr_times.get, default=False)
                    if not fi:
                        logger.warning(
                            "(%s) OBP UNIT *LoopControl* fi is empty: STREAM ID: %s, TG: %s",
                            system_name, int_id(stream_id), int_id(dst_id),
                        )
                        return
                    if system_name != fi:
                        if not status[stream_id].get("LOOPLOG"):
                            logger.debug(
                                "(%s) OBP UNIT *LoopControl* FIRST OBP %s, STREAM ID: %s, TG %s, IGNORE THIS SOURCE",
                                system_name, fi, int_id(stream_id), int_id(dst_id),
                            )
                            status[stream_id]["LOOPLOG"] = True
                        return

        # Dtype-specific logging (legacy routerOBP ~2257-2280, routerHBP ~3052-3082)
        if dtype_vseq == 3:
            logger.info(
                "(%s) *UNIT CSBK* STREAM ID: %s SUB: %s PEER: %s DST_ID %s TS %s",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), _int_dst_id, slot,
            )
        elif dtype_vseq == 6:
            logger.info(
                "(%s) *UNIT DATA HEADER* STREAM ID: %s SUB: %s PEER: %s DST_ID %s TS %s",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), _int_dst_id, slot,
            )
        elif dtype_vseq == 7:
            logger.info(
                "(%s) *UNIT VCSBK 1/2 DATA BLOCK* STREAM ID: %s SUB: %s PEER: %s TGID %s TS %s",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), _int_dst_id, slot,
            )
        elif dtype_vseq == 8:
            logger.info(
                "(%s) *UNIT VCSBK 3/4 DATA BLOCK* STREAM ID: %s SUB: %s PEER: %s TGID %s TS %s",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), _int_dst_id, slot,
            )
        else:
            logger.info(
                "(%s) *UNKNOWN DATA TYPE* STREAM ID: %s SUB: %s PEER: %s TGID %s TS %s",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), _int_dst_id, slot,
            )

        _dtype_labels = {3: "UNIT CSBK", 6: "UNIT DATA HEADER", 7: "UNIT VCSBK 1/2 DATA BLOCK", 8: "UNIT VCSBK 3/4 DATA BLOCK"}
        _label = _dtype_labels.get(dtype_vseq, "UNIT DATA")
        self._send_bridge_event(
            "{},DATA,RX,{},{},{},{},{},{}".format(
                _label, system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, _int_dst_id,
            )
        )

        # DATA-GATEWAY forwarding (legacy ~2281-2284 / ~3083-3087)
        if global_cfg.get("DATA_GATEWAY"):
            dg_cfg = systems_cfg.get("DATA-GATEWAY", {})
            if dg_cfg.get("MODE") == "OPENBRIDGE" and dg_cfg.get("ENABLED"):
                logger.debug("(%s) DATA packet sent to DATA-GATEWAY", system_name)
                self._send_data_to_obp(
                    system_name, "DATA-GATEWAY", data, dmrpkt, pkt_time, stream_id,
                    dst_id, peer_id, rf_src, _bits, slot,
                    hops=_hops, ber=_ber, rssi=_rssi,
                    source_server=_source_server, source_rptr=_source_rptr,
                )

        # Fan-out to all OBP systems with VER > 1 and dst_id >= 1000000 (legacy ~2286-2295 / ~3088-3097)
        protocols = self._get_protocols() if self._get_protocols else {}
        for sys_name, sys_cfg in systems_cfg.items():
            if sys_name == system_name:
                continue
            if sys_name == "DATA-GATEWAY":
                continue
            if sys_cfg.get("MODE") == "OPENBRIDGE" and sys_cfg.get("VER", 1) > 1 and _int_dst_id >= 1000000:
                self._send_data_to_obp(
                    system_name, sys_name, data, dmrpkt, pkt_time, stream_id,
                    dst_id, peer_id, rf_src, _bits, slot,
                    hops=_hops, ber=_ber, rssi=_rssi,
                    source_server=_source_server, source_rptr=_source_rptr,
                )

        # SUB_MAP lookup (legacy ~2297-2312 / ~3099-3114)
        sub_map = self._config.get("_SUB_MAP", {})
        if dst_id in sub_map:
            _d_system, _d_slot, _d_time = sub_map[dst_id]
            _d_proto = protocols.get(_d_system)
            if _d_proto:
                _dst_slot = getattr(_d_proto, "STATUS", {}).get(_d_slot, {})
                logger.info("(%s) SUB_MAP matched, System: %s Slot: %s, Time: %s", system_name, _d_system, _d_slot, _d_time)
                _d_sys_cfg = systems_cfg.get(_d_system, {})
                if (
                    _dst_slot.get("RX_TYPE") == HBPF_SLT_VTERM
                    and _dst_slot.get("TX_TYPE") == HBPF_SLT_VTERM
                    and (pkt_time - _dst_slot.get("TX_TIME", 0) > _d_sys_cfg.get("GROUP_HANGTIME", 5))
                ):
                    _tmp_bits = _bits ^ (1 << 7) if slot != _d_slot else _bits
                    self._send_data_to_hbp(system_name, _d_system, _d_slot, dst_id, _tmp_bits, data, dmrpkt, rf_src, stream_id, peer_id)
                else:
                    logger.debug("(%s) UNIT Data not bridged to HBP - target busy: %s DST_ID: %s", system_name, _d_system, _int_dst_id)
        else:
            # Hotspot 6/7-digit peer ID match (legacy ~3131-3168 / ~2314-2345)
            for _d_system, _d_sys_cfg in systems_cfg.items():
                if _d_sys_cfg.get("MODE") != "MASTER":
                    continue
                _d_proto = protocols.get(_d_system)
                if not _d_proto:
                    continue
                _peers = _d_sys_cfg.get("PEERS", {})
                _matched = False
                for _to_peer in _peers:
                    _int_to_peer = int_id(_to_peer)
                    _dst_str = str(_int_dst_id)
                    _to_str = str(_int_to_peer)
                    if len(_dst_str) == 6:
                        if _to_str[:6] == _dst_str:
                            _d_slot = 2
                            _dst_slot = getattr(_d_proto, "STATUS", {}).get(_d_slot, {})
                            logger.info("(%s) User Peer Hotspot ID (6-digit) matched, System: %s Slot: %s", system_name, _d_system, _d_slot)
                            if (
                                _dst_slot.get("RX_TYPE") == HBPF_SLT_VTERM
                                and _dst_slot.get("TX_TYPE") == HBPF_SLT_VTERM
                                and (pkt_time - _dst_slot.get("TX_TIME", 0) > _d_sys_cfg.get("GROUP_HANGTIME", 5))
                            ):
                                _tmp_bits = _bits ^ (1 << 7) if slot != 2 else _bits
                                self._send_data_to_hbp(system_name, _d_system, _d_slot, dst_id, _tmp_bits, data, dmrpkt, rf_src, stream_id, peer_id)
                            else:
                                logger.debug("(%s) UNIT Data not bridged to HBP on slot %s - target busy: %s DST_ID: %s", system_name, _d_slot, _d_system, _int_dst_id)
                            _matched = True
                            break
                    elif len(_dst_str) >= 7:
                        if _to_str[:7] == _dst_str[:7]:
                            _d_slot = 2
                            _dst_slot = getattr(_d_proto, "STATUS", {}).get(_d_slot, {})
                            logger.info("(%s) User Peer Hotspot ID (7-digit) matched, System: %s Slot: %s", system_name, _d_system, _d_slot)
                            if (
                                _dst_slot.get("RX_TYPE") == HBPF_SLT_VTERM
                                and _dst_slot.get("TX_TYPE") == HBPF_SLT_VTERM
                                and (pkt_time - _dst_slot.get("TX_TIME", 0) > _d_sys_cfg.get("GROUP_HANGTIME", 5))
                            ):
                                _tmp_bits = _bits ^ (1 << 7) if slot != 2 else _bits
                                self._send_data_to_hbp(system_name, _d_system, _d_slot, dst_id, _tmp_bits, data, dmrpkt, rf_src, stream_id, peer_id)
                            else:
                                logger.debug("(%s) UNIT Data not bridged to HBP on slot %s - target busy: %s DST_ID: %s", system_name, _d_slot, _d_system, _int_dst_id)
                            _matched = True
                            break
                if _matched:
                    break

    def _pvt_call_received(
        self,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        seq: int,
        slot: int,
        frame_type: int,
        dtype_vseq: int,
        stream_id: bytes,
        data: bytes,
    ) -> None:
        """Legacy pvt_call_received: route private (unit) calls via SUB_MAP lookup."""
        pkt_time = time.time()
        dmrpkt = data[20:53] if len(data) >= 53 else b""
        _bits = data[15] if len(data) > 15 else 0
        sub_map = self._config.get("_SUB_MAP", {})
        systems_cfg = self._config.get("SYSTEMS", {})
        protocols = self._get_protocols() if self._get_protocols else {}
        source_proto = protocols.get(system_name)
        source_status = getattr(source_proto, "STATUS", {}) if source_proto else {}
        if source_proto:
            source_status.setdefault(slot, {})
        slot_st = source_status[slot] if source_proto and slot in source_status else {}
        if stream_id != slot_st.get("RX_STREAM_ID"):
            if (slot_st.get("RX_TYPE") != HBPF_SLT_VTERM) and (pkt_time < (slot_st.get("RX_TIME", 0) + STREAM_TO)) and (rf_src != slot_st.get("RX_RFS")):
                logger.warning(
                    "(%s) PRIVATE CALL Packet received with STREAM ID: %s <FROM> SUB: %s PEER: %s <TO> UNIT %s, SLOT %s collided with existing call",
                    system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), int_id(dst_id), slot,
                )
                return
            slot_st["RX_START"] = pkt_time
            if dst_id in sub_map:
                if sub_map[dst_id][0] != system_name:
                    self._pvt_targets = [sub_map[dst_id][0]]
                else:
                    self._pvt_targets = []
                    logger.error("PRIVATE call to a subscriber on the same system, send nothing")
            else:
                self._pvt_targets = []
            logger.info(
                "(%s) *PRIVATE CALL START* STREAM ID: %s SUB: %s PEER: %s DST: %s, TS: %s, FORWARD: %s",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), int_id(dst_id), slot, self._pvt_targets,
            )
            self._send_bridge_event(
                "PRIVATE VOICE,START,RX,{},{},{},{},{},{}".format(
                    system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id)
                )
            )
        for _target in getattr(self, "_pvt_targets", []):
            target_proto = protocols.get(_target)
            if not target_proto:
                continue
            _target_status = getattr(target_proto, "STATUS", {})
            _target_system = systems_cfg.get(_target, {})
            if _target_system.get("MODE") == "OPENBRIDGE":
                if _target_system.get("ENHANCED_OBP") and "_bcka" in _target_system and _target_system["_bcka"] < pkt_time - 60:
                    continue
                if stream_id not in _target_status:
                    _target_status[stream_id] = {
                        "START": pkt_time,
                        "CONTENTION": False,
                        "RFS": rf_src,
                        "TYPE": "UNIT",
                        "DST": dst_id,
                        "ACTIVE": True,
                    }
                    logger.info(
                        "(%s) PRIVATE call bridged to OBP System: %s TS: %s, UNIT: %s",
                        system_name, _target, slot if _target_system.get("BOTH_SLOTS") else 1, int_id(dst_id),
                    )
                    self._send_bridge_event(
                        "PRIVATE VOICE,START,TX,{},{},{},{},{},{}".format(
                            _target, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id),
                        ).encode("utf-8", "ignore")
                    )
                _target_status[stream_id]["LAST"] = pkt_time
                if _target_system.get("BOTH_SLOTS"):
                    _tmp_bits = _bits
                else:
                    _tmp_bits = _bits & ~(1 << 7)
                _tmp_data = b"".join([data[:15], _tmp_bits.to_bytes(1, "big"), data[16:20]])
                send_data = b"".join([_tmp_data, dmrpkt])
                if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM:
                    _target_status[stream_id]["ACTIVE"] = False
            else:
                ts_st = _target_status.get(slot, {})
                if (dst_id == ts_st.get("RX_TGID")) and ((pkt_time - ts_st.get("RX_TIME", 0)) < STREAM_TO):
                    if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD and slot_st.get("RX_STREAM_ID") != stream_id:
                        logger.info(
                            "(%s) PRIVATE Call not routed to destination %s, matching call already active on target: HBSystem: %s, TS: %s, DEST: %s",
                            system_name, int_id(dst_id), _target, slot, int_id(ts_st.get("RX_TGID", b"")),
                        )
                    continue
                if (dst_id == ts_st.get("TX_TGID")) and (rf_src != ts_st.get("TX_RFS")) and ((pkt_time - ts_st.get("TX_TIME", 0)) < STREAM_TO):
                    if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD and slot_st.get("RX_STREAM_ID") != stream_id:
                        logger.info(
                            "(%s) PRIVATE Call not routed for subscriber %s, call route in progress on target: HBSystem: %s, TS: %s, DEST: %s, SUB: %s",
                            system_name, int_id(rf_src), _target, slot, int_id(ts_st.get("TX_TGID", b"")), int_id(ts_st.get("TX_RFS", b"")),
                        )
                    continue
                if stream_id != slot_st.get("RX_STREAM_ID"):
                    ts_st["TX_START"] = pkt_time
                    ts_st["TX_TGID"] = dst_id
                    ts_st["TX_STREAM_ID"] = stream_id
                    ts_st["TX_RFS"] = rf_src
                    ts_st["TX_PEER"] = peer_id
                    logger.info("(%s) PRIVATE call bridged to HBP System: %s TS: %s, DST: %s", system_name, _target, slot, int_id(dst_id))
                    self._send_bridge_event(
                        "PRIVATE VOICE,START,TX,{},{},{},{},{},{}".format(
                            _target, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id),
                        ).encode("utf-8", "ignore")
                    )
                ts_st["TX_TIME"] = pkt_time
                ts_st["TX_TYPE"] = dtype_vseq
                send_data = data
            try:
                self._send_to_system(_target, send_data)
            except Exception as e:
                logger.warning("(ROUTER) send_to_system %s failed: %s", _target, e)
        if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM and slot_st.get("RX_TYPE") != HBPF_SLT_VTERM:
            self._pvt_targets = []
            call_duration = pkt_time - slot_st.get("RX_START", pkt_time)
            logger.info(
                "(%s) *PRIVATE CALL END*   STREAM ID: %s SUB: %s PEER: %s DST: %s, TS %s, Duration: %.2f",
                system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), int_id(dst_id), slot, call_duration,
            )
            self._send_bridge_event(
                "PRIVATE VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                    system_name,
                    int_id(stream_id),
                    int_id(peer_id),
                    int_id(rf_src),
                    slot,
                    int_id(dst_id),
                    call_duration,
                )
            )
        if slot_st:
            slot_st["RX_PEER"] = peer_id
            slot_st["RX_SEQ"] = seq
            slot_st["RX_RFS"] = rf_src
            slot_st["RX_TYPE"] = dtype_vseq
            slot_st["RX_TGID"] = dst_id
            slot_st["RX_TIME"] = pkt_time
            slot_st["RX_STREAM_ID"] = stream_id
