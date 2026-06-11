# ADN DMR Peer Server - bridge timer loops (V2-P0-004)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Legacy bridge timer / trimmer loops (no Twisted imports)."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from ...domain import HBPF_SLT_VTERM, bytes_3, int_id
from .helpers import is_special_tg

logger = logging.getLogger(__name__)


class BridgeTimerMixin:
    """rule_timer, stream_trimmer, bridge_reset, stat_trimmer, bridge_debug loops."""

    def rule_timer_loop(self) -> None:
        """Run one iteration of rule_timer_loop (legacy 52s LoopingCall). Activate/deactivate by timeout."""
        if self._subscription_store is not None:
            from ..subscription.rule_timer_ops import apply_rule_timer_store
            from ..subscription.store_sync import replace_store_from_bridges

            replace_store_from_bridges(self._subscription_store, self._router.get_bridges())
            apply_rule_timer_store(
                self._subscription_store,
                self._config.get("SYSTEMS", {}),
                time.time(),
                on_bridge_deactivated=self._on_bridge_deactivated,
            )
            self._export_store_to_router()
            return

        bridges = self._router.get_bridges()
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        remove_bridges: deque = deque()
        _debug_msgs: list[str] = []

        for bridge_key, entries in list(bridges.items()):
            if bridge_key not in bridges:
                continue
            bridge_used = False
            special_tg = is_special_tg(bridge_key)

            for sys_entry in entries:
                system_name = sys_entry.get("SYSTEM", "")
                sys_config = systems_cfg.get(system_name, {})
                is_single_mode = sys_config.get("SINGLE_MODE", False)
                to_type = sys_entry.get("TO_TYPE", "")
                active = sys_entry.get("ACTIVE", False)
                timer = sys_entry.get("TIMER", 0.0)
                is_dynamic = bridge_key[0:1] != "#" and to_type != "STAT"
                is_obp = sys_config.get("MODE") == "OPENBRIDGE"

                if not is_single_mode and is_dynamic and not is_obp and not special_tg:
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
                        # OBP legs from make_single_bridge use TO_TYPE NONE (legacy parity); keep the
                        # bridge table while the OBP source row is ACTIVE (do not trim as "unused").
                        if not is_obp or (is_obp and (to_type == "STAT" or active)):
                            bridge_used = True
                        _debug_msgs.append('(ROUTER) Conference Bridge NO ACTION: System: %s, Bridge: %s, TS: %s, TGID: %s' % (system_name, bridge_key, sys_entry.get("TS"), int_id(sys_entry.get("TGID", b""))))

            if not bridge_used:
                remove_bridges.append(bridge_key)

        if _debug_msgs:
            logger.debug('\n'.join(_debug_msgs))

        for key in remove_bridges:
            del bridges[key]
            logger.debug("(ROUTER) Unused conference bridge %s removed", key)

        self._finalize_bridges_state()

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
                if _bridge not in bridges:
                    continue
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
                    if _bridge not in bridges:
                        continue
                    for enabled_system in entries:
                        if enabled_system.get("ACTIVE") and _bridge and _bridge[:1] == "#":
                            t = enabled_system.get("TIMER")
                            if isinstance(t, (int, float)):
                                times[t] = _bridge
                for _bridge in set(times.values()):
                    if _bridge not in bridges:
                        continue
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
        self._finalize_bridges_state()

    def apply_in_band_signalling(
        self, system_name: str, slot: int, dst_id: bytes, pkt_time: float
    ) -> None:
        """Legacy in-band signalling on voice terminator (bridge_master.py ~3447-3549).

        Reflector bridges (#xxx) are ONLY processed when dst TG is 9 (legacy ~3455).
        De-activation distinguishes SINGLE_MODE True/False (legacy ~3484-3548).
        """
        bridges = self._router.get_bridges()
        systems_cfg = self._config.get("SYSTEMS", {})
        _dst_group = int_id(dst_id)
        dst_id_b = dst_id if isinstance(dst_id, bytes) and len(dst_id) >= 3 else bytes_3(_dst_group)

        for _bridge, entries in list(bridges.items()):
            if _bridge not in bridges:
                continue
            # Legacy bridge_master.py ~3455: reflector bridges only respond to TG9
            if _bridge[:1] == "#" and _dst_group != 9:
                continue
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
                # [1] TGID matches a rule source, reset its timer
                if slot == _ts and tgid_match:
                    to_type = _system.get("TO_TYPE", "")
                    active = _system.get("ACTIVE", False)
                    timeout = _system.get("TIMEOUT")
                    timeout_sec = timeout if isinstance(timeout, (int, float)) else 0.0
                    if (to_type == "ON" and active) or (to_type == "OFF" and not active):
                        if timeout_sec:
                            _system["TIMER"] = pkt_time + timeout_sec
                            logger.info("(%s) [1] Transmission match for Bridge: %s. Reset timeout to %s", system_name, _bridge, _system["TIMER"])

                # [2-4] TGID matches an ACTIVATION trigger (dst_id in ON or RESET)
                on_list = _system.get("ON") or []
                reset_list = _system.get("RESET") or []
                if slot == _ts and (dst_id_b in on_list or dst_id_b in reset_list or any(int_id(x) == _dst_group for x in on_list) or any(int_id(x) == _dst_group for x in reset_list)):
                    if dst_id_b in on_list or any(int_id(x) == _dst_group for x in on_list):
                        if not _system.get("ACTIVE"):
                            _system["ACTIVE"] = True
                            _system["TIMER"] = pkt_time + (float(_system.get("TIMEOUT") or 0) or 0)
                            logger.info("(%s) [2] Bridge: %s, connection changed to state: %s", system_name, _bridge, _system["ACTIVE"])
                            if _system.get("TO_TYPE") == "OFF":
                                _system["TIMER"] = pkt_time
                                logger.info("(%s) [3] Bridge: %s set to \"OFF\" with an on timer rule: timeout timer cancelled", system_name, _bridge)
                        if _system.get("ACTIVE") and _system.get("TO_TYPE") == "ON" and _system.get("TIMEOUT"):
                            _system["TIMER"] = pkt_time + float(_system["TIMEOUT"])
                            logger.info("(%s) [4] Bridge: %s, timeout timer reset to: %s", system_name, _bridge, _system["TIMER"] - pkt_time)

                # [5-8] TGID matches a DE-ACTIVATION trigger
                # Legacy bridge_master.py ~3484-3548: SINGLE_MODE True vs False
                sys_cfg = systems_cfg.get(system_name, {})
                is_single_mode = sys_cfg.get("MODE") == "MASTER" and sys_cfg.get("SINGLE_MODE", False)

                if is_single_mode:
                    # SINGLE_MODE=True: aggressive de-activation (legacy ~3484-3503)
                    off_list = _system.get("OFF") or []
                    if slot == _ts and (dst_id_b in off_list or dst_id_b in reset_list or dst_id_b == bytes_3(4000) or dst_id_b != _tgid):
                        if dst_id_b in off_list or dst_id_b != _tgid or dst_id_b == bytes_3(4000):
                            if _system.get("ACTIVE"):
                                _system["ACTIVE"] = False
                                logger.info("(%s) [5] Bridge: %s, connection changed to state: %s", system_name, _bridge, _system["ACTIVE"])
                                if _system.get("TO_TYPE") == "ON":
                                    _system["TIMER"] = pkt_time
                                    logger.info("(%s) [6] Bridge: %s set to \"OFF\" with an on timer rule: timeout timer cancelled", system_name, _bridge)
                        if not _system.get("ACTIVE") and _system.get("TO_TYPE") == "OFF" and _system.get("TIMEOUT"):
                            _system["TIMER"] = pkt_time + float(_system["TIMEOUT"])
                            logger.info("(%s) [7] Bridge: %s, timeout timer reset to: %s", system_name, _bridge, _system["TIMER"] - pkt_time)
                        if _system.get("ACTIVE") and _system.get("TO_TYPE") == "ON" and dst_id_b in off_list:
                            _system["TIMER"] = pkt_time
                            logger.info("(%s) [8] Bridge: %s set to ON with and \"OFF\" timer rule: timeout timer cancelled", system_name, _bridge)
                else:
                    # SINGLE_MODE=False: only de-activate on TG 4000 (legacy ~3504-3548)
                    if dst_id_b == bytes_3(4000) and slot == _ts:
                        is_static_tg = False
                        ts1_static = sys_cfg.get("TS1_STATIC") or ""
                        ts2_static = sys_cfg.get("TS2_STATIC") or ""
                        if ts1_static and slot == 1:
                            static_tgs = [int(tg) for tg in ts1_static.split(",") if tg.strip()]
                            if _dst_group in static_tgs:
                                is_static_tg = True
                        elif ts2_static and slot == 2:
                            static_tgs = [int(tg) for tg in ts2_static.split(",") if tg.strip()]
                            if _dst_group in static_tgs:
                                is_static_tg = True

                        is_reflector = _bridge[:1] == "#"
                        off_list = _system.get("OFF") or []
                        if dst_id_b in off_list or dst_id_b == bytes_3(4000) or (dst_id_b != _tgid and not is_static_tg and not is_reflector):
                            if _system.get("ACTIVE"):
                                _system["ACTIVE"] = False
                                logger.info("(%s) [5b] Bridge: %s, connection changed to state: %s (TG 4000 forced deactivation)", system_name, _bridge, _system["ACTIVE"])
                                if _system.get("TO_TYPE") == "ON":
                                    _system["TIMER"] = pkt_time
                                    logger.info("(%s) [6b] Bridge: %s set to \"OFF\" with an on timer rule: timeout timer cancelled", system_name, _bridge)
                        if not _system.get("ACTIVE") and _system.get("TO_TYPE") == "OFF" and _system.get("TIMEOUT"):
                            _system["TIMER"] = pkt_time + float(_system["TIMEOUT"])
                            logger.info("(%s) [7b] Bridge: %s, timeout timer reset to: %s", system_name, _bridge, _system["TIMER"] - pkt_time)
                        if _system.get("ACTIVE") and _system.get("TO_TYPE") == "ON" and dst_id_b in (off_list or []):
                            _system["TIMER"] = pkt_time
                            logger.info("(%s) [8b] Bridge: %s set to ON with and \"OFF\" timer rule: timeout timer cancelled", system_name, _bridge)

        self._finalize_bridges_state()
        self._send_bridge_snapshot(incremental=True)

    def _obp_emit_end_tx_forward_leg(
        self,
        tgt_name: str,
        stream_id: bytes,
        tst: dict[str, Any],
        now: float,
    ) -> bool:
        """Emit GROUP VOICE,END,TX for one to_target OBP forward leg (H_LC in STATUS).

        Same CSV shape as legacy bridge_master.py send_bridgeEvent on VTERM (~2039, ~2121).
        Safe for legacy and v2 monitors (OPENBRIDGE STREAMS chip clear on END,TX).
        """
        if not isinstance(tst, dict) or "H_LC" not in tst:
            return False
        if tst.get("_end_tx_sent"):
            # Already cleared this leg's monitor TX chip; do not re-emit on repeated BCSQ.
            return False
        if not bool(self._config.get("REPORTS", {}).get("REPORT", True)):
            return False
        rfs = tst.get("RFS", b"\x00\x00\x00")
        peer = tst.get("RX_PEER", b"\x00\x00\x00\x00")
        tgid_b = tst.get("TGID", b"\x00\x00\x00")
        start = tst.get("START", now)
        duration = max(0.0, now - start)
        if not self._send_bridge_event(
            "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                tgt_name,
                int_id(stream_id),
                int_id(peer),
                int_id(rfs),
                1,
                int_id(tgid_b),
                duration,
            )
        ):
            return False
        tst["_end_tx_sent"] = True
        return True

    def _obp_emit_end_tx_for_forward_legs(self, stream_id: bytes, source_system: str, now: float) -> None:
        """Emit GROUP VOICE,END,TX for every OBP that still holds this stream as a to_target forward leg.

        On idle timeout the trimmer sends END,RX for the source only. VTERM may never arrive for
        forwarded legs, so the monitor would otherwise keep stale TX chips on destination rows.
        Forward legs are identified by STATUS[stream_id] containing H_LC (see to_target OPENBRIDGE).
        """
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
            # Emit the monitor END,TX chip-clear but DO NOT pop STATUS: legacy keeps the
            # forward-leg entry until the stream trimmer removes it by age (180s). Popping
            # mid-stream caused the source/forward-leg entry to vanish and re-CALL-START churn.
            self._obp_emit_end_tx_forward_leg(tgt_name, stream_id, tst, now)

    def on_obp_bcsq_received(self, system_name: str, tgid: bytes, stream_id: bytes) -> None:
        """After valid BCSQ on this OBP leg: emit the monitor END,TX chip-clear only.

        Legacy parity (hblink.py ~629-639): BCSQ only records CONFIG['_bcsq'][tgid]=stream_id
        (done inline in udp_hbp) and routerOBP.to_target then *skips* the quenched target for
        that stream (see _obp_target_bcsq_quenches_stream). It never destroys stream state.
        We additionally emit a one-shot END,TX so the monitor clears stale TX chips, but we do
        NOT pop STATUS[stream_id]: popping mid-call made the same stream re-CALL-START over and
        over (visible as BCSQ-storm churn), which flapped loop-control and broke OBP->HBP audio.
        The forward-leg entry is removed by the stream trimmer on idle (legacy behaviour).
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
        self._obp_emit_end_tx_forward_leg(system_name, stream_id, tst, time.time())

    def flush_monitor_events_for_system(self, system_name: str, protocol: Any) -> None:
        if not self._config.get("REPORTS", {}).get("REPORT", True):
            return
        status = getattr(protocol, "STATUS", None)
        if not isinstance(status, dict):
            return
        mode = self._config.get("SYSTEMS", {}).get(system_name, {}).get("MODE")
        now = time.time()

        if mode == "OPENBRIDGE":
            for stream_id, st in list(status.items()):
                if not isinstance(stream_id, (bytes, bytearray)) or not isinstance(st, dict):
                    continue
                trx = "TX" if "H_LC" in st else "RX"
                start = st.get("START", now)
                self._send_bridge_event(
                    "GROUP VOICE,END,{},{},{},{},{},{},{},{:.2f}".format(
                        trx, system_name, int_id(stream_id),
                        int_id(st.get("RX_PEER", b"\x00\x00\x00\x00")),
                        int_id(st.get("RFS", b"\x00\x00\x00")), 1,
                        int_id(st.get("TGID", b"\x00\x00\x00")),
                        max(0.0, now - start),
                    )
                )
                if trx == "RX":
                    self._obp_emit_end_tx_for_forward_legs(stream_id, system_name, now)
            return

        for slot in (1, 2):
            slot_st = status.get(slot)
            if not isinstance(slot_st, dict):
                continue
            for trx, sid_key, peer_key, rfs_key, tgid_key, start_key, type_key in (
                ("RX", "RX_STREAM_ID", "RX_PEER", "RX_RFS", "RX_TGID", "RX_START", "RX_TYPE"),
                ("TX", "TX_STREAM_ID", "TX_PEER", "TX_RFS", "TX_TGID", "TX_START", "TX_TYPE"),
            ):
                sid = slot_st.get(sid_key, b"\x00")
                if sid in (b"\x00", b"") or slot_st.get(type_key) == HBPF_SLT_VTERM:
                    continue
                self._send_bridge_event(
                    "GROUP VOICE,END,{},{},{},{},{},{},{},{:.2f}".format(
                        trx, system_name, int_id(sid),
                        int_id(slot_st.get(peer_key, b"\x00\x00\x00\x00")),
                        int_id(slot_st.get(rfs_key, b"\x00\x00\x00")), slot,
                        int_id(slot_st.get(tgid_key, b"\x00\x00\x00")),
                        max(0.0, now - slot_st.get(start_key, now)),
                    )
                )

    def stream_trimmer_loop(self) -> None:
        """Trim old stream state (legacy stream_trimmer_loop, 5s). RX/TX timeout per system/slot; OBP streams (legacy bridge.py 181-240)."""
        logger.debug("(ROUTER) Trimming inactive stream IDs from system lists")
        protocols = self._get_protocols() if self._get_protocols else {}
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        for system_name, protocol in protocols.items():
            if not getattr(protocol, "STATUS", None):
                continue
            # OBP: legacy bridge_master.stream_trimmer_loop:631-703 — two-stage lifecycle:
            # Stage 1 (5s idle, no _to, no _fin): set _to=True, emit END,RX, continue.
            # Stage 2 (180s idle): remove stream entry.
            #
            # Legacy parity: routerOBP.STATUS is a *flat* dict keyed only by stream_id
            # (bridge_master.py:1911). The loop iterates `for stream_id in systems[s].STATUS:`,
            # which automatically catches everything seeded by to_target HBP->OBP,
            # sendDataToOBP, pvt_call_received and the OBP source path itself. We do
            # not keep a parallel dict -- that was a divergence that produced leaks.
            if systems_cfg.get(system_name, {}).get("MODE") == "OPENBRIDGE":
                obp_status = getattr(protocol, "STATUS", None)
                if isinstance(obp_status, dict) and obp_status:
                    to_remove: list[bytes] = []
                    for stream_id, st in list(obp_status.items()):
                        if not isinstance(st, dict):
                            continue
                        last = st.get("LAST", 0)
                        # Stage 2: finished streams older than 180s → remove
                        if st.get("_fin") and last < now - 180:
                            to_remove.append(stream_id)
                            continue
                        # Stage 2: timed-out streams older than 180s → remove
                        if st.get("_to") and last < now - 180:
                            to_remove.append(stream_id)
                            continue
                        # Stage 1: 5s idle, not yet timed out → mark _to, emit END
                        if "_to" not in st and "_fin" not in st and last < now - 5:
                            rfs = st.get("RFS", b"\x00\x00\x00")
                            peer = st.get("RX_PEER", b"\x00\x00\x00\x00")
                            tgid = st.get("TGID", b"\x00\x00\x00")
                            start = st.get("START", now)
                            duration = max(0.0, last - start)
                            self._send_bridge_event(
                                "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                                    system_name, int_id(stream_id), int_id(peer), int_id(rfs), 1, int_id(tgid), duration
                                )
                            )
                            st["_to"] = True
                            # Legacy trimmer emits END,RX here only; forward legs waited ~180s.
                            # END,TX now (END_TX_FORWARD): same event as legacy VTERM path (~2039).
                            self._obp_emit_end_tx_for_forward_legs(stream_id, system_name, now)
                            continue
                    for stream_id in to_remove:
                        _syscfg = systems_cfg.get(system_name, {})
                        _bmap = _syscfg.get("_bcsq")
                        if isinstance(_bmap, dict):
                            for _tgid_k, _sid in list(_bmap.items()):
                                if _sid == stream_id:
                                    _bmap.pop(_tgid_k, None)
                        self._obp_emit_end_tx_for_forward_legs(stream_id, system_name, now)
                        obp_status.pop(stream_id, None)
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
                    self._send_bridge_event(
                        "GROUP VOICE,END,RX,{},{},{},{},{},{},{:.2f}".format(
                            system_name, int_id(_slot.get("RX_STREAM_ID", b"")), int_id(_slot.get("RX_PEER", b"")),
                            int_id(_slot.get("RX_RFS", b"")), slot, int_id(_slot.get("RX_TGID", b"")),
                            _slot.get("RX_TIME", 0) - _slot.get("RX_START", 0),
                        )
                    )
                if _slot.get("RX_TIME", 0) < now - 60:
                    _slot["RX_STREAM_ID"] = b"\x00"
                if _slot.get("TX_TYPE") != HBPF_SLT_VTERM and _slot.get("TX_TIME", 0) < now - 5:
                    _slot["TX_TYPE"] = HBPF_SLT_VTERM
                    logger.debug(
                        "(%s) *TIME OUT*  TX STREAM ID: %s SUB: %s TGID %s, TS %s, Duration: %.2f",
                        system_name, int_id(_slot.get("TX_STREAM_ID", b"")), int_id(_slot.get("TX_RFS", b"")),
                        int_id(_slot.get("TX_TGID", b"")), slot, _slot.get("TX_TIME", 0) - _slot.get("TX_START", 0),
                    )
                    self._send_bridge_event(
                        "GROUP VOICE,END,TX,{},{},{},{},{},{},{:.2f}".format(
                            system_name, int_id(_slot.get("TX_STREAM_ID", b"")), int_id(_slot.get("TX_PEER", b"")),
                            int_id(_slot.get("TX_RFS", b"")), slot, int_id(_slot.get("TX_TGID", b"")),
                            _slot.get("TX_TIME", 0) - _slot.get("TX_START", 0),
                        )
                    )
            # -- Intentional divergence from legacy --
            # Legacy bridge_master.py:602 only iterates `range(1,3)` in the HBP branch,
            # so any STATUS[stream_id] entry seeded by voice_use_cases (announcements
            # via sys_obj.STATUS[stream_id], cf. bridge_master.py:1156/1626) or by
            # send_voice_packet against HBP MASTER targets is never freed in legacy.
            # Here we defensively sweep any bytes-keyed entry with LAST > 180 s.
            # This does not change the wire protocol; it only releases memory.
            hbp_status = getattr(protocol, "STATUS", None)
            if isinstance(hbp_status, dict):
                for _k in list(hbp_status.keys()):
                    if isinstance(_k, (bytes, bytearray)):
                        _v = hbp_status.get(_k)
                        if isinstance(_v, dict) and _v.get("LAST", 0) < now - 180:
                            hbp_status.pop(_k, None)
            if hasattr(protocol, "trim_dmra_streams"):
                protocol.trim_dmra_streams()

    def bridge_reset_loop(self) -> None:
        """Bridge reset iteration (legacy bridge_reset, 6s). Clear _reset and remove_bridge_system."""
        systems_cfg = self._config.get("SYSTEMS", {})
        for system_name in list(systems_cfg.keys()):
            sys_cfg = systems_cfg.get(system_name, {})
            if sys_cfg.get("_reset"):
                logger.info("(BRIDGERESET) Bridge reset for %s - no peers", system_name)
                self.remove_bridge_system(system_name)
                try:
                    del sys_cfg["_opt_key"]
                except KeyError:
                    pass
                try:
                    del sys_cfg["_options_static_apply_fp"]
                except KeyError:
                    pass
                self._restore_prohibited_static_bridge_legs(system_name)
                sys_cfg["_reset"] = False
                sys_cfg["_resetlog"] = False
        self._finalize_bridges_state()

    def _restore_prohibited_static_bridge_legs(self, system_name: str) -> None:
        """After BRIDGERESET / peer RPTO: restore static TGs in prohibited_tgs (parity with _make_echo_bridges)."""
        prohibited_tgs = (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999)
        sys_cfg = self._config.get("SYSTEMS", {}).get(system_name, {})
        if sys_cfg.get("MODE") != "MASTER" or not sys_cfg.get("ENABLED", True):
            return
        bridges = self._router.get_bridges()
        now = time.time()
        for ts, static_key, acl_key in (
            (1, "TS1_STATIC", "TG1_ACL"),
            (2, "TS2_STATIC", "TG2_ACL"),
        ):
            for tg_s in str(sys_cfg.get(static_key) or "").split(","):
                tg_s = tg_s.strip()
                if not tg_s:
                    continue
                try:
                    tg = int(tg_s)
                except ValueError:
                    continue
                if tg not in prohibited_tgs:
                    continue
                if sys_cfg.get("USE_ACL") and not self.acl_check(
                    bytes_3(tg), sys_cfg.get(acl_key, (True, []))
                ):
                    continue
                bridge_key = str(tg)
                if bridge_key not in bridges:
                    continue
                timeout_sec = (1.0 / 6.0) * 60.0
                leg: dict[str, Any] = {
                    "SYSTEM": system_name,
                    "TS": ts,
                    "TGID": bytes_3(tg),
                    "ACTIVE": True,
                    "TIMEOUT": timeout_sec,
                    "TO_TYPE": "NONE",
                    "ON": [],
                    "OFF": [],
                    "RESET": [],
                    "TIMER": now + timeout_sec,
                }
                for i, entry in enumerate(bridges[bridge_key]):
                    if entry.get("SYSTEM") == system_name and entry.get("TS") == ts:
                        if entry.get("ACTIVE") and entry.get("TO_TYPE") == "NONE":
                            break
                        bridges[bridge_key][i] = leg
                        logger.info(
                            "(ROUTER) Restored service bridge leg: %s bridge %s TS %s",
                            system_name, bridge_key, ts,
                        )
                        break
                else:
                    bridges[bridge_key].append(leg)
                    logger.info(
                        "(ROUTER) Re-added service bridge leg: %s bridge %s TS %s",
                        system_name, bridge_key, ts,
                    )
        self._finalize_bridges_state()

    def _remove_bridge_system(self, system_name: str, bridges: dict[str, list[dict[str, Any]]]) -> None:
        """Remove all bridge entries for system (legacy remove_bridge_system)."""
        to_remove: list[str] = []
        for bridge_key, entries in list(bridges.items()):
            if bridge_key not in bridges:
                continue
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
            if bridge_key not in bridges:
                continue
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
        self._finalize_bridges_state()
