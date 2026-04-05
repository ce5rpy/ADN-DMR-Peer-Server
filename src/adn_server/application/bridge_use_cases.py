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

"""Bridge management: rule_timer, make_single_bridge, make_static_tg, etc. Orchestrates BridgeRouter."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from hashlib import blake2b
from time import perf_counter
from typing import Any

from bitarray import bitarray
from dmr_utils3 import bptc
from dmr_utils3 import decode
from dmr_utils3.const import LC_OPT

from ..domain import int_id, bytes_3, bytes_4
from ..infrastructure.hbp_constants import HBPF_DATA_SYNC, HBPF_SLT_VHEAD, HBPF_SLT_VTERM, STREAM_TO
from .ports import BridgeRouter

logger = logging.getLogger(__name__)

# While loop-control loser, re-send BCSQ periodically so peers stop forwarding if first UDP was lost (legacy sends once).
_BCSQ_LOSER_RESEND_SEC = 2.0


def _obp_target_bcsq_quenches_stream(
    systems_cfg: dict[str, Any], target_name: str, dst_id_b: bytes, stream_id: bytes
) -> bool:
    """True if target OBP config has _bcsq[tgid]==stream_id (bytes key or same int TG)."""
    m = systems_cfg.get(target_name, {}).get("_bcsq")
    if not isinstance(m, dict) or not m:
        return False
    tid = dst_id_b[:3] if isinstance(dst_id_b, bytes) and len(dst_id_b) >= 3 else bytes_3(int_id(dst_id_b))
    if m.get(tid) == stream_id:
        return True
    for k, v in m.items():
        if v != stream_id:
            continue
        try:
            if isinstance(k, bytes) and len(k) >= 3 and int_id(k) == int_id(tid):
                return True
        except Exception:
            continue
    return False


def _is_special_tg(bridge_key: str) -> bool:
    """True if bridge is special TGID 9990-9999 (excluded from infinite timer)."""
    if bridge_key and bridge_key[0:1] == "#":
        return False
    try:
        return 9990 <= int(bridge_key) <= 9999
    except ValueError:
        return False


class BridgeUseCases:
    """Use cases for conference bridge state (BRIDGES)."""

    def __init__(
        self,
        bridge_router: BridgeRouter,
        config: dict[str, Any],
        send_to_system: Any = None,
        get_protocols: Any = None,
        report_factory: Any = None,
        on_bridge_deactivated: Any = None,
        send_bcsq: Any = None,
    ) -> None:
        self._router = bridge_router
        self._config = config
        self._send_to_system = send_to_system  # (system_name, packet, **kwargs) -> None
        self._get_protocols = get_protocols  # () -> dict[str, protocol]
        self._report_factory = report_factory
        self._on_bridge_deactivated = on_bridge_deactivated  # (system_name: str) -> None; legacy disconnectedVoice
        self._send_bcsq = send_bcsq  # (system_name, tgid, stream_id) -> None; legacy OBP send_bcsq from router

    def get_bridges(self) -> dict[str, list[dict[str, Any]]]:
        """Return current BRIDGES."""
        return self._router.get_bridges()

    def rule_timer_loop(self) -> None:
        """Run one iteration of rule_timer_loop (legacy 52s LoopingCall). Activate/deactivate by timeout."""
        bridges = self._router.get_bridges()
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        remove_bridges: deque = deque()
        _debug_msgs: list[str] = []

        for bridge_key, entries in list(bridges.items()):
            bridge_used = False
            is_special_tg = _is_special_tg(bridge_key)

            for sys_entry in entries:
                system_name = sys_entry.get("SYSTEM", "")
                sys_config = systems_cfg.get(system_name, {})
                is_single_mode = sys_config.get("SINGLE_MODE", False)
                to_type = sys_entry.get("TO_TYPE", "")
                active = sys_entry.get("ACTIVE", False)
                timer = sys_entry.get("TIMER", 0.0)
                is_dynamic = bridge_key[0:1] != "#" and to_type != "STAT"
                is_obp = sys_config.get("MODE") == "OPENBRIDGE"

                if not is_single_mode and is_dynamic and not is_obp and not is_special_tg:
                    if to_type == "ON":
                        if active:
                            bridge_used = True
                            _debug_msgs.append('(ROUTER) Conference Bridge ACTIVE (INFINITE TIMER): System: %s Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))
                        else:
                            _debug_msgs.append('(ROUTER) Conference Bridge INACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))
                    elif to_type == "OFF":
                        if not active:
                            sys_entry["ACTIVE"] = True
                            bridge_used = True
                            logger.info(
                                "(ROUTER) Conference Bridge ACTIVATED (NO TIMEOUT): System: %s, Bridge: %s, TS: %s, TGID: %s",
                                system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))
                            )
                        else:
                            bridge_used = True
                            _debug_msgs.append('(ROUTER) Conference Bridge ACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))
                else:
                    if to_type == "ON":
                        if active:
                            bridge_used = True
                            if timer < now:
                                sys_entry["ACTIVE"] = False
                                if self._on_bridge_deactivated and bridge_key[:1] == "#":
                                    self._on_bridge_deactivated(system_name)
                                logger.info(
                                    "(ROUTER) Conference Bridge TIMEOUT: DEACTIVATE System: %s, Bridge: %s, TS: %s, TGID: %s",
                                    system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))
                                )
                            else:
                                logger.info(
                                    "(ROUTER) Conference Bridge ACTIVE (ON timer running): System: %s Bridge: %s, TS: %s, TGID: %s, Timeout in: %.2fs,",
                                    system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b"")), timer - now
                                )
                        elif not active:
                            _debug_msgs.append('(ROUTER) Conference Bridge INACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))
                    elif to_type == "OFF":
                        if not active:
                            if timer < now:
                                sys_entry["ACTIVE"] = True
                                bridge_used = True
                                logger.info(
                                    "(ROUTER) Conference Bridge TIMEOUT: ACTIVATE System: %s, Bridge: %s, TS: %s, TGID: %s",
                                    system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))
                                )
                            else:
                                bridge_used = True
                                logger.info(
                                    "(ROUTER) Conference Bridge INACTIVE (OFF timer running): System: %s Bridge: %s, TS: %s, TGID: %s, Timeout in: %.2fs,",
                                    system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b"")), timer - now
                                )
                        elif active:
                            bridge_used = True
                            _debug_msgs.append('(ROUTER) Conference Bridge ACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))
                    else:
                        if not is_obp or (is_obp and to_type == "STAT"):
                            bridge_used = True
                        _debug_msgs.append('(ROUTER) Conference Bridge NO ACTION: System: %s, Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))

            if not bridge_used:
                remove_bridges.append(bridge_key)

        if _debug_msgs:
            logger.debug('\n'.join(_debug_msgs))

        for key in remove_bridges:
            del bridges[key]
            logger.debug("(ROUTER) Unused conference bridge %s removed", key)

    def bridge_debug_loop(self) -> None:
        """Legacy bridgeDebug (bridge_master.py 487-543): remove invalid bridges, fix >1 active dial per MASTER."""
        logger.debug("(BRIDGEDEBUG) Running bridge debug")
        bridges = self._router.get_bridges()
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        statroll = 0

        # Kill off any bridges that should not exist, ever (legacy: 0-9, #0-#9)
        for b in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
            bridges.pop(b, None)
            bridges.pop("#" + b, None)

        for system in systems_cfg:
            bridgeroll = 0
            dialroll = 0
            activeroll = 0
            for _bridge, entries in list(bridges.items()):
                for enabled_system in entries:
                    if enabled_system.get("SYSTEM") == system:
                        bridgeroll += 1
                        if enabled_system.get("ACTIVE"):
                            if _bridge and _bridge[:1] == "#":
                                dialroll += 1
                                activeroll += 1
                            else:
                                activeroll += 1
                        if enabled_system.get("TO_TYPE") == "STAT":
                            statroll += 1
            if bridgeroll:
                logger.debug(
                    "(BRIDGEDEBUG) system %s has %s bridges of which %s are in an ACTIVE state",
                    system, bridgeroll, activeroll,
                )
            if dialroll > 1 and systems_cfg.get(system, {}).get("MODE") == "MASTER":
                logger.warning(
                    "(BRIDGEDEBUG) system %s has more than one active dial bridge (%s) - fixing",
                    system, dialroll,
                )
                _tmout = float(systems_cfg.get(system, {}).get("DEFAULT_UA_TIMER", 10))
                times: dict[float, str] = {}
                for _bridge, entries in list(bridges.items()):
                    for enabled_system in entries:
                        if enabled_system.get("ACTIVE") and _bridge and _bridge[:1] == "#":
                            t = enabled_system.get("TIMER")
                            if isinstance(t, (int, float)):
                                times[t] = _bridge
                for _bridge in set(times.values()):
                    logger.warning("(BRIDGEDEBUG) deactivating system: %s for bridge: %s", system, _bridge)
                    try:
                        _setbridge = int(_bridge[1:]) if _bridge[:1] == "#" else int(_bridge)
                    except ValueError:
                        _setbridge = 9
                    bridgetemp: list[dict[str, Any]] = []
                    for bridgesystem in bridges.get(_bridge, []):
                        if bridgesystem.get("SYSTEM") == system and bridgesystem.get("TS") == 2:
                            bridgetemp.append({
                                "SYSTEM": system,
                                "TS": 2,
                                "TGID": bytes_3(9),
                                "ACTIVE": False,
                                "TIMEOUT": _tmout * 60.0,
                                "TO_TYPE": "ON",
                                "OFF": [],
                                "ON": [bytes_3(_setbridge)],
                                "RESET": [],
                                "TIMER": now + _tmout * 60.0,
                            })
                        else:
                            bridgetemp.append(bridgesystem)
                    bridges[_bridge] = bridgetemp

        logger.info("(BRIDGEDEBUG) The server currently has %s STATic bridges", statroll)

    def apply_in_band_signalling(
        self, system_name: str, slot: int, dst_id: bytes, pkt_time: float
    ) -> None:
        """Legacy in-band signalling on voice terminator (bridge.py 817-866): reset TIMER, ON/OFF activation."""
        bridges = self._router.get_bridges()
        _dst_group = int_id(dst_id)
        dst_id_b = dst_id if isinstance(dst_id, bytes) and len(dst_id) >= 3 else bytes_3(_dst_group)

        for _bridge, entries in list(bridges.items()):
            for _system in entries:
                if _system.get("SYSTEM") != system_name:
                    continue
                _ts = _system.get("TS")
                _tgid = _system.get("TGID")
                tgid_match = _tgid == dst_id_b or (isinstance(_tgid, bytes) and isinstance(dst_id_b, bytes) and _tgid == dst_id_b)
                if not tgid_match and _tgid is not None:
                    try:
                        tgid_match = int_id(_tgid) == _dst_group
                    except (TypeError, ValueError):
                        pass
                # TGID matches a rule source, reset its timer
                if slot == _ts and tgid_match:
                    to_type = _system.get("TO_TYPE", "")
                    active = _system.get("ACTIVE", False)
                    timeout = _system.get("TIMEOUT")
                    timeout_sec = timeout if isinstance(timeout, (int, float)) else 0.0
                    if (to_type == "ON" and active) or (to_type == "OFF" and not active):
                        if timeout_sec:
                            _system["TIMER"] = pkt_time + timeout_sec
                            logger.info("(%s) Transmission match for Bridge: %s. Reset timeout to %s", system_name, _bridge, _system["TIMER"])

                # TGID matches an ACTIVATION trigger (dst_id in ON or RESET)
                on_list = _system.get("ON") or []
                reset_list = _system.get("RESET") or []
                if slot == _ts and (dst_id_b in on_list or dst_id_b in reset_list or any(int_id(x) == _dst_group for x in on_list) or any(int_id(x) == _dst_group for x in reset_list)):
                    if dst_id_b in on_list or any(int_id(x) == _dst_group for x in on_list):
                        if not _system.get("ACTIVE"):
                            _system["ACTIVE"] = True
                            _system["TIMER"] = pkt_time + (float(_system.get("TIMEOUT") or 0) or 0)
                            logger.info("(%s) Bridge: %s, connection changed to state: %s", system_name, _bridge, _system["ACTIVE"])
                            if _system.get("TO_TYPE") == "OFF":
                                _system["TIMER"] = pkt_time
                                logger.info("(%s) Bridge: %s set to \"OFF\" with an on timer rule: timeout timer cancelled", system_name, _bridge)
                        if _system.get("ACTIVE") and _system.get("TO_TYPE") == "ON" and _system.get("TIMEOUT"):
                            _system["TIMER"] = pkt_time + float(_system["TIMEOUT"])
                            logger.info("(%s) Bridge: %s, timeout timer reset to: %s", system_name, _bridge, _system["TIMER"] - pkt_time)

                # TGID matches a DE-ACTIVATION trigger (dst_id in OFF or RESET)
                off_list = _system.get("OFF") or []
                if slot == _ts and (dst_id_b in off_list or dst_id_b in reset_list or any(int_id(x) == _dst_group for x in off_list) or any(int_id(x) == _dst_group for x in reset_list)):
                    if dst_id_b in off_list or any(int_id(x) == _dst_group for x in off_list):
                        if _system.get("ACTIVE"):
                            _system["ACTIVE"] = False
                            logger.info("(%s) Bridge: %s, connection changed to state: %s", system_name, _bridge, _system["ACTIVE"])
                            if _system.get("TO_TYPE") == "ON":
                                _system["TIMER"] = pkt_time
                                logger.info("(%s) Bridge: %s set to ON with and \"OFF\" timer rule: timeout timer cancelled", system_name, _bridge)
                        if not _system.get("ACTIVE") and _system.get("TO_TYPE") == "OFF" and _system.get("TIMEOUT"):
                            _system["TIMER"] = pkt_time + float(_system["TIMEOUT"])
                            logger.info("(%s) Bridge: %s, timeout timer reset to: %s", system_name, _bridge, _system["TIMER"] - pkt_time)
                        if _system.get("ACTIVE") and _system.get("TO_TYPE") == "ON" and _dst_group in [int_id(x) for x in (_system.get("OFF") or [])]:
                            _system["TIMER"] = pkt_time
                            logger.info("(%s) Bridge: %s set to ON with and \"OFF\" timer rule: timeout timer cancelled", system_name, _bridge)

    def _obp_emit_end_tx_for_forward_legs(self, stream_id: bytes, source_system: str, now: float) -> None:
        """Emit GROUP VOICE,END,TX for every OBP that still holds this stream as a to_target forward leg.

        On idle timeout the trimmer sends END,RX for the source only. VTERM may never arrive for
        forwarded legs, so the monitor would otherwise keep stale TX chips on destination rows.
        Forward legs are identified by STATUS[stream_id] containing H_LC (see to_target OPENBRIDGE).
        """
        if not bool(self._config.get("REPORTS", {}).get("REPORT", True)):
            return
        report = self._report_factory
        if not report or not hasattr(report, "send_bridge_event"):
            return
        protocols = self._get_protocols() if self._get_protocols else {}
        systems_cfg = self._config.get("SYSTEMS", {})
        for tgt_name, tgt_proto in (protocols or {}).items():
            if tgt_name == source_system:
                continue
            if systems_cfg.get(tgt_name, {}).get("MODE") != "OPENBRIDGE":
                continue
            tstatus = getattr(tgt_proto, "STATUS", None)
            if not tstatus or stream_id not in tstatus:
                continue
            tst = tstatus[stream_id]
            if not isinstance(tst, dict) or "H_LC" not in tst:
                continue
            rfs = tst.get("RFS", b"\x00\x00\x00")
            peer = tst.get("RX_PEER", b"\x00\x00\x00\x00")
            tgid_b = tst.get("TGID", b"\x00\x00\x00")
            start = tst.get("START", now)
            duration = max(0.0, now - start)
            try:
                report.send_bridge_event(
                    "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                        tgt_name,
                        int_id(stream_id),
                        int_id(peer),
                        int_id(rfs),
                        1,
                        int_id(tgid_b),
                        duration,
                    )
                )
            except Exception:
                pass
            tstatus.pop(stream_id, None)

    def on_obp_bcsq_received(self, system_name: str, tgid: bytes, stream_id: bytes) -> None:
        """After valid BCSQ on this OBP leg: clear forward STATUS if present (no VTERM to peer).

        No BRDG_EVENT: BCSQ is control-plane quench, not a normal call end; reporting would spam
        the monitor / Last Heard with spurious ends while the real call may continue elsewhere.
        """
        protocols = self._get_protocols() if self._get_protocols else {}
        tgt_proto = protocols.get(system_name)
        if not tgt_proto:
            return
        if self._config.get("SYSTEMS", {}).get(system_name, {}).get("MODE") != "OPENBRIDGE":
            return
        tstatus = getattr(tgt_proto, "STATUS", None)
        if not tstatus or stream_id not in tstatus:
            return
        tst = tstatus[stream_id]
        if not isinstance(tst, dict) or "H_LC" not in tst:
            return
        if tst.get("TGID", b"\x00\x00\x00") != tgid:
            return
        tstatus.pop(stream_id, None)

    def stream_trimmer_loop(self) -> None:
        """Trim old stream state (legacy stream_trimmer_loop, 5s). RX/TX timeout per system/slot; OBP streams (legacy bridge.py 181-240)."""
        logger.debug("(ROUTER) Trimming inactive stream IDs from system lists")
        protocols = self._get_protocols() if self._get_protocols else {}
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        report = self._report_factory
        for system_name, protocol in protocols.items():
            if not getattr(protocol, "STATUS", None):
                continue
            # OBP: legacy bridge.py 181-202 — send GROUP VOICE,END,RX on timeout so report/monitor clears TG
            if systems_cfg.get(system_name, {}).get("MODE") == "OPENBRIDGE":
                obp_streams = getattr(protocol, "_obp_streams", None)
                if obp_streams and report and hasattr(report, "send_bridge_event"):
                    to_remove = []
                    for stream_id, st in list(obp_streams.items()):
                        last = st.get("LAST", 0)
                        if st.get("_fin") and last < now - 180:
                            to_remove.append(stream_id)
                            continue
                        if last < now - 5:
                            try:
                                rfs = st.get("RFS", b"\x00\x00\x00")
                                peer = st.get("RX_PEER", b"\x00\x00\x00\x00")
                                tgid = st.get("TGID", b"\x00\x00\x00")
                                start = st.get("START", now)
                                duration = max(0.0, last - start)
                                report.send_bridge_event(
                                    "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                                        system_name, int_id(stream_id), int_id(peer), int_id(rfs), 1, int_id(tgid), duration
                                    )
                                )
                            except Exception:
                                pass
                            to_remove.append(stream_id)
                    for stream_id in to_remove:
                        st_rm = obp_streams.get(stream_id) or {}
                        _syscfg = systems_cfg.get(system_name, {})
                        _bmap = _syscfg.get("_bcsq")
                        if isinstance(_bmap, dict):
                            for _tgid_k, _sid in list(_bmap.items()):
                                if _sid == stream_id:
                                    _bmap.pop(_tgid_k, None)
                        self._obp_emit_end_tx_for_forward_legs(stream_id, system_name, now)
                        obp_streams.pop(stream_id, None)
                        getattr(protocol, "STATUS", {}).pop(stream_id, None)
                continue
            for slot in (1, 2):
                _slot = protocol.STATUS.get(slot)
                if not _slot:
                    continue
                if _slot.get("RX_TYPE") != HBPF_SLT_VTERM and _slot.get("RX_TIME", 0) < now - 5:
                    _slot["RX_TYPE"] = HBPF_SLT_VTERM
                    logger.info(
                        "(%s) *TIME OUT*  RX STREAM ID: %s SUB: %s TGID %s, TS %s, Duration: %.2f",
                        system_name, int_id(_slot.get("RX_STREAM_ID", b"")), int_id(_slot.get("RX_RFS", b"")),
                        int_id(_slot.get("RX_TGID", b"")), slot, _slot.get("RX_TIME", 0) - _slot.get("RX_START", 0),
                    )
                    if report and hasattr(report, "send_bridge_event"):
                        try:
                            report.send_bridge_event(
                                "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                                    system_name, int_id(_slot.get("RX_STREAM_ID", b"")), int_id(_slot.get("RX_PEER", b"")),
                                    int_id(_slot.get("RX_RFS", b"")), slot, int_id(_slot.get("RX_TGID", b"")),
                                    _slot.get("RX_TIME", 0) - _slot.get("RX_START", 0),
                                )
                            )
                        except Exception:
                            pass
                if _slot.get("RX_TIME", 0) < now - 60:
                    _slot["RX_STREAM_ID"] = b"\x00"
                if _slot.get("TX_TYPE") != HBPF_SLT_VTERM and _slot.get("TX_TIME", 0) < now - 5:
                    _slot["TX_TYPE"] = HBPF_SLT_VTERM
                    logger.debug(
                        "(%s) *TIME OUT*  TX STREAM ID: %s SUB: %s TGID %s, TS %s, Duration: %.2f",
                        system_name, int_id(_slot.get("TX_STREAM_ID", b"")), int_id(_slot.get("TX_RFS", b"")),
                        int_id(_slot.get("TX_TGID", b"")), slot, _slot.get("TX_TIME", 0) - _slot.get("TX_START", 0),
                    )
                    if report and hasattr(report, "send_bridge_event"):
                        try:
                            report.send_bridge_event(
                                "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                                    system_name, int_id(_slot.get("TX_STREAM_ID", b"")), int_id(_slot.get("TX_PEER", b"")),
                                    int_id(_slot.get("TX_RFS", b"")), slot, int_id(_slot.get("TX_TGID", b"")),
                                    _slot.get("TX_TIME", 0) - _slot.get("TX_START", 0),
                                )
                            )
                        except Exception:
                            pass

    def bridge_reset_loop(self) -> None:
        """Bridge reset iteration (legacy bridge_reset, 6s). Clear _reset and remove_bridge_system."""
        bridges = self._router.get_bridges()
        systems_cfg = self._config.get("SYSTEMS", {})
        for system_name in list(systems_cfg.keys()):
            sys_cfg = systems_cfg.get(system_name, {})
            if sys_cfg.get("_reset"):
                logger.info("(BRIDGERESET) Bridge reset for %s - no peers", system_name)
                self._remove_bridge_system(system_name, bridges)
                try:
                    del sys_cfg["_opt_key"]
                except KeyError:
                    pass
                sys_cfg["_reset"] = False
                sys_cfg["_resetlog"] = False

    def _remove_bridge_system(self, system_name: str, bridges: dict[str, list[dict[str, Any]]]) -> None:
        """Remove all bridge entries for system (legacy remove_bridge_system)."""
        to_remove: list[str] = []
        for bridge_key, entries in list(bridges.items()):
            new_entries = [e for e in entries if e.get("SYSTEM") != system_name]
            if len(new_entries) < len(entries):
                if new_entries:
                    bridges[bridge_key] = new_entries
                else:
                    to_remove.append(bridge_key)
        for key in to_remove:
            del bridges[key]

    def stat_trimmer_loop(self) -> None:
        """Trim STAT-only bridges with no ON/OFF in use (legacy statTrimmer, 303s)."""
        logger.debug("(ROUTER) STAT trimmer loop started")
        bridges = self._router.get_bridges()
        remove_bridges: deque = deque()
        for bridge_key, entries in list(bridges.items()):
            has_stat = any(e.get("TO_TYPE") == "STAT" for e in entries)
            in_use = any(
                (e.get("TO_TYPE") == "ON" and e.get("ACTIVE")) or e.get("TO_TYPE") == "OFF"
                for e in entries
            )
            if has_stat and not in_use:
                remove_bridges.append(bridge_key)
        for key in remove_bridges:
            del bridges[key]
            logger.debug("(ROUTER) STAT bridge %s removed", key)

    def acl_check(self, id_val: bytes | int, acl: tuple[bool, list[tuple[int, int]]]) -> bool:
        """Check ID against ACL. Legacy acl_check."""
        return self._router.acl_check(id_val, acl)

    def _ensure_obp_source_for_tg(
        self,
        system_name: str,
        bridge_key: str,
        dst_id_b: bytes,
        dst_int: int,
    ) -> None:
        """Ensure this OBP has an ACTIVE source row for TG (TS1) in main and #reflector bridges.

        remove_bridge_system / BRIDGERESET sets all rows for a system to ACTIVE False. Local MASTER
        traffic still matches MASTER source rows; inbound OBP traffic needs these OBP rows re-enabled
        or added (e.g. new OBP in config after bridge was built).
        Same TG range as make_single_bridge OBP entries.
        """
        systems_cfg = self._config.get("SYSTEMS", {})
        if systems_cfg.get(system_name, {}).get("MODE") != "OPENBRIDGE":
            return
        if not systems_cfg.get(system_name, {}).get("ENABLED", True):
            return
        if not (79 <= dst_int < 9990 or dst_int > 9999):
            return
        bridges = self._router.get_bridges()
        now = time.time()

        def _tgid_match(entry: dict[str, Any]) -> bool:
            tg = entry.get("TGID")
            if tg == dst_id_b:
                return True
            try:
                return int_id(tg or b"\x00\x00\x00") == dst_int
            except (TypeError, ValueError):
                return False

        def _patch(entries: list[dict[str, Any]]) -> None:
            for e in entries:
                if e.get("SYSTEM") != system_name:
                    continue
                if e.get("TS") != 1:
                    continue
                if not _tgid_match(e):
                    continue
                if not e.get("ACTIVE"):
                    e["ACTIVE"] = True
                return
            entries.append(
                {
                    "SYSTEM": system_name,
                    "TS": 1,
                    "TGID": dst_id_b,
                    "ACTIVE": True,
                    "TIMEOUT": "",
                    "TO_TYPE": "NONE",
                    "OFF": [],
                    "ON": [],
                    "RESET": [],
                    "TIMER": now,
                }
            )

        for key in (bridge_key, "#" + bridge_key):
            if key not in bridges:
                continue
            _patch(bridges[key])

    def make_single_bridge(
        self,
        _tgid: bytes | int,
        _sourcesystem: str,
        _slot: int,
        _tmout: float,
    ) -> None:
        """Legacy make_single_bridge: create bridge for TG with entries per MASTER (source ACTIVE on its slot) and OBP."""
        tgid_int = int_id(_tgid) if not isinstance(_tgid, int) else _tgid
        _tgid_s = str(tgid_int)
        _tgid_b = _tgid if isinstance(_tgid, bytes) and len(_tgid) >= 3 else bytes_3(tgid_int)
        if _tgid_s in ("9990", "9991", "9992", "9993", "9994", "9995", "9996", "9997", "9998", "9999"):
            _tmout = 1.0 / 6.0
        timeout_sec = _tmout * 60.0
        now = time.time()
        bridges = self._router.get_bridges()
        bridges[_tgid_s] = []
        systems_cfg = self._config.get("SYSTEMS", {})
        for _system in systems_cfg:
            sys_cfg = systems_cfg.get(_system, {})
            if sys_cfg.get("MODE") == "OPENBRIDGE":
                if 79 <= tgid_int < 9990 or tgid_int > 9999:
                    bridges[_tgid_s].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid_b, "ACTIVE": True, "TIMEOUT": "", "TO_TYPE": "NONE", "OFF": [], "ON": [], "RESET": [], "TIMER": now})
            else:
                if _system == _sourcesystem:
                    if _slot == 1:
                        bridges[_tgid_s].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid_b, "ACTIVE": True, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now + timeout_sec})
                        bridges[_tgid_s].append({"SYSTEM": _system, "TS": 2, "TGID": _tgid_b, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now})
                    else:
                        bridges[_tgid_s].append({"SYSTEM": _system, "TS": 2, "TGID": _tgid_b, "ACTIVE": True, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now + timeout_sec})
                        bridges[_tgid_s].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid_b, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now})
                else:
                    # Other MASTER/PEER: ACTIVE False (legacy). ACTIVE True only via make_static_tg when a peer has this TG static.
                    bridges[_tgid_s].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid_b, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now})
                    bridges[_tgid_s].append({"SYSTEM": _system, "TS": 2, "TGID": _tgid_b, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now})

    def make_single_reflector(self, _tgid: bytes | int, _tmout: float, _sourcesystem: str) -> None:
        """Legacy make_single_reflector: create reflector bridge #tgid with MASTERs and OBP."""
        _tgid_s = str(int_id(_tgid) if not isinstance(_tgid, int) else _tgid)
        _bridge = "#" + _tgid_s
        _tgid_b = _tgid if isinstance(_tgid, bytes) and len(_tgid) >= 3 else bytes_3(int(_tgid_s))
        if _tgid_s in ("9990", "9991", "9992", "9993", "9994", "9995", "9996", "9997", "9998", "9999"):
            _tmout = 1.0 / 6.0
        now = time.time()
        bridges = self._router.get_bridges()
        bridges[_bridge] = []
        systems_cfg = self._config.get("SYSTEMS", {})
        for _system in systems_cfg:
            if systems_cfg.get(_system, {}).get("MODE") == "MASTER":
                def_ua = systems_cfg[_system].get("DEFAULT_UA_TIMER", 10) * 60.0
                if _system == _sourcesystem:
                    bridges[_bridge].append({"SYSTEM": _system, "TS": 2, "TGID": bytes_3(9), "ACTIVE": True, "TIMEOUT": _tmout * 60.0, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now + _tmout * 60.0})
                else:
                    bridges[_bridge].append({"SYSTEM": _system, "TS": 2, "TGID": bytes_3(9), "ACTIVE": False, "TIMEOUT": def_ua, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid_b], "RESET": [], "TIMER": now})
            if systems_cfg.get(_system, {}).get("MODE") == "OPENBRIDGE" and (79 <= int(_tgid_s) < 9990 or int(_tgid_s) > 9999):
                bridges[_bridge].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid_b, "ACTIVE": True, "TIMEOUT": "", "TO_TYPE": "NONE", "OFF": [], "ON": [], "RESET": [], "TIMER": now})

    def make_default_reflector(self, reflector: int, _tmout: float, system: str) -> None:
        """Legacy make_default_reflector: ensure #reflector bridge exists and set system TS2 to ACTIVE/OFF."""
        bridge = "#" + str(reflector)
        bridges = self._router.get_bridges()
        if bridge not in bridges:
            bridges[bridge] = []
            self.make_single_reflector(bytes_3(reflector), _tmout, system)
        bridgetemp = deque()
        for bridgesystem in bridges.get(bridge, []):
            if bridgesystem.get("SYSTEM") == system and bridgesystem.get("TS") == 2:
                bridgetemp.append({"SYSTEM": system, "TS": 2, "TGID": bytes_3(9), "ACTIVE": True, "TIMEOUT": _tmout * 60.0, "TO_TYPE": "OFF", "OFF": [], "ON": [bytes_3(reflector)], "RESET": [], "TIMER": time.time() + _tmout * 60.0})
            else:
                bridgetemp.append(bridgesystem)
        bridges[bridge] = list(bridgetemp)

    def _ensure_master_legs_in_tg_bridge(self, tg: int, system: str, _tmout: float) -> None:
        """If BRIDGES[tg] exists but this MASTER has no TS1/TS2 rows, append them.

        Legacy parity: make_stat_bridge and OPTIONS UA re-add create TS1+TS2 per MASTER; if a bridge
        was built earlier without this system, make_static_tg must insert missing legs before ACTIVE.
        """
        sys_cfg = self._config.get("SYSTEMS", {}).get(system, {})
        if sys_cfg.get("MODE") != "MASTER":
            return
        bridge_key = str(tg)
        if bridge_key[:1] == "#":
            return
        bridges = self._router.get_bridges()
        entries = bridges.get(bridge_key)
        if not entries:
            return
        tgid_b = bytes_3(tg)
        if bridge_key in ("9990", "9991", "9992", "9993", "9994", "9995", "9996", "9997", "9998", "9999"):
            tmout_eff = 1.0 / 6.0
        else:
            tmout_eff = float(_tmout)
        if tmout_eff <= 0:
            tmout_eff = 35791394.0
        timeout_sec = tmout_eff * 60.0
        now = time.time()
        has_ts1 = any(e.get("SYSTEM") == system and e.get("TS") == 1 for e in entries)
        has_ts2 = any(e.get("SYSTEM") == system and e.get("TS") == 2 for e in entries)
        if not has_ts1:
            entries.append(
                {
                    "SYSTEM": system,
                    "TS": 1,
                    "TGID": tgid_b,
                    "ACTIVE": False,
                    "TIMEOUT": timeout_sec,
                    "TO_TYPE": "ON",
                    "OFF": [],
                    "ON": [tgid_b],
                    "RESET": [],
                    "TIMER": now + timeout_sec,
                }
            )
        if not has_ts2:
            entries.append(
                {
                    "SYSTEM": system,
                    "TS": 2,
                    "TGID": tgid_b,
                    "ACTIVE": False,
                    "TIMEOUT": timeout_sec,
                    "TO_TYPE": "ON",
                    "OFF": [],
                    "ON": [tgid_b],
                    "RESET": [],
                    "TIMER": now + timeout_sec,
                }
            )

    def make_static_tg(self, tg: int, ts: int, _tmout: float, system: str) -> None:
        """Legacy make_static_tg: ensure bridge for tg exists and set system/ts to ACTIVE/OFF."""
        bridges = self._router.get_bridges()
        key = str(tg)
        if key not in bridges or not bridges.get(key):
            self.make_single_bridge(bytes_3(tg), system, ts, _tmout)
        self._ensure_master_legs_in_tg_bridge(tg, system, _tmout)
        bridges = self._router.get_bridges()
        bridgetemp = deque()
        for bridgesystem in bridges.get(key, []):
            if bridgesystem.get("SYSTEM") == system and bridgesystem.get("TS") == ts:
                bridgetemp.append({"SYSTEM": system, "TS": ts, "TGID": bytes_3(tg), "ACTIVE": True, "TIMEOUT": _tmout * 60.0, "TO_TYPE": "OFF", "OFF": [], "ON": [bytes_3(tg)], "RESET": [], "TIMER": time.time() + _tmout * 60.0})
            else:
                bridgetemp.append(bridgesystem)
        bridges[key] = list(bridgetemp)

    def reset_static_tg(self, tg: int, ts: int, _tmout: float, system: str) -> None:
        """Legacy reset_static_tg: set system/ts entry to ACTIVE False, TO_TYPE ON."""
        bridges = self._router.get_bridges()
        key = str(tg)
        if key not in bridges:
            return
        bridgetemp = deque()
        for bridgesystem in bridges[key]:
            if bridgesystem.get("SYSTEM") == system and bridgesystem.get("TS") == ts:
                bridgetemp.append({"SYSTEM": system, "TS": ts, "TGID": bytes_3(tg), "ACTIVE": False, "TIMEOUT": _tmout * 60.0, "TO_TYPE": "ON", "OFF": [], "ON": [bytes_3(tg)], "RESET": [], "TIMER": time.time() + _tmout * 60.0})
            else:
                bridgetemp.append(bridgesystem)
        bridges[key] = list(bridgetemp)

    def reset_all_reflector_system(self, _tmout: float, system: str) -> None:
        """Legacy reset_all_reflector_system: set system's TS2 entry to inactive in every # bridge."""
        bridges = self._router.get_bridges()
        timeout_sec = _tmout * 60.0
        now = time.time()
        for bridge in list(bridges.keys()):
            if bridge[:1] != "#":
                continue
            bridgetemp = deque()
            for bridgesystem in bridges.get(bridge, []):
                if bridgesystem.get("SYSTEM") == system and bridgesystem.get("TS") == 2:
                    tgid = bridgesystem.get("TGID", bytes_3(9))
                    on_tgid = bytes_3(int(bridge[1:])) if bridge[1:] else bytes_3(9)
                    bridgetemp.append({"SYSTEM": system, "TS": 2, "TGID": tgid, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [on_tgid], "RESET": [], "TIMER": now + timeout_sec})
                else:
                    bridgetemp.append(bridgesystem)
            bridges[bridge] = list(bridgetemp)

    def remove_bridge_system(self, system: str) -> None:
        """Legacy remove_bridge_system: set all entries for system to ACTIVE False, TO_TYPE ON."""
        bridges = self._router.get_bridges()
        for _bridge in list(bridges.keys()):
            bridgetemp = deque()
            for bridgesystem in bridges.get(_bridge, []):
                if bridgesystem.get("SYSTEM") != system:
                    bridgetemp.append(bridgesystem)
                else:
                    t = bridgesystem.get("TIMEOUT") or 600.0
                    if isinstance(t, str):
                        t = 600.0
                    bridgetemp.append({"SYSTEM": system, "TS": bridgesystem.get("TS", 1), "TGID": bridgesystem.get("TGID", bytes_3(0)), "ACTIVE": False, "TIMEOUT": t, "TO_TYPE": "ON", "OFF": [], "ON": [bridgesystem.get("TGID", bytes_3(0))], "RESET": [], "TIMER": time.time() + t})
            bridges[_bridge] = list(bridgetemp)

    def make_stat_bridge(self, _tgid: bytes) -> None:
        """Legacy make_stat_bridge: on-the-fly relay bridges for OBP traffic when GEN_STAT_BRIDGES is True."""
        _tgid_s = str(int_id(_tgid))
        bridges = self._router.get_bridges()
        bridges[_tgid_s] = []
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        for _system in systems_cfg:
            sys_cfg = systems_cfg.get(_system, {})
            if sys_cfg.get("MODE") != "OPENBRIDGE":
                if sys_cfg.get("MODE") == "MASTER":
                    _tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
                    timeout_sec = _tmout * 60.0
                    bridges[_tgid_s].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid], "RESET": [], "TIMER": now})
                    bridges[_tgid_s].append({"SYSTEM": _system, "TS": 2, "TGID": _tgid, "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [_tgid], "RESET": [], "TIMER": now})
            else:
                bridges[_tgid_s].append({"SYSTEM": _system, "TS": 1, "TGID": _tgid, "ACTIVE": True, "TIMEOUT": "", "TO_TYPE": "STAT", "OFF": [], "ON": [], "RESET": [], "TIMER": now})

    def deactivate_all_dynamic_bridges(self, system_name: str) -> None:
        """Legacy deactivate_all_dynamic_bridges: deactivate all non-STAT, non-reflector bridges for a system (TG 4000)."""
        bridges = self._router.get_bridges()
        for _bridge in list(bridges):
            if _bridge[:1] == "#":
                continue
            for _sys_entry in bridges[_bridge]:
                if _sys_entry.get("SYSTEM") == system_name and _sys_entry.get("TO_TYPE") != "STAT":
                    if _sys_entry.get("ACTIVE"):
                        _sys_entry["ACTIVE"] = False
                        logger.info(
                            "(ROUTER) Deactivated dynamic bridge due to TG/ID 4000: System: %s, Bridge: %s, TS: %s, TGID: %s",
                            system_name, _bridge, _sys_entry.get("TS"), int_id(_sys_entry.get("TGID", b"\x00\x00\x00")),
                        )

    def _readd_system_after_ua_timer_change(self, system: str, _tmout: float) -> None:
        """After remove_bridge_system, re-add system to bridges that no longer have ts1/ts2 (legacy 1624-1639)."""
        bridges = self._router.get_bridges()
        timeout_sec = _tmout * 60.0
        now = time.time()
        for _bridge in list(bridges.keys()):
            has_ts1 = any(e.get("SYSTEM") == system and e.get("TS") == 1 for e in bridges.get(_bridge, []))
            has_ts2 = any(e.get("SYSTEM") == system and e.get("TS") == 2 for e in bridges.get(_bridge, []))
            if _bridge[:1] != "#":
                if not has_ts1:
                    try:
                        bridges[_bridge].append({"SYSTEM": system, "TS": 1, "TGID": bytes_3(int(_bridge)), "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [bytes_3(int(_bridge))], "RESET": [], "TIMER": now + timeout_sec})
                    except ValueError:
                        pass
                if not has_ts2:
                    try:
                        bridges[_bridge].append({"SYSTEM": system, "TS": 2, "TGID": bytes_3(int(_bridge)), "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [], "ON": [bytes_3(int(_bridge))], "RESET": [], "TIMER": now + timeout_sec})
                    except ValueError:
                        pass
            else:
                if not has_ts2:
                    try:
                        bridges[_bridge].append({"SYSTEM": system, "TS": 2, "TGID": bytes_3(9), "ACTIVE": False, "TIMEOUT": timeout_sec, "TO_TYPE": "ON", "OFF": [bytes_3(4000)], "ON": [], "RESET": [], "TIMER": now + timeout_sec})
                    except ValueError:
                        pass

    def apply_startup_bridges(self) -> None:
        """Legacy startup: set default reflectors and static TGs for each MASTER system."""
        prohibited_tgs = (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999)
        logger.debug("(ROUTER) Setting default reflectors")
        for system, sys_cfg in self._config.get("SYSTEMS", {}).items():
            if sys_cfg.get("MODE") != "MASTER":
                continue
            default_ref = int(sys_cfg.get("DEFAULT_REFLECTOR", 0))
            if default_ref not in prohibited_tgs:
                self.make_default_reflector(default_ref, float(sys_cfg.get("DEFAULT_UA_TIMER", 10)), system)
        logger.debug("(ROUTER) setting static TGs")
        for system, sys_cfg in self._config.get("SYSTEMS", {}).items():
            if sys_cfg.get("MODE") != "MASTER":
                continue
            tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
            ts1_raw = sys_cfg.get("TS1_STATIC") or ""
            ts2_raw = sys_cfg.get("TS2_STATIC") or ""
            ts1 = [s.strip() for s in ts1_raw.split(",") if s.strip()]
            ts2 = [s.strip() for s in ts2_raw.split(",") if s.strip()]
            for tg_s in ts1:
                try:
                    tg = int(tg_s)
                except ValueError:
                    continue
                if tg in prohibited_tgs:
                    continue
                self.make_static_tg(tg, 1, tmout, system)
            for tg_s in ts2:
                try:
                    tg = int(tg_s)
                except ValueError:
                    continue
                if tg in prohibited_tgs:
                    continue
                self.make_static_tg(tg, 2, tmout, system)

    def options_config_for_system(self, system_name: str) -> None:
        """Update static TG bridges for one system immediately (e.g. when RPTO received). So incoming OBP traffic reaches hotspots without waiting for the 26s options_config_loop."""
        prohibited_tgs = (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999)
        systems_cfg = self._config.get("SYSTEMS", {})
        sys_cfg = systems_cfg.get(system_name, {})
        if sys_cfg.get("MODE") != "MASTER" or "OPTIONS" not in sys_cfg:
            return
        try:
            opt_str = sys_cfg["OPTIONS"]
            if isinstance(opt_str, bytes):
                opt_str = opt_str.decode("utf8", errors="replace")
            opt_str = opt_str.rstrip("\x00").encode("ascii", "ignore").decode()
            opt_str = re.sub(r"['\"]", "", opt_str)
            _options: dict[str, Any] = {}
            for x in opt_str.split(";"):
                try:
                    k, v = x.split("=", 1)
                    _options[k.strip()] = v.strip()
                except ValueError:
                    continue
            for old_k, new_k in [("DIAL", "DEFAULT_REFLECTOR"), ("TIMER", "DEFAULT_UA_TIMER"), ("TS1", "TS1_STATIC"), ("TS2", "TS2_STATIC")]:
                if old_k in _options:
                    _options[new_k] = _options.pop(old_k)
            for old_k, new_k in [("StartRef", "DEFAULT_REFLECTOR"), ("RelinkTime", "DEFAULT_UA_TIMER")]:
                if old_k in _options:
                    _options[new_k] = _options.pop(old_k)
            if "TS1_1" in _options:
                parts = [_options.pop("TS1_1", "")]
                for i in range(2, 10):
                    p = _options.pop(f"TS1_{i}", None)
                    if p is not None:
                        parts.append(p)
                _options["TS1_STATIC"] = ",".join(parts)
            if "TS2_1" in _options:
                parts = [_options.pop("TS2_1", "")]
                for i in range(2, 10):
                    p = _options.pop(f"TS2_{i}", None)
                    if p is not None:
                        parts.append(p)
                _options["TS2_STATIC"] = ",".join(parts)
            _options.setdefault("DEFAULT_UA_TIMER", sys_cfg.get("DEFAULT_UA_TIMER", 10))
            _tmout = float(int(_options.get("DEFAULT_UA_TIMER", 10)))
            if _tmout <= 0:
                _tmout = 35791394
            new_ts1 = str(_options.get("TS1_STATIC") or "").strip()
            new_ts2 = str(_options.get("TS2_STATIC") or "").strip()
            if re.search(r"[^\d,]", new_ts1) or re.search(r"[^\d,]", new_ts2):
                return
            # Legacy: reset TGs that were removed (bridge_master.py 1736-1767)
            old_ts1 = str(sys_cfg.get("TS1_STATIC") or "").strip()
            old_ts2 = str(sys_cfg.get("TS2_STATIC") or "").strip()
            new_ts1_set: set[int] = set()
            new_ts2_set: set[int] = set()
            for x in new_ts1.split(","):
                if x.strip():
                    try:
                        new_ts1_set.add(int(x))
                    except ValueError:
                        pass
            for x in new_ts2.split(","):
                if x.strip():
                    try:
                        t = int(x)
                        if t != 0 and t < 16777215:
                            new_ts2_set.add(t)
                    except ValueError:
                        pass
            for tg_s in old_ts1.split(","):
                if not tg_s.strip():
                    continue
                try:
                    tg = int(tg_s)
                    if tg not in new_ts1_set:
                        self.reset_static_tg(tg, 1, _tmout, system_name)
                except ValueError:
                    pass
            for tg_s in old_ts2.split(","):
                if not tg_s.strip():
                    continue
                try:
                    tg = int(tg_s)
                    if tg not in new_ts2_set and tg != 0 and tg < 16777215:
                        self.reset_static_tg(tg, 2, _tmout, system_name)
                except ValueError:
                    pass
            for tg_s in new_ts1.split(","):
                if not tg_s.strip():
                    continue
                try:
                    tg = int(tg_s)
                    if tg in prohibited_tgs:
                        continue
                    self.make_static_tg(tg, 1, _tmout, system_name)
                except ValueError:
                    pass
            for tg_s in new_ts2.split(","):
                if not tg_s.strip():
                    continue
                try:
                    tg = int(tg_s)
                    if tg == 0 or tg >= 16777215 or tg in prohibited_tgs:
                        continue
                    self.make_static_tg(tg, 2, _tmout, system_name)
                except ValueError:
                    pass
            systems_cfg[system_name]["TS1_STATIC"] = new_ts1
            systems_cfg[system_name]["TS2_STATIC"] = new_ts2
            systems_cfg[system_name]["DEFAULT_UA_TIMER"] = int(_tmout)
            if new_ts1 or new_ts2:
                logger.info("(OPTIONS) %s static TGs applied: TS1=%s TS2=%s", system_name, new_ts1 or "-", new_ts2 or "-")
        except Exception as e:
            logger.debug("(OPTIONS) options_config_for_system %s: %s", system_name, e)

    def _static_tg_lists_from_runtime_cfg(
        self, sys_cfg: dict[str, Any]
    ) -> tuple[float, list[int], list[int]] | None:
        """Build static TG lists from TS1_STATIC / TS2_STATIC (updated when peers send RPTO)."""
        prohibited_tgs = (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999)
        tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
        if tmout <= 0:
            tmout = 35791394.0
        ts1_list: list[int] = []
        ts2_list: list[int] = []
        for tg_s in str(sys_cfg.get("TS1_STATIC") or "").split(","):
            if not tg_s.strip():
                continue
            try:
                tg = int(tg_s.strip())
            except ValueError:
                continue
            if tg in prohibited_tgs:
                continue
            ts1_list.append(tg)
        for tg_s in str(sys_cfg.get("TS2_STATIC") or "").split(","):
            if not tg_s.strip():
                continue
            try:
                tg = int(tg_s.strip())
            except ValueError:
                continue
            if tg in prohibited_tgs:
                continue
            if tg == 0 or tg >= 16777215:
                continue
            ts2_list.append(tg)
        if not ts1_list and not ts2_list:
            return None
        return (tmout, ts1_list, ts2_list)

    def _parse_options_static_tgs(self, opt_str: str, sys_cfg: dict) -> tuple[float, list[int], list[int]] | None:
        """Parse OPTIONS string; return (tmout, ts1_tg_list, ts2_tg_list) or None. Used to apply static TGs to an existing bridge."""
        try:
            if isinstance(opt_str, bytes):
                opt_str = opt_str.decode("utf8", errors="replace")
            opt_str = opt_str.rstrip("\x00").encode("ascii", "ignore").decode()
            opt_str = re.sub(r"['\"]", "", opt_str)
            _options: dict[str, Any] = {}
            for x in opt_str.split(";"):
                try:
                    k, v = x.split("=", 1)
                    _options[k.strip()] = v.strip()
                except ValueError:
                    continue
            for old_k, new_k in [("DIAL", "DEFAULT_REFLECTOR"), ("TIMER", "DEFAULT_UA_TIMER"), ("TS1", "TS1_STATIC"), ("TS2", "TS2_STATIC")]:
                if old_k in _options:
                    _options[new_k] = _options.pop(old_k)
            if "TS1_1" in _options:
                parts = [_options.pop("TS1_1", "")]
                for i in range(2, 10):
                    p = _options.pop(f"TS1_{i}", None)
                    if p is not None:
                        parts.append(p)
                _options["TS1_STATIC"] = ",".join(parts)
            if "TS2_1" in _options:
                parts = [_options.pop("TS2_1", "")]
                for i in range(2, 10):
                    p = _options.pop(f"TS2_{i}", None)
                    if p is not None:
                        parts.append(p)
                _options["TS2_STATIC"] = ",".join(parts)
            _tmout = float(int(_options.get("DEFAULT_UA_TIMER", sys_cfg.get("DEFAULT_UA_TIMER", 10))))
            if _tmout <= 0:
                _tmout = 35791394
            ts1_list: list[int] = []
            ts2_list: list[int] = []
            for tg_s in str(_options.get("TS1_STATIC") or "").split(","):
                try:
                    tg1 = int(tg_s.strip())
                    if tg1 not in (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999):
                        ts1_list.append(tg1)
                except ValueError:
                    pass
            for tg_s in str(_options.get("TS2_STATIC") or "").split(","):
                try:
                    tg2 = int(tg_s.strip())
                    if 0 < tg2 < 16777215 and tg2 not in (9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999):
                        ts2_list.append(tg2)
                except ValueError:
                    pass
            return (_tmout, ts1_list, ts2_list)
        except Exception:
            return None

    def apply_static_tg_to_bridge(self, tg_int: int) -> None:
        """When a bridge was just created from OBP, mark MASTER systems that have this TG in static TS1/TS2 (runtime lists or OPTIONS) ACTIVE so the first OBP traffic reaches them."""
        systems_cfg = self._config.get("SYSTEMS", {})
        for _system in systems_cfg:
            if systems_cfg.get(_system, {}).get("MODE") != "MASTER":
                continue
            if not systems_cfg.get(_system, {}).get("ENABLED", True):
                continue
            sys_cfg = systems_cfg[_system]
            parsed = self._static_tg_lists_from_runtime_cfg(sys_cfg)
            if parsed is None and "OPTIONS" in sys_cfg:
                parsed = self._parse_options_static_tgs(sys_cfg["OPTIONS"], sys_cfg)
            if not parsed:
                continue
            _tmout, ts1_list, ts2_list = parsed
            if tg_int in ts1_list:
                self.make_static_tg(tg_int, 1, _tmout, _system)
            if tg_int in ts2_list:
                self.make_static_tg(tg_int, 2, _tmout, _system)

    def log_connected_systems_and_tgs(self) -> None:
        """Periodic debug: log each system, connection state, and static TGs (TS1/TS2). Only emits at DEBUG level."""
        if not logger.isEnabledFor(logging.DEBUG):
            return
        systems_cfg = self._config.get("SYSTEMS", {})
        protocols = self._get_protocols() if self._get_protocols else {}
        lines: list[str] = ["(DEBUG) Systems and TGs:"]
        for name in sorted(systems_cfg.keys()):
            cfg = systems_cfg.get(name, {})
            mode = cfg.get("MODE", "?")
            enabled = cfg.get("ENABLED", True)
            en = "enabled" if enabled else "disabled"
            parts = [f"  {name}: {mode} ({en})"]
            if mode == "MASTER":
                proto = protocols.get(name)
                peers = getattr(proto, "_peers", {}) if proto else {}
                connected = [p for p in peers.values() if p.get("CONNECTION") == "YES"]
                parts.append(f"peers_connected={len(connected)}")
                if connected:
                    def _cs(c):
                        v = c.get("CALLSIGN") or b""
                        if isinstance(v, bytes):
                            return v.decode("utf8", errors="replace").strip() or "?"
                        return str(v).strip() or "?"
                    parts.append(
                        "peers=[%s]"
                        % ", ".join("%s/%s" % (p.get("RADIO_ID", "?"), _cs(p)) for p in connected[:10])
                    )
                    if len(connected) > 10:
                        parts[-1] = parts[-1].rstrip("]") + f", +{len(connected) - 10} more]"
                ts1 = (cfg.get("TS1_STATIC") or "").strip()
                ts2 = (cfg.get("TS2_STATIC") or "").strip()
                if ts1 or ts2:
                    parts.append("TS1=%s TS2=%s" % (ts1 or "-", ts2 or "-"))
            elif mode == "PEER":
                proto = protocols.get(name)
                conn = getattr(proto, "_stats", {}).get("CONNECTION", "?") if proto else "?"
                parts.append("connection=%s" % conn)
            lines.append("".join(parts))
        if len(lines) > 1:
            logger.debug("\n".join(lines))

    def options_config_loop(self) -> None:
        """Legacy options_config: parse OPTIONS from MASTER systems and update bridges (default reflector, static TGs)."""
        prohibited_tgs = (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999)
        logger.debug("(OPTIONS) Running options parser")
        systems_cfg = self._config.get("SYSTEMS", {})
        for _system in list(systems_cfg.keys()):
            try:
                if systems_cfg.get(_system, {}).get("MODE") != "MASTER":
                    continue
                if not systems_cfg.get(_system, {}).get("ENABLED", True):
                    continue
                if "OPTIONS" not in systems_cfg.get(_system, {}):
                    continue
                opt_str = systems_cfg[_system]["OPTIONS"]
                if isinstance(opt_str, bytes):
                    opt_str = opt_str.decode("utf8", errors="replace")
                opt_str = opt_str.rstrip("\x00").encode("ascii", "ignore").decode()
                opt_str = re.sub(r"['\"]", "", opt_str)
                _options: dict[str, Any] = {}
                for x in opt_str.split(";"):
                    try:
                        k, v = x.split("=", 1)
                        _options[k.strip()] = v.strip()
                    except ValueError:
                        continue
                logger.debug("(OPTIONS) Options found for %s", _system)
                if "_opt_key" in systems_cfg[_system] and systems_cfg[_system].get("_opt_key"):
                    if "KEY" not in _options:
                        logger.debug("(OPTIONS) %s, options key set but no key in options string, skipping", _system)
                        continue
                    if systems_cfg[_system]["_opt_key"] != _options.get("KEY"):
                        logger.debug("(OPTIONS) %s, options key set but key sent does not match, skipping", _system)
                        continue
                elif _options.get("KEY"):
                    systems_cfg[_system]["_opt_key"] = _options["KEY"]
                    logger.debug("(OPTIONS) %s, _opt_key not set but key sent. Setting to sent key", _system)
                else:
                    systems_cfg[_system]["_opt_key"] = False
                    logger.debug("(OPTIONS) %s, _opt_key not set and no key sent. Set to false", _system)
                for old_k, new_k in [("DIAL", "DEFAULT_REFLECTOR"), ("TIMER", "DEFAULT_UA_TIMER"), ("TS1", "TS1_STATIC"), ("TS2", "TS2_STATIC"), ("IDENTTG", "OVERRIDE_IDENT_TG"), ("VOICETG", "OVERRIDE_IDENT_TG"), ("IDENT", "VOICE")]:
                    if old_k in _options:
                        _options[new_k] = _options.pop(old_k)
                for old_k, new_k in [("StartRef", "DEFAULT_REFLECTOR"), ("RelinkTime", "DEFAULT_UA_TIMER")]:
                    if old_k in _options:
                        _options[new_k] = _options.pop(old_k)
                if "TS1_1" in _options:
                    parts = [_options.pop("TS1_1", "")]
                    for i in range(2, 10):
                        p = _options.pop(f"TS1_{i}", None)
                        if p is not None:
                            parts.append(p)
                    _options["TS1_STATIC"] = ",".join(parts)
                if "TS2_1" in _options:
                    parts = [_options.pop("TS2_1", "")]
                    for i in range(2, 10):
                        p = _options.pop(f"TS2_{i}", None)
                        if p is not None:
                            parts.append(p)
                    _options["TS2_STATIC"] = ",".join(parts)
                # VOICE_IDENT, SINGLE_MODE, LANG (legacy options_config lines 1576-1587)
                if "VOICE" in _options and bool(_options["VOICE"]) and (systems_cfg[_system].get("VOICE_IDENT") != bool(int(_options["VOICE"]))):
                    systems_cfg[_system]["VOICE_IDENT"] = bool(int(_options["VOICE"]))
                    logger.debug("(OPTIONS) %s - Setting voice ident to %s", _system, systems_cfg[_system]["VOICE_IDENT"])
                if "OVERRIDE_IDENT_TG" in _options and _options["OVERRIDE_IDENT_TG"] and (systems_cfg[_system].get("OVERRIDE_IDENT_TG") != int(_options["OVERRIDE_IDENT_TG"])):
                    systems_cfg[_system]["OVERRIDE_IDENT_TG"] = int(_options["OVERRIDE_IDENT_TG"])
                    logger.debug("(OPTIONS) %s - Setting OVERRIDE_IDENT_TG to %s", _system, systems_cfg[_system]["OVERRIDE_IDENT_TG"])
                if "LANG" in _options and _options["LANG"] != systems_cfg[_system].get("ANNOUNCEMENT_LANGUAGE"):
                    systems_cfg[_system]["ANNOUNCEMENT_LANGUAGE"] = _options["LANG"]
                    logger.debug("(OPTIONS) %s - Setting voice language to %s", _system, systems_cfg[_system]["ANNOUNCEMENT_LANGUAGE"])
                if "SINGLE" in _options and (systems_cfg[_system].get("SINGLE_MODE") != bool(int(_options["SINGLE"]))):
                    systems_cfg[_system]["SINGLE_MODE"] = bool(int(_options["SINGLE"]))
                    logger.debug("(OPTIONS) %s - Setting SINGLE_MODE to %s", _system, systems_cfg[_system]["SINGLE_MODE"])
                _options.setdefault("TS1_STATIC", False)
                _options.setdefault("TS2_STATIC", False)
                _options.setdefault("DEFAULT_REFLECTOR", 0)
                _options.setdefault("OVERRIDE_IDENT_TG", False)
                _options.setdefault("DEFAULT_UA_TIMER", systems_cfg[_system].get("DEFAULT_UA_TIMER", 10))
                if "TS1_STATIC" not in _options or "TS2_STATIC" not in _options or "DEFAULT_REFLECTOR" not in _options or "DEFAULT_UA_TIMER" not in _options:
                    logger.debug("(OPTIONS) %s - Required field missing, ignoring", _system)
                    continue
                if _options["TS1_STATIC"] == "":
                    _options["TS1_STATIC"] = False
                if _options["TS2_STATIC"] == "":
                    _options["TS2_STATIC"] = False
                if _options.get("TS1_STATIC") and re.search(r"[^\d,]", str(_options["TS1_STATIC"])):
                    logger.debug("(OPTIONS) %s - TS1_STATIC contains characters other than numbers and comma, ignoring", _system)
                    continue
                if _options.get("TS2_STATIC") and re.search(r"[^\d,]", str(_options["TS2_STATIC"])):
                    logger.debug("(OPTIONS) %s - TS2_STATIC contains characters other than numbers and comma, ignoring", _system)
                    continue
                for key in ("DEFAULT_REFLECTOR", "OVERRIDE_IDENT_TG", "DEFAULT_UA_TIMER"):
                    if isinstance(_options.get(key), str) and not str(_options[key]).isdigit():
                        logger.debug("(OPTIONS) %s - %s is not an integer, ignoring", _system, key)
                        continue
                if int(_options.get("DEFAULT_UA_TIMER", 0)) == 0:
                    _options["DEFAULT_UA_TIMER"] = 35791394
                _tmout = float(int(_options["DEFAULT_UA_TIMER"]))
                ua_timer_changed = int(_options["DEFAULT_UA_TIMER"]) != systems_cfg[_system].get("DEFAULT_UA_TIMER")
                if ua_timer_changed:
                    logger.debug("(OPTIONS) %s Updating DEFAULT_UA_TIMER for existing bridges.", _system)
                    self.remove_bridge_system(_system)
                    self._readd_system_after_ua_timer_change(_system, _tmout)
                new_ref = int(_options.get("DEFAULT_REFLECTOR", 0))
                cur_ref = int(systems_cfg[_system].get("DEFAULT_REFLECTOR", 0))
                if new_ref != cur_ref:
                    if new_ref > 0:
                        logger.debug("(OPTIONS) %s default reflector changed, updating", _system)
                        self.reset_all_reflector_system(_tmout, _system)
                        self.make_default_reflector(new_ref, _tmout, _system)
                    elif new_ref in prohibited_tgs and not bool(new_ref):
                        logger.debug("(OPTIONS) %s default reflector is prohibited, ignoring change", _system)
                    else:
                        logger.debug("(OPTIONS) %s default reflector disabled, updating", _system)
                        self.reset_all_reflector_system(_tmout, _system)
                cur_ts1 = systems_cfg[_system].get("TS1_STATIC") or ""
                cur_ts2 = systems_cfg[_system].get("TS2_STATIC") or ""
                new_ts1 = _options.get("TS1_STATIC") or ""
                new_ts2 = _options.get("TS2_STATIC") or ""
                if str(new_ts1) != str(cur_ts1) or ua_timer_changed:
                    logger.debug("(OPTIONS) %s TS1 static TGs changed, updating", _system)
                    if cur_ts1:
                        for tg_s in str(cur_ts1).split(","):
                            if not tg_s.strip():
                                continue
                            try:
                                self.reset_static_tg(int(tg_s), 1, _tmout, _system)
                            except ValueError:
                                pass
                    if new_ts1:
                        for tg_s in str(new_ts1).split(","):
                            if not tg_s.strip():
                                continue
                            try:
                                tg = int(tg_s)
                                if tg in prohibited_tgs:
                                    logger.debug("(OPTIONS) %s TS1 TG %s is prohibited, ignoring change", _system, tg)
                                    continue
                                self.make_static_tg(tg, 1, _tmout, _system)
                            except ValueError:
                                pass
                if str(new_ts2) != str(cur_ts2) or ua_timer_changed:
                    logger.debug("(OPTIONS) %s TS2 static TGs changed, updating", _system)
                    if cur_ts2:
                        for tg_s in str(cur_ts2).split(","):
                            if not tg_s.strip():
                                continue
                            try:
                                t = int(tg_s)
                                if t == 0 or t >= 16777215:
                                    continue
                                self.reset_static_tg(t, 2, _tmout, _system)
                            except ValueError:
                                pass
                    if new_ts2:
                        for tg_s in str(new_ts2).split(","):
                            if not tg_s.strip():
                                continue
                            try:
                                tg = int(tg_s)
                                if tg == 0 or tg >= 16777215:
                                    continue
                                if tg in prohibited_tgs:
                                    logger.debug("(OPTIONS) %s TS2 TG %s is prohibited, ignoring change", _system, tg)
                                    continue
                                self.make_static_tg(tg, 2, _tmout, _system)
                            except ValueError:
                                pass
                systems_cfg[_system]["TS1_STATIC"] = _options.get("TS1_STATIC") or ""
                systems_cfg[_system]["TS2_STATIC"] = _options.get("TS2_STATIC") or ""
                systems_cfg[_system]["DEFAULT_REFLECTOR"] = int(_options.get("DEFAULT_REFLECTOR", 0))
                systems_cfg[_system]["DEFAULT_UA_TIMER"] = int(_options.get("DEFAULT_UA_TIMER", 10))
            except Exception as e:
                logger.exception("(OPTIONS) caught exception: %s", e)

    def _obp_wire_stream_dict(self, src_proto: Any, stream_id: bytes, st: dict[str, Any]) -> None:
        """Legacy routerOBP uses one STATUS[stream_id]; mirror into _obp_streams for trimmer/_fin."""
        status = getattr(src_proto, "STATUS", None)
        if status is not None:
            status[stream_id] = st
        obp = getattr(src_proto, "_obp_streams", None)
        if obp is not None:
            obp[stream_id] = st

    def _obp_group_voice_router_obp(
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
        obp_hops: bytes,
    ) -> bool:
        """Port of bridge_master.routerOBP.dmrd_received group/vcsbk (~2269-2411). False = drop packet."""
        pkt_time = time.time()
        dmrpkt = data[20:53] if len(data) >= 53 else b""
        _h = blake2b(digest_size=16)
        _h.update(data)
        _pkt_crc = _h.digest()
        protocols = self._get_protocols() if self._get_protocols else {}
        src_proto = protocols.get(system_name) if protocols else None
        if not src_proto:
            return True
        systems_cfg = self._config.get("SYSTEMS", {})
        _do_report = bool(self._config.get("REPORTS", {}).get("REPORT", True))
        status = getattr(src_proto, "STATUS", None)
        if status is None:
            return True

        if stream_id not in status:
            st: dict[str, Any] = {
                "START": pkt_time,
                "CONTENTION": False,
                "RFS": rf_src,
                "TGID": dst_id,
                "1ST": perf_counter(),
                "lastSeq": False,
                "lastData": False,
                "RX_PEER": peer_id,
                "packets": 0,
                "loss": 0,
                "crcs": set(),
            }
            if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
                try:
                    decoded = decode.voice_head_term(dmrpkt)
                    st["LC"] = decoded["LC"]
                except Exception:
                    st["LC"] = LC_OPT + dst_id + rf_src
            else:
                st["LC"] = LC_OPT + dst_id + rf_src
            self._obp_wire_stream_dict(src_proto, stream_id, st)
            _inthops = int.from_bytes(obp_hops, "big") if obp_hops else 0
            logger.info(
                "(%s) *CALL START* STREAM ID: %s SUB: %s PEER: %s TGID %s TS %s HOPS %s",
                system_name,
                int_id(stream_id),
                int_id(rf_src),
                int_id(peer_id),
                int_id(dst_id),
                slot,
                _inthops,
            )
            # INGRESS: debug-only (all OBP legs); monitor logs it but does not update OPENBRIDGES chips until START.
            if _do_report and self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
                try:
                    self._report_factory.send_bridge_event(
                        "GROUP VOICE,INGRESS,RX,{},{},{},{},{},{}".format(
                            system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id)
                        )
                    )
                except Exception:
                    pass
        else:
            st = status[stream_id]
            if "packets" in st:
                st["packets"] = st["packets"] + 1
            if "_fin" in st:
                if "_finlog" not in st:
                    logger.debug(
                        "(%s) OBP *LoopControl* STREAM ID: %s ALREADY FINISHED FROM THIS SOURCE, IGNORING",
                        system_name,
                        int_id(stream_id),
                    )
                st["_finlog"] = True
                return False
            if st["START"] + 180 < pkt_time:
                if "LOOPLOG" not in st or not st["LOOPLOG"]:
                    logger.info(
                        "(%s) OBP *TIMEOUT*, STREAM ID: %s, TG: %s, IGNORE THIS SOURCE",
                        system_name,
                        int_id(stream_id),
                        int_id(dst_id),
                    )
                    st["LOOPLOG"] = True
                st["LAST"] = pkt_time
                return False

        st = status[stream_id]
        hr_times: dict[str, float] = {}
        _sysslot_last = 0
        for other_name, proto in (protocols or {}).items():
            omode = systems_cfg.get(other_name, {}).get("MODE")
            if other_name != system_name and omode != "OPENBRIDGE":
                ostatus = getattr(proto, "STATUS", None)
                if not ostatus:
                    continue
                for _sysslot in ostatus:
                    _sysslot_last = _sysslot if isinstance(_sysslot, int) else _sysslot_last
                    slot_st = ostatus.get(_sysslot)
                    if not isinstance(slot_st, dict):
                        continue
                    if "RX_STREAM_ID" in slot_st and stream_id == slot_st.get("RX_STREAM_ID"):
                        if "LOOPLOG" not in st or not st["LOOPLOG"]:
                            logger.debug(
                                "(%s) OBP *LoopControl* FIRST HBP: %s, STREAM ID: %s, TG: %s, TS: %s, IGNORE THIS SOURCE",
                                system_name,
                                other_name,
                                int_id(stream_id),
                                int_id(dst_id),
                                _sysslot,
                            )
                            st["LOOPLOG"] = True
                        st["LAST"] = pkt_time
                        return False
            else:
                obp_status = getattr(proto, "STATUS", None)
                if not obp_status:
                    continue
                if (
                    stream_id in obp_status
                    and "1ST" in obp_status[stream_id]
                    and obp_status[stream_id].get("TGID") == dst_id
                ):
                    hr_times[other_name] = obp_status[stream_id]["1ST"]

        fi = min(hr_times, key=hr_times.get, default=False)
        hr_times.clear()
        if not fi:
            logger.warning(
                "(%s) OBP *LoopControl* fi is empty for some reason : STREAM ID: %s, TG: %s, TS: %s",
                system_name,
                int_id(stream_id),
                int_id(dst_id),
                _sysslot_last,
            )
            return False
        if system_name != fi:
            if "LOOPLOG" not in st or not st["LOOPLOG"]:
                call_duration = pkt_time - st["START"]
                logger.debug(
                    "(%s) OBP *LoopControl* FIRST OBP %s, STREAM ID: %s, TG %s, IGNORE THIS SOURCE. PACKET RATE %0.2f/s",
                    system_name,
                    fi,
                    int_id(stream_id),
                    int_id(dst_id),
                    call_duration,
                )
                st["LOOPLOG"] = True
                if _do_report and self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
                    try:
                        self._report_factory.send_bridge_event(
                            "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                                system_name,
                                int_id(stream_id),
                                int_id(peer_id),
                                int_id(rf_src),
                                slot,
                                int_id(dst_id),
                                max(0.0, pkt_time - st.get("START", pkt_time)),
                            )
                        )
                    except Exception:
                        pass
            st["LAST"] = pkt_time
            if systems_cfg.get(system_name, {}).get("ENHANCED_OBP") and self._send_bcsq:
                now_sq = time.time()
                last_sq = float(st.get("_bcsq_last", 0.0))
                if "_bcsq" not in st or (now_sq - last_sq >= _BCSQ_LOSER_RESEND_SEC):
                    self._send_bcsq(system_name, dst_id, stream_id)
                    st["_bcsq_last"] = now_sq
                    st["_bcsq"] = True
            return False

        # Legacy skips packet control on the first frame of a stream (else branch only on 2nd+ packet).
        if st.get("packets", 0) > 0:
            _elapsed = pkt_time - st["START"]
            if _elapsed > 0 and st["packets"] > 18 and (st["packets"] / _elapsed) > 25:
                logger.warning(
                    "(%s) *PacketControl* RATE DROP! Stream ID:, %s TGID: %s",
                    system_name,
                    int_id(stream_id),
                    int_id(dst_id),
                )
                pb = getattr(src_proto, "proxy_bad_peer", None)
                if callable(pb):
                    pb()
                return False

            if st["lastData"] and st["lastData"] == data and seq > 1:
                st["loss"] += 1
                logger.debug(
                    "(%s) *PacketControl* last packet is a complete duplicate of the previous one, disgarding. Stream ID:, %s TGID: %s, LOSS: %.2f%%",
                    system_name,
                    int_id(stream_id),
                    int_id(dst_id),
                    ((st["loss"] / st["packets"]) * 100) if st.get("packets") else 0.0,
                )
                return False
            if seq and seq == st["lastSeq"]:
                st["loss"] += 1
                logger.debug(
                    "(%s) *PacketControl* Duplicate sequence number %s, disgarding. Stream ID:, %s TGID: %s, LOSS: %.2f%%",
                    system_name,
                    seq,
                    int_id(stream_id),
                    int_id(dst_id),
                    ((st["loss"] / st["packets"]) * 100) if st.get("packets") else 0.0,
                )
                return False
            if seq and st["lastSeq"] and (seq != 1) and (seq < st["lastSeq"]):
                st["loss"] += 1
                logger.debug(
                    "(%s) *PacketControl* Out of order packet - last SEQ: %s, this SEQ: %s,  disgarding. Stream ID:, %s TGID: %s, LOSS: %.2f%%",
                    system_name,
                    st["lastSeq"],
                    seq,
                    int_id(stream_id),
                    int_id(dst_id),
                    ((st["loss"] / st["packets"]) * 100) if st.get("packets") else 0.0,
                )
                return False
            if _pkt_crc in st["crcs"]:
                st["loss"] += 1
                logger.debug(
                    "(%s) *PacketControl* DMR packet payload with hash: %s seen before in this stream, disgarding. Stream ID:, %s TGID: %s: SEQ:%s PACKETS: %s, LOSS: %.2f%% ",
                    system_name,
                    _pkt_crc,
                    int_id(stream_id),
                    int_id(dst_id),
                    seq,
                    st["packets"],
                    ((st["loss"] / st["packets"]) * 100) if st.get("packets") else 0.0,
                )
                return False
            if seq and st["lastSeq"] and seq > (st["lastSeq"] + 1):
                st["loss"] += 1
                logger.debug(
                    "(%s) *PacketControl* Missed packet(s) - last SEQ: %s, this SEQ: %s. Stream ID:, %s TGID: %s , LOSS: %.2f%%",
                    system_name,
                    st["lastSeq"],
                    seq,
                    int_id(stream_id),
                    int_id(dst_id),
                    ((st["loss"] / st["packets"]) * 100) if st.get("packets") else 0.0,
                )
            st["lastSeq"] = seq
            st["lastData"] = data

        # Canonical START,RX for monitor CTABLE (OpenBridge / Linked / Active QSO) after loop win; INGRESS was debug-only.
        if _do_report and self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
            if not st.get("_monitor_canonical_rx"):
                try:
                    self._report_factory.send_bridge_event(
                        "GROUP VOICE,START,RX,{},{},{},{},{},{}".format(
                            system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id)
                        )
                    )
                    st["_monitor_canonical_rx"] = True
                except Exception:
                    pass

        st = status[stream_id]
        st["crcs"].add(_pkt_crc)
        st["LAST"] = pkt_time

        if self._config.get("GLOBAL", {}).get("GEN_STAT_BRIDGES"):
            _di = int_id(dst_id)
            _bk = str(_di)
            if _di >= 5 and _di != 9 and _bk not in self._router.get_bridges():
                logger.debug("(%s) Bridge for STAT TG %s does not exist. Creating", system_name, _di)
                self.make_stat_bridge(dst_id)
        return True

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
        obp_use_parsed: bool = False,
        obp_hops: bytes = b"",
        obp_source_server: bytes | None = None,
        obp_ber: bytes = b"\x00",
        obp_rssi: bytes = b"\x00",
        obp_source_rptr: bytes = b"\x00\x00\x00\x00",
    ) -> None:
        """Called by UDP when DMRD is received. Forward to other systems in same bridge (to_target).

        Legacy `hblink.dmrd_received` passes `_hash,_hops,_source_server,_ber,_rssi,_source_rptr` after
        parsing OPENBRIDGE DMRD v1 / DMRE (`hblink.py` ~309–416, ~592–596). When `obp_use_parsed` is True,
        the OBP path uses those values (1:1 with `bridge.py` `routerOBP.dmrd_received` → `send_system`).
        """
        if not self._send_to_system:
            return
        # Legacy bridge_master 3080–3085: private call to ID 4000 only disconnects dynamics; do not route as PC.
        if call_type == "unit" and int_id(dst_id) == 4000:
            return
        if call_type == "unit":
            self._pvt_call_received(system_name, peer_id, rf_src, dst_id, seq, slot, frame_type, dtype_vseq, stream_id, data)
            return
        bridge_key = str(int_id(dst_id))
        bridges = self._router.get_bridges()
        dst_int = int_id(dst_id)
        systems_cfg = self._config.get("SYSTEMS", {})
        source_is_obp = systems_cfg.get(system_name, {}).get("MODE") == "OPENBRIDGE"
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
                tmout = self._config.get("SYSTEMS", {}).get(system_name, {}).get("DEFAULT_UA_TIMER", 10)
                logger.info(
                    "(%s) Bridge for TG %s does not exist. Creating as User Activated. Timeout %s",
                    system_name, dst_int, tmout,
                )
                self.make_single_bridge(dst_id, system_name, slot, float(tmout))
                self.apply_static_tg_to_bridge(dst_int)
                bridges = self._router.get_bridges()
        # Legacy bridge_master routerOBP ~2413-2418: scan every BRIDGES[_bridge] table; forward only within
        # a table that contains a matching ACTIVE source row (not a flat merge of TG + #TG only).
        dst_id_b = dst_id if isinstance(dst_id, bytes) and len(dst_id) >= 3 else bytes_3(dst_int)

        def _row_is_active_source(row: dict[str, Any]) -> bool:
            return bool(
                row.get("SYSTEM") == system_name
                and row.get("TS") == bridge_match_slot
                and row.get("ACTIVE")
                and (
                    row.get("TGID") == dst_id_b
                    or int_id(row.get("TGID") or b"\x00\x00\x00") == dst_int
                )
            )

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
        has_source = any(_row_is_active_source(e) for elist in bridges.values() for e in elist)
        if not has_source and systems_cfg.get(system_name, {}).get("MODE") == "MASTER":
            self.options_config_for_system(system_name)
            bridges = self._router.get_bridges()
            has_source = any(_row_is_active_source(e) for elist in bridges.values() for e in elist)
        if not has_source:
            logger.debug(
                "(ROUTER) No matching source rule for TG %s from %s slot %s (ACTIVE), not forwarding",
                bridge_key, system_name, bridge_match_slot,
            )
            return
        pkt_time = time.time()
        # Legacy bridge.py: BRDG_EVENT (OBP group/vcsbk START/END handled in _obp_group_voice_router_obp / post-forward VTERM)
        if self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
            try:
                _obp_grp = source_is_obp and call_type in ("group", "vcsbk")
                if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
                    if not _obp_grp:
                        self._report_factory.send_bridge_event(
                            "GROUP VOICE,START,RX,{},{},{},{},{},{}".format(
                                system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id)
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
                        self._report_factory.send_bridge_event(
                            "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                                system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id), duration
                            )
                        )
            except Exception:
                pass
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
        sys_ignore_obp: set[tuple[str, int]] = set()
        forwarded = []
        for _bridge_table_name, _bridge_rows in list(bridges.items()):
            if not any(_row_is_active_source(r) for r in _bridge_rows):
                continue
            for entry in _bridge_rows:
                if entry.get("SYSTEM") == system_name:
                    continue
                if not entry.get("ACTIVE", False):
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
                    _obp_key = (entry["SYSTEM"], int(entry_ts_obp))
                    if _obp_key in sys_ignore_obp:
                        continue
                    sys_ignore_obp.add(_obp_key)
                    target_tgid = entry.get("TGID")
                    if isinstance(target_tgid, int):
                        target_tgid = bytes_3(target_tgid)
                    # If target has quenched us, don't send (~1856-1859).
                    if _obp_target_bcsq_quenches_stream(systems_cfg, entry["SYSTEM"], dst_id_b, stream_id):
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
                            _target_status[stream_id]["EMB_LC"] = bptc.encode_emblc(dst_lc)
                            logger.debug(
                                "(%s) Conference Bridge: %s, Call Bridged to OBP System: %s TS: %s, TGID: %s",
                                system_name, _bridge_table_name, entry["SYSTEM"], entry.get("TS", 1), int_id(target_tgid),
                            )
                            if self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
                                try:
                                    self._report_factory.send_bridge_event(
                                        "GROUP VOICE,START,TX,{},{},{},{},{},{}".format(
                                            entry["SYSTEM"], int_id(stream_id), int_id(peer_id), int_id(rf_src), entry.get("TS", 1), int_id(target_tgid)
                                        )
                                    )
                                except Exception:
                                    pass
                        if "EMB_LC" not in _target_status[stream_id]:
                            try:
                                dst_lc = source_lc[0:3] + target_tgid + rf_src
                                _target_status[stream_id]["EMB_LC"] = bptc.encode_emblc(dst_lc)
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
                            if self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
                                try:
                                    call_duration = pkt_time - _target_status[stream_id].get("START", pkt_time)
                                    self._report_factory.send_bridge_event(
                                        "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                                            entry["SYSTEM"], int_id(stream_id), int_id(peer_id), int_id(rf_src), entry.get("TS", 1), int_id(target_tgid), call_duration
                                        )
                                    )
                                except Exception:
                                    pass
                        elif dtype_vseq in (1, 2, 3, 4):
                            dmrbits = dmrbits[0:116] + _target_status[stream_id]["EMB_LC"][dtype_vseq] + dmrbits[148:264]
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
                    # Contention handling (exact port of legacy bridge.py 413-432 / 730-745)
                    if (entry_tgid_b != _ts_st.get("RX_TGID", b"\x00\x00\x00")) and ((pkt_time - _ts_st.get("RX_TIME", 0)) < float(_target_system.get("GROUP_HANGTIME", 0))):
                        continue
                    if (entry_tgid_b != _ts_st.get("TX_TGID", b"\x00\x00\x00")) and ((pkt_time - _ts_st.get("TX_TIME", 0)) < float(_target_system.get("GROUP_HANGTIME", 0))):
                        continue
                    if (entry_tgid_b == _ts_st.get("RX_TGID", b"\x00\x00\x00")) and ((pkt_time - _ts_st.get("RX_TIME", 0)) < STREAM_TO):
                        continue
                    if (entry_tgid_b == _ts_st.get("TX_TGID", b"\x00\x00\x00")) and (rf_src != _ts_st.get("TX_RFS", b"")) and ((pkt_time - _ts_st.get("TX_TIME", 0)) < STREAM_TO):
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
                        _ts_st["TX_EMB_LC"] = bptc.encode_emblc(dst_lc)
                        logger.info(
                            "(%s) Conference Bridge: %s, Call Bridged to HBP System: %s TS: %s, TGID: %s",
                            system_name, _bridge_table_name, entry["SYSTEM"], entry_ts, int_id(entry_tgid_b),
                        )
                        if self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
                            try:
                                self._report_factory.send_bridge_event(
                                    "GROUP VOICE,START,TX,{},{},{},{},{},{}".format(
                                        entry["SYSTEM"], int_id(stream_id), int_id(peer_id), int_id(rf_src), entry_ts, int_id(entry_tgid_b)
                                    )
                                )
                            except Exception:
                                pass
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
                        if self._report_factory and hasattr(self._report_factory, "send_bridge_event"):
                            try:
                                call_duration = pkt_time - _ts_st.get("TX_START", pkt_time)
                                self._report_factory.send_bridge_event(
                                    "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                                        entry["SYSTEM"], int_id(stream_id), int_id(peer_id), int_id(rf_src), entry_ts, int_id(entry_tgid_b), call_duration
                                    )
                                )
                            except Exception:
                                pass
                    elif dtype_vseq in (1, 2, 3, 4):
                        try:
                            dmrbits = dmrbits[0:116] + _ts_st["TX_EMB_LC"][dtype_vseq] + dmrbits[148:264]
                        except Exception:
                            pass
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
        # Legacy bridge_master routerOBP ~2420-2434: after to_target, VTERM — CALL END log, END RX report, _fin, lastSeq
        if (
            source_is_obp
            and call_type in ("group", "vcsbk")
            and frame_type == HBPF_DATA_SYNC
            and dtype_vseq == HBPF_SLT_VTERM
        ):
            _src_p = protocols.get(system_name) if protocols else None
            _obp_st = getattr(_src_p, "_obp_streams", None) if _src_p else None
            if _obp_st is not None and stream_id in _obp_st:
                ost = _obp_st[stream_id]
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
                if self._config.get("REPORTS", {}).get("REPORT", True) and self._report_factory and hasattr(
                    self._report_factory, "send_bridge_event"
                ):
                    try:
                        self._report_factory.send_bridge_event(
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
                    except Exception:
                        pass
                ost["lastSeq"] = False
        if forwarded:
            if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VHEAD:
                logger.info(
                    "(ROUTER) Bridged TG %s from %s -> %s",
                    bridge_key, system_name, ", ".join(forwarded),
                )

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
            report = self._report_factory
            if report and hasattr(report, "send_bridge_event"):
                report.send_bridge_event(
                    "PRIVATE VOICE,START,RX,{},{},{},{},{},{}".format(system_name, int_id(stream_id), int_id(peer_id), int_id(rf_src), slot, int_id(dst_id))
                )
        for _target in getattr(self, "_pvt_targets", []):
            target_proto = protocols.get(_target)
            if not target_proto:
                continue
            _target_status = getattr(target_proto, "STATUS", {})
            _target_system = systems_cfg.get(_target, {})
            if _target_system.get("MODE") == "OPENBRIDGE":
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
            report = self._report_factory
            if report and hasattr(report, "send_bridge_event"):
                try:
                    report.send_bridge_event(
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
                except Exception:
                    pass
        if slot_st:
            slot_st["RX_PEER"] = peer_id
            slot_st["RX_SEQ"] = seq
            slot_st["RX_RFS"] = rf_src
            slot_st["RX_TYPE"] = dtype_vseq
            slot_st["RX_TGID"] = dst_id
            slot_st["RX_TIME"] = pkt_time
            slot_st["RX_STREAM_ID"] = stream_id
