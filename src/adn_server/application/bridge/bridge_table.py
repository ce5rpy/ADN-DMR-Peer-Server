# ADN DMR Peer Server - bridge table management (V2-P0-004)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""BRIDGES table lifecycle: create, static TG, OPTIONS refresh (no Twisted)."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from typing import Any

from ...domain import bytes_3, int_id

logger = logging.getLogger(__name__)


class BridgeTableMixin:
    """make_single_bridge, stat/static TG, options_config_loop."""

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
        for bridgesystem in bridges.get(key, []):
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
            if bridge not in bridges:
                continue
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
            if _bridge not in bridges:
                continue
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
            if _bridge not in bridges:
                continue
            if _bridge[:1] == "#":
                continue
            for _sys_entry in bridges.get(_bridge, []):
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
            if _bridge not in bridges:
                continue
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
        self._sync_subscription_store()

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
            # Legacy options_config: malformed TS1/TS2 aborts the whole OPTIONS apply (continue).
            if new_ts1 and re.search(r"[^\d,]", new_ts1):
                return
            if new_ts2 and re.search(r"[^\d,]", new_ts2):
                return
            merged = self._merged_static_tg_lists_for_master(system_name)
            if merged is not None:
                _tmout, ts1_nums, ts2_nums = merged
                new_ts1 = ",".join(str(x) for x in ts1_nums)
                new_ts2 = ",".join(str(x) for x in ts2_nums)
            if re.search(r"[^\d,]", new_ts1) or re.search(r"[^\d,]", new_ts2):
                return
            # Peers may resend identical RPTO on every voice burst. YAML may already match parsed TS — do not
            # compare only to TS*_STATIC (first RPTO could skip make_static_tg). Skip if we already applied
            # this exact fingerprint after a previous RPTO in this process.
            _fp = f"{new_ts1}|{new_ts2}|{int(_tmout)}"
            if sys_cfg.get("_options_static_apply_fp") == _fp:
                self._restore_prohibited_static_bridge_legs(system_name)
                self._sync_subscription_store()
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
            systems_cfg[system_name]["_options_static_apply_fp"] = _fp
            if new_ts1 or new_ts2:
                logger.info("(OPTIONS) %s static TGs applied: TS1=%s TS2=%s", system_name, new_ts1 or "-", new_ts2 or "-")
            self._restore_prohibited_static_bridge_legs(system_name)
            self._sync_subscription_store()
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
            ts1_raw = str(_options.get("TS1_STATIC") or "").strip()
            ts2_raw = str(_options.get("TS2_STATIC") or "").strip()
            if ts1_raw and not re.search(r"[^\d,]", ts1_raw):
                for tg_s in ts1_raw.split(","):
                    try:
                        tg1 = int(tg_s.strip())
                        if tg1 not in (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999):
                            ts1_list.append(tg1)
                    except ValueError:
                        pass
            if ts2_raw and not re.search(r"[^\d,]", ts2_raw):
                for tg_s in ts2_raw.split(","):
                    try:
                        tg2 = int(tg_s.strip())
                        if 0 < tg2 < 16777215 and tg2 not in (9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999):
                            ts2_list.append(tg2)
                    except ValueError:
                        pass
            return (_tmout, ts1_list, ts2_list)
        except Exception:
            return None

    def _merged_static_tg_lists_for_master(
        self, system_name: str
    ) -> tuple[float, list[int], list[int]] | None:
        """Union static TG ids from runtime YAML and every connected peer RPTO (inject proxy)."""
        sys_cfg = self._config.get("SYSTEMS", {}).get(system_name, {})
        if sys_cfg.get("MODE") != "MASTER":
            return None
        tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
        if tmout <= 0:
            tmout = 35791394.0
        ts1_set: set[int] = set()
        ts2_set: set[int] = set()
        runtime = self._static_tg_lists_from_runtime_cfg(sys_cfg)
        if runtime is not None:
            tmout, ts1_list, ts2_list = runtime
            ts1_set.update(ts1_list)
            ts2_set.update(ts2_list)
        protocols = self._get_protocols() if self._get_protocols else {}
        proto = protocols.get(system_name)
        peers = getattr(proto, "_peers", {}) if proto is not None else {}
        if isinstance(peers, dict):
            for peer in peers.values():
                if not isinstance(peer, dict) or peer.get("CONNECTION") != "YES":
                    continue
                opt = peer.get("OPTIONS")
                if opt is None:
                    continue
                if isinstance(opt, bytes):
                    opt_str = opt.decode("utf8", errors="replace")
                else:
                    opt_str = str(opt)
                parsed = self._parse_options_static_tgs(opt_str, sys_cfg)
                if parsed is None:
                    continue
                peer_tmout, ts1_list, ts2_list = parsed
                if peer_tmout > 0:
                    tmout = max(tmout, peer_tmout)
                ts1_set.update(ts1_list)
                ts2_set.update(ts2_list)
        if not ts1_set and not ts2_set and "OPTIONS" in sys_cfg:
            parsed = self._parse_options_static_tgs(sys_cfg["OPTIONS"], sys_cfg)
            if parsed is not None:
                tmout, ts1_list, ts2_list = parsed
                ts1_set.update(ts1_list)
                ts2_set.update(ts2_list)
        if not ts1_set and not ts2_set:
            return None
        return (tmout, sorted(ts1_set), sorted(ts2_set))

    def apply_static_tg_to_bridge(self, tg_int: int) -> None:
        """When a bridge was just created from OBP, mark MASTER systems that have this TG in static TS1/TS2 (runtime lists or OPTIONS) ACTIVE so the first OBP traffic reaches them."""
        systems_cfg = self._config.get("SYSTEMS", {})
        for _system in systems_cfg:
            if systems_cfg.get(_system, {}).get("MODE") != "MASTER":
                continue
            if not systems_cfg.get(_system, {}).get("ENABLED", True):
                continue
            parsed = self._merged_static_tg_lists_for_master(_system)
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
                merged = self._merged_static_tg_lists_for_master(_system)
                if merged is not None:
                    _tmout, ts1_nums, ts2_nums = merged
                    new_ts1 = ",".join(str(x) for x in ts1_nums) if ts1_nums else ""
                    new_ts2 = ",".join(str(x) for x in ts2_nums) if ts2_nums else ""
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
        self._sync_subscription_store()

