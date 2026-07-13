# ADN DMR Peer Server - voice use cases
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

"""Voice/AMBE/TTS: scheduled announcements, TTS announcements, playback. Orchestrates VoiceProvider."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable

from ..domain import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, bytes_3, bytes_4
from .ports import VoiceProvider

logger = logging.getLogger(__name__)

_FRAME_INTERVAL = 0.058
_ANNOUNCEMENT_EXCLUDED = ("ECHO", "D-APRS")
_BROADCAST_GAP = 1.5


class VoiceUseCases:
    """Use cases for voice announcements and TTS."""

    def __init__(
        self,
        voice_provider: VoiceProvider,
        config: dict[str, Any],
        get_protocols: Callable[[], dict[str, Any]] | None = None,
        call_from_reactor: Callable[..., None] | None = None,
        audio_path: str | None = None,
        routing_table_for_report: Callable[[], dict[str, list[dict[str, Any]]]] | None = None,
        call_later: Callable[..., Any] | None = None,
        start_looping_call: Callable[[Callable[[], None], float, bool], Any] | None = None,
        defer_to_thread: Callable[..., Any] | None = None,
    ) -> None:
        self._voice = voice_provider
        self._config = config
        self._get_protocols = get_protocols
        self._call_from_reactor = call_from_reactor
        self._audio_path = audio_path or ""
        self._routing_table_for_report = routing_table_for_report
        self._call_later = call_later
        self._start_looping_call = start_looping_call
        self._defer_to_thread = defer_to_thread
        self._ann_tasks: dict[int, Any] = {}
        self._tts_tasks: dict[int, Any] = {}
        self._announcement_running: dict[int, bool] = {}
        self._tts_running: dict[int, bool] = {}
        self._announcement_last_hour: dict[int, int] = {}
        self._tts_last_hour: dict[int, int] = {}
        self._broadcast_queue: list[dict[str, Any]] = []
        self._broadcast_active_tgs: set[str] = set()
        self._broadcast_active_slots: set[tuple[str, int]] = set()
        self._broadcast_slot_hold: dict[str, set[tuple[str, int]]] = {}

    def _slot_keys(self, targets: list[dict[str, Any]]) -> set[tuple[str, int]]:
        return {(t["name"], t["ts"]) for t in targets}

    def _can_start_broadcast(self, tg: int, targets: list[dict[str, Any]]) -> bool:
        if str(tg) in self._broadcast_active_tgs:
            return False
        return not (self._slot_keys(targets) & self._broadcast_active_slots)

    def _begin_broadcast(self, tg: int, targets: list[dict[str, Any]]) -> None:
        tg_key = str(tg)
        keys = self._slot_keys(targets)
        self._broadcast_active_tgs.add(tg_key)
        self._broadcast_active_slots.update(keys)
        self._broadcast_slot_hold[tg_key] = keys
        self._mark_slots_busy(targets)

    def _end_broadcast_slots(self, tg: int, targets: list[dict[str, Any]]) -> None:
        tg_key = str(tg)
        keys = self._broadcast_slot_hold.pop(tg_key, set())
        self._broadcast_active_slots -= keys
        self._broadcast_active_tgs.discard(tg_key)
        self._mark_slots_free(targets)

    def get_ambe_words(self, languages: str, audio_path: str) -> dict[str, dict[str, Any]]:
        """Load AMBE words for given languages (legacy readAMBE.readfiles)."""
        return self._voice.get_ambe_words(languages, audio_path)

    def pkt_gen(self, rf_src: bytes, dst_id: bytes, peer: bytes, slot: int, phrase: list[Any]) -> Any:
        """Generate HBP voice packets for phrase (legacy mk_voice.pkt_gen)."""
        return self._voice.pkt_gen(rf_src, dst_id, peer, slot, phrase)

    def _build_announcement_targets(
        self, tg_int: int, tg_str: str, label: str
    ) -> tuple[list[dict[str, Any]], int]:
        """MASTER systems with active bridge for tg_int and idle slot (legacy target list).

        Returns (targets, busy_count). busy_count increments when a candidate slot is skipped
        because a QSO is active (RX/TX not VTERM), for anti-collision retry scheduling.
        """
        targets: list[dict[str, Any]] = []
        busy_count = 0
        protocols = self._get_protocols() if self._get_protocols else {}
        systems_cfg = self._config.get("SYSTEMS", {})
        bridges = self._routing_table_for_report() if self._routing_table_for_report else {}
        bridge_entries = bridges.get(tg_str, [])
        for sys_name in list(protocols.keys()):
            if sys_name in _ANNOUNCEMENT_EXCLUDED or any(
                sys_name.startswith(ex + "-") for ex in _ANNOUNCEMENT_EXCLUDED
            ):
                continue
            if sys_name not in systems_cfg or systems_cfg[sys_name].get("MODE") != "MASTER":
                continue
            if not systems_cfg[sys_name].get("PEERS"):
                continue
            has_peers = any(
                systems_cfg[sys_name]["PEERS"].get(pid, {}).get("CALLSIGN")
                for pid in systems_cfg[sys_name]["PEERS"]
            )
            if not has_peers or sys_name not in protocols:
                continue
            sys_obj = protocols[sys_name]
            if not getattr(sys_obj, "STATUS", None):
                continue
            active_slots = [
                be["TS"] for be in bridge_entries
                if be.get("SYSTEM") == sys_name and be.get("ACTIVE") and be.get("TS") is not None
            ]
            active_slots = list(dict.fromkeys(active_slots))
            if not active_slots:
                continue
            for ts in active_slots:
                slot_index = 2 if ts == 2 else 1
                slot = sys_obj.STATUS.get(slot_index)
                if not slot:
                    continue
                rx_type = slot.get("RX_TYPE")
                tx_type = slot.get("TX_TYPE")
                if (rx_type != HBPF_SLT_VTERM) or (tx_type != HBPF_SLT_VTERM):
                    logger.debug("(%s) System %s TS%s busy (QSO active), skipping", label, sys_name, ts)
                    busy_count += 1
                    continue
                targets.append({"sys_obj": sys_obj, "name": sys_name, "slot": slot, "ts": ts})
        return targets, busy_count

    def _send_filtered_by_tg(
        self, sys_obj: Any, pkt: bytes, tg: int, ts: int, bridges: dict[str, list[dict[str, Any]]]
    ) -> int:
        """Return -1 if sent, 0 if TG/TS not active (legacy _sendFilteredByTG)."""
        tg_str = str(tg)
        for be in bridges.get(tg_str, []):
            if be.get("SYSTEM") == getattr(sys_obj, "_system", None) and be.get("TS") == ts and be.get("ACTIVE"):
                sys_obj.send_system(pkt)
                return -1
        return 0

    def _mark_slots_busy(self, targets: list[dict[str, Any]]) -> None:
        """Mark target slots busy (TX_TYPE=VHEAD) to prevent TS conflict."""
        server_rfs = bytes_3(5000)
        now = time.time()
        for t in targets:
            try:
                slot = t.get("slot")
                if slot is not None:
                    slot["TX_TYPE"] = HBPF_SLT_VHEAD
                    slot["TX_TIME"] = now
                    slot["TX_RFS"] = server_rfs
            except (KeyError, TypeError):
                pass

    def _mark_slots_free(self, targets: list[dict[str, Any]]) -> None:
        """Mark target slots free (TX_TYPE=VTERM) when broadcast done."""
        for t in targets:
            try:
                slot = t.get("slot")
                if slot is not None:
                    slot["TX_TYPE"] = HBPF_SLT_VTERM
            except (KeyError, TypeError):
                pass

    def _enqueue_broadcast(
        self, _type: str, targets: list[dict[str, Any]], pkts_by_ts: dict[int, list[bytes]],
        source_id: bytes, dst_id: bytes, tg: int, num: int, label: str,
    ) -> None:
        if not self._can_start_broadcast(tg, targets):
            self._broadcast_queue.append({
                'type': _type, 'targets': targets, 'pkts_by_ts': pkts_by_ts,
                'source_id': source_id, 'dst_id': dst_id, 'tg': tg, 'num': num, 'label': label,
            })
            _pos = len(self._broadcast_queue)
            logger.info(
                '(%s) Enqueued broadcast for TG %s (position %s in queue; slot or TG busy)',
                label,
                tg,
                _pos,
            )
        else:
            self._begin_broadcast(tg, targets)
            logger.info('(%s) Starting broadcast immediately for TG %s (active TGs: %s)', label, tg, len(self._broadcast_active_tgs))
            if self._call_later:
                if _type == 'ann':
                    self._call_later(0.5, self._announcement_send_broadcast, targets, pkts_by_ts, 0, source_id, dst_id, tg, num, label, None)
                elif _type == 'tts':
                    self._call_later(0.5, self._tts_send_broadcast, targets, pkts_by_ts, 0, source_id, dst_id, tg, num, label, None)

    def _start_next_broadcast(self) -> None:
        if not self._broadcast_queue:
            return
        _next = None
        for i, _item in enumerate(self._broadcast_queue):
            if self._can_start_broadcast(_item['tg'], _item['targets']):
                _next = self._broadcast_queue.pop(i)
                break
        if not _next:
            return
        _type = _next['type']
        _label = _next['label']
        self._begin_broadcast(_next['tg'], _next['targets'])
        logger.info('(%s) Starting broadcast from queue for TG %s (%s remaining, active TGs: %s)', _label, _next['tg'], len(self._broadcast_queue), len(self._broadcast_active_tgs))
        if self._call_later:
            if _type == 'ann':
                self._call_later(0.5, self._announcement_send_broadcast, _next['targets'], _next['pkts_by_ts'], 0, _next['source_id'], _next['dst_id'], _next['tg'], _next['num'], _label, None)
            elif _type == 'tts':
                self._call_later(0.5, self._tts_send_broadcast, _next['targets'], _next['pkts_by_ts'], 0, _next['source_id'], _next['dst_id'], _next['tg'], _next['num'], _label, None)

    def _broadcast_finished(self, tg: int | None = None) -> None:
        if tg is not None:
            self._broadcast_active_tgs.discard(str(tg))
        if self._broadcast_queue:
            logger.info('(QUEUE) Broadcast finished for TG %s, checking queue (%s queued, active TGs: %s)', tg, len(self._broadcast_queue), len(self._broadcast_active_tgs))
            if self._call_later:
                self._call_later(_BROADCAST_GAP, self._start_next_broadcast)
        else:
            if not self._broadcast_active_tgs:
                logger.info('(QUEUE) All broadcasts finished, queue empty')
            else:
                logger.info('(QUEUE) Broadcast finished for TG %s, %s TGs still active', tg, len(self._broadcast_active_tgs))

    def _announcement_send_broadcast(
        self,
        targets: list[dict[str, Any]],
        pkts_by_ts: dict[int, list[bytes]],
        pkt_idx: int,
        source_id: bytes,
        dst_id: bytes,
        tg: int,
        ann_idx: int,
        label: str,
        next_time: float | None = None,
    ) -> None:
        """Send one batch of packets; schedule next via call_later."""
        total = len(pkts_by_ts.get(1, []))
        if pkt_idx >= total or not targets:
            self._end_broadcast_slots(tg, targets)
            for t in targets:
                try:
                    obj = t.get("sys_obj")
                    if getattr(obj, "STATUS", None):
                        for sid in list(obj.STATUS.keys()):
                            if sid not in (1, 2):
                                del obj.STATUS[sid]
                except Exception as e:
                    logger.warning("(%s) slot STATUS cleanup failed: %s", label, e)
            self._announcement_running[ann_idx] = False
            if not targets:
                logger.info(
                    "(%s) Broadcast aborted at packet %s/%s: all targets removed (QSO collision)",
                    label,
                    pkt_idx,
                    total,
                )
            else:
                logger.info("(%s) Broadcast complete: %s packets sent to %s targets", label, total, len(targets))
            self._broadcast_finished(tg)
            return
        collided: list[dict[str, Any]] = []
        for t in targets:
            slot = t["slot"]
            if slot.get("RX_TYPE") != HBPF_SLT_VTERM:
                logger.info(
                    "(%s) QSO detected on %s/TS%s during broadcast (packet %s/%s), removing target",
                    label,
                    t["name"],
                    t["ts"],
                    pkt_idx,
                    total,
                )
                slot["TX_TYPE"] = HBPF_SLT_VTERM
                collided.append(t)
        for t in collided:
            targets.remove(t)
        if not targets:
            self._announcement_running[ann_idx] = False
            logger.info(
                "(%s) Broadcast stopped: all targets had QSO collision at packet %s/%s",
                label,
                pkt_idx,
                total,
            )
            self._end_broadcast_slots(tg, collided)
            self._broadcast_finished(tg)
            return
        bridges = self._routing_table_for_report() if self._routing_table_for_report else {}
        now = time.time()
        for t in targets:
            try:
                sys_obj = t["sys_obj"]
                slot = t["slot"]
                t_ts = t["ts"]
                pkt = pkts_by_ts[t_ts][pkt_idx]
                stream_id = pkt[16:20]
                if stream_id not in sys_obj.STATUS:
                    sys_obj.STATUS[stream_id] = {
                        "START": now,
                        "CONTENTION": False,
                        "RFS": source_id,
                        "TGID": dst_id,
                        "LAST": now,
                    }
                    slot["TX_TGID"] = dst_id
                    slot["TX_RFS"] = source_id
                else:
                    sys_obj.STATUS[stream_id]["LAST"] = now
                slot["TX_TIME"] = now
                self._send_filtered_by_tg(sys_obj, pkt, tg, t_ts, bridges)
            except Exception as e:
                logger.error("(%s) Error sending packet %s to %s/TS%s: %s", label, pkt_idx, t.get("name"), t.get("ts"), e)
        if next_time is None:
            next_time = now + _FRAME_INTERVAL
        else:
            next_time = next_time + _FRAME_INTERVAL
        delay = max(0.001, next_time - time.time())
        if self._call_later:
            self._call_later(
                delay,
                self._announcement_send_broadcast,
                targets,
                pkts_by_ts,
                pkt_idx + 1,
                source_id,
                dst_id,
                tg,
                ann_idx,
                label,
                next_time,
            )

    def scheduled_announcement(self, ann_idx: int = 0, _retry: int = 0) -> None:
        """Run one scheduled file announcement from ANNOUNCEMENTS[ann_idx]."""
        g = self._config.get("VOICE", {})
        announcements = g.get("ANNOUNCEMENTS") or []
        if ann_idx < 0 or ann_idx >= len(announcements):
            return
        item = announcements[ann_idx]
        if not isinstance(item, dict) or not item.get("ENABLED"):
            return
        label = "ANNOUNCEMENT-{}".format(ann_idx + 1)
        if self._announcement_running.get(ann_idx):
            if _retry == 0:
                logger.debug("(%s) Previous announcement still running, skipping", label)
            return
        mode = item.get("MODE", "interval")
        if mode == "hourly" and _retry == 0:
            now = datetime.now()
            if now.minute != 0:
                return
            if self._announcement_last_hour.get(ann_idx) == now.hour:
                return
        _tg = int(item.get("TG", 0))
        if str(_tg) in self._broadcast_active_tgs and _retry < 60:
            if _retry == 0:
                logger.debug("(%s) Same TG %s already broadcasting, deferring prep", label, _tg)
            if self._call_later:
                self._call_later(3.0 + ann_idx * 0.5, self.scheduled_announcement, ann_idx, _retry + 1)
            return
        _file = str(item.get("FILE") or "").strip()
        _lang = item.get("LANGUAGE", "en_GB")
        if not _file or not _tg:
            return
        _dst_id = bytes_3(_tg)
        _source_id = bytes_3(5000)
        server_id = self._config.get("GLOBAL", {}).get("SERVER_ID", b"\x00\x00\x00\x00")
        if not isinstance(server_id, bytes):
            server_id = bytes_3(int(server_id))
        logger.info("(%s) Playing file: %s to TG %s (both TS, mode: %s, lang: %s)", label, _file, _tg, mode, _lang)
        try:
            _say = self.read_single_file(self._audio_path, _lang, str(_file))
        except Exception as e:
            logger.warning("(%s) Cannot read AMBE file: Audio/%s/ondemand/%s.ambe: %s", label, _lang, _file, e)
            return
        if not _say:
            logger.warning("(%s) AMBE file empty or not found: %s/ondemand/%s.ambe", label, _lang, _file)
            return
        tg_str = str(_tg)
        targets, busy_count = self._build_announcement_targets(_tg, tg_str, label)
        if not targets:
            if busy_count > 0 and _retry < 60:
                if _retry == 0:
                    logger.info(
                        "(%s) All %s target slots busy (QSO active), waiting for QSO to finish...",
                        label,
                        busy_count,
                    )
                if self._call_later:
                    self._call_later(5.0, self.scheduled_announcement, ann_idx, _retry + 1)
                return
            logger.info("(%s) No systems with active bridge for TG %s to send to", label, _tg)
            return
        if mode == "hourly":
            self._announcement_last_hour[ann_idx] = datetime.now().hour
        _say_list = [_say]
        pkts_by_ts = {
            1: list(self.pkt_gen(_source_id, _dst_id, server_id, 0, _say_list)),
            2: list(self.pkt_gen(_source_id, _dst_id, server_id, 1, _say_list)),
        }
        ts1_count = sum(1 for t in targets if t["ts"] == 1)
        ts2_count = sum(1 for t in targets if t["ts"] == 2)
        sys_names = ", ".join("{}/TS{}".format(t["name"], t["ts"]) for t in targets[:8])
        if len(targets) > 8:
            sys_names += ", ... +{}".format(len(targets) - 8)
        logger.info(
            "(%s) Broadcasting %s packets to %s targets (TS1:%s TS2:%s): %s",
            label, len(pkts_by_ts[1]), len(targets), ts1_count, ts2_count, sys_names,
        )
        self._announcement_running[ann_idx] = True
        self._enqueue_broadcast('ann', targets, pkts_by_ts, _source_id, _dst_id, _tg, ann_idx, label)

    def scheduled_tts_announcement(self, tts_idx: int = 0, _retry: int = 0) -> None:
        """Run one scheduled TTS announcement from TTS_ANNOUNCEMENTS[tts_idx]."""
        g = self._config.get("VOICE", {})
        tts_list = g.get("TTS_ANNOUNCEMENTS") or []
        if tts_idx < 0 or tts_idx >= len(tts_list):
            return
        item = tts_list[tts_idx]
        if not isinstance(item, dict) or not item.get("ENABLED", False):
            return
        label = "TTS-{}".format(tts_idx + 1)
        if self._tts_running.get(tts_idx):
            if _retry == 0:
                logger.debug("(%s) Previous TTS announcement still running, skipping", label)
            return
        mode = item.get("MODE", "interval")
        if mode == "hourly" and _retry == 0:
            now = datetime.now()
            if now.minute != 0:
                return
            if self._tts_last_hour.get(tts_idx) == now.hour:
                return
        _tg = int(item.get("TG", 0))
        if str(_tg) in self._broadcast_active_tgs and _retry < 60:
            if _retry == 0:
                logger.debug("(%s) Same TG %s already broadcasting, deferring TTS prep", label, _tg)
            if self._call_later:
                self._call_later(3.0 + tts_idx * 0.5, self.scheduled_tts_announcement, tts_idx, _retry + 1)
            return
        _file = str(item.get("FILE") or "").strip()
        _lang = item.get("LANGUAGE", "en_GB")
        self._tts_running[tts_idx] = True
        logger.info("(%s) Starting TTS conversion in background thread for %s", label, _file)
        if self._defer_to_thread:
            d = self._defer_to_thread(self._voice.ensure_tts_ambe, self._config, item, self._audio_path)
            d.addCallback(self._tts_conversion_done, tts_idx, _file, _tg, _lang, mode, label)
            d.addErrback(self._tts_conversion_error, tts_idx, label)
        else:
            try:
                ambe_path = self._voice.ensure_tts_ambe(self._config, item, self._audio_path)
                self._tts_conversion_done(ambe_path, tts_idx, _file, _tg, _lang, mode, label)
            except Exception as e:
                self._tts_conversion_error(e, tts_idx, label)

    def _tts_conversion_done(
        self, ambe_path: str | None, tts_idx: int, _file: str, _tg: int, _lang: str, mode: str, label: str, _retry: int = 0
    ) -> None:
        """After TTS conversion: broadcast like scheduled_announcement."""
        if not ambe_path:
            self._tts_running[tts_idx] = False
            logger.warning("(%s) No AMBE file available for TTS announcement %s", label, _file)
            return
        if str(_tg) in self._broadcast_active_tgs and _retry < 60:
            if _retry == 0:
                logger.debug("(%s) Same TG %s already broadcasting, deferring TTS packet prep", label, _tg)
            if self._call_later:
                self._call_later(3.0 + tts_idx * 0.5, self._tts_conversion_done, ambe_path, tts_idx, _file, _tg, _lang, mode, label, _retry + 1)
            return
        logger.info("(%s) Playing TTS file: %s to TG %s (both TS, mode: %s, lang: %s)", label, _file, _tg, mode, _lang)
        _dst_id = bytes_3(_tg)
        _source_id = bytes_3(5000)
        server_id = self._config.get("GLOBAL", {}).get("SERVER_ID", b"\x00\x00\x00\x00")
        if not isinstance(server_id, bytes):
            server_id = bytes_3(int(server_id))
        _file_base = _file.replace(".ambe", "")
        _say = self.read_single_file(self._audio_path, _lang, _file_base)
        if not _say:
            logger.warning("(%s) Cannot read AMBE file: %s", label, ambe_path)
            self._tts_running[tts_idx] = False
            return
        tg_str = str(_tg)
        targets, busy_count = self._build_announcement_targets(_tg, tg_str, label)
        if not targets:
            if busy_count > 0 and _retry < 60:
                if _retry == 0:
                    logger.info(
                        "(%s) All %s target slots busy (QSO active), waiting for QSO to finish...",
                        label,
                        busy_count,
                    )
                if self._call_later:
                    self._call_later(
                        5.0,
                        self._tts_conversion_done,
                        ambe_path,
                        tts_idx,
                        _file,
                        _tg,
                        _lang,
                        mode,
                        label,
                        _retry + 1,
                    )
                return
            self._tts_running[tts_idx] = False
            logger.info("(%s) No systems with active bridge for TG %s to send to", label, _tg)
            return
        if mode == "hourly":
            self._tts_last_hour[tts_idx] = datetime.now().hour
        _say_list = [_say]
        pkts_by_ts = {
            1: list(self.pkt_gen(_source_id, _dst_id, server_id, 0, _say_list)),
            2: list(self.pkt_gen(_source_id, _dst_id, server_id, 1, _say_list)),
        }
        logger.info("(%s) Broadcasting %s packets to %s targets", label, len(pkts_by_ts[1]), len(targets))
        self._enqueue_broadcast('tts', targets, pkts_by_ts, _source_id, _dst_id, _tg, tts_idx, label)

    def _tts_conversion_error(self, failure: Any, tts_idx: int, label: str) -> None:
        self._tts_running[tts_idx] = False
        try:
            msg = failure.getErrorMessage()
        except Exception as e:
            logger.warning("(%s) failure.getErrorMessage unavailable: %s", label, e)
            msg = str(failure)
        logger.error("(%s) TTS conversion error: %s", label, msg)

    def _tts_send_broadcast(
        self,
        targets: list[dict[str, Any]],
        pkts_by_ts: dict[int, list[bytes]],
        pkt_idx: int,
        source_id: bytes,
        dst_id: bytes,
        tg: int,
        tts_idx: int,
        label: str,
        next_time: float | None = None,
    ) -> None:
        """Same as _announcement_send_broadcast but clears _tts_running."""
        total = len(pkts_by_ts.get(1, []))
        if pkt_idx >= total or not targets:
            self._end_broadcast_slots(tg, targets)
            for t in targets:
                try:
                    obj = t.get("sys_obj")
                    if getattr(obj, "STATUS", None):
                        for sid in list(obj.STATUS.keys()):
                            if sid not in (1, 2):
                                del obj.STATUS[sid]
                except Exception as e:
                    logger.warning("(%s) slot STATUS cleanup failed: %s", label, e)
            self._tts_running[tts_idx] = False
            if not targets:
                logger.info(
                    "(%s) Broadcast aborted at packet %s/%s: all targets removed (QSO collision)",
                    label,
                    pkt_idx,
                    total,
                )
            else:
                logger.info("(%s) Broadcast complete: %s packets sent to %s targets", label, total, len(targets))
            self._broadcast_finished(tg)
            return
        collided: list[dict[str, Any]] = []
        for t in targets:
            slot = t["slot"]
            if slot.get("RX_TYPE") != HBPF_SLT_VTERM:
                logger.info(
                    "(%s) QSO detected on %s/TS%s during broadcast (packet %s/%s), removing target",
                    label,
                    t["name"],
                    t["ts"],
                    pkt_idx,
                    total,
                )
                slot["TX_TYPE"] = HBPF_SLT_VTERM
                collided.append(t)
        for t in collided:
            targets.remove(t)
        if not targets:
            self._tts_running[tts_idx] = False
            logger.info(
                "(%s) Broadcast stopped: all targets had QSO collision at packet %s/%s",
                label,
                pkt_idx,
                total,
            )
            self._end_broadcast_slots(tg, collided)
            self._broadcast_finished(tg)
            return
        bridges = self._routing_table_for_report() if self._routing_table_for_report else {}
        now = time.time()
        for t in targets:
            try:
                sys_obj = t["sys_obj"]
                slot = t["slot"]
                t_ts = t["ts"]
                pkt = pkts_by_ts[t_ts][pkt_idx]
                stream_id = pkt[16:20]
                if stream_id not in sys_obj.STATUS:
                    sys_obj.STATUS[stream_id] = {
                        "START": now,
                        "CONTENTION": False,
                        "RFS": source_id,
                        "TGID": dst_id,
                        "LAST": now,
                    }
                    slot["TX_TGID"] = dst_id
                    slot["TX_RFS"] = source_id
                else:
                    sys_obj.STATUS[stream_id]["LAST"] = now
                slot["TX_TIME"] = now
                self._send_filtered_by_tg(sys_obj, pkt, tg, t_ts, bridges)
            except Exception as e:
                logger.error("(%s) Error sending packet %s to %s: %s", label, pkt_idx, t.get("name"), e)
        if next_time is None:
            next_time = now + _FRAME_INTERVAL
        else:
            next_time = next_time + _FRAME_INTERVAL
        delay = max(0.001, next_time - time.time())
        if self._call_later:
            self._call_later(
                delay,
                self._tts_send_broadcast,
                targets,
                pkts_by_ts,
                pkt_idx + 1,
                source_id,
                dst_id,
                tg,
                tts_idx,
                label,
                next_time,
            )

    def read_single_file(self, audio_path: str, lang: str, file_number: str) -> list:
        """Read one AMBE file (e.g. ondemand/{file_number}.ambe). Legacy readSingleFile."""
        return self._voice.read_single_file(audio_path, lang, file_number)

    def play_file_on_request(self, file_number: str, system: str) -> None:
        """Play AMBE file on request (legacy playFileOnRequest). TG 9991-9999 triggers this."""
        if not self._get_protocols or not self._call_from_reactor or not self._audio_path:
            return
        protocol = self._get_protocols().get(system)
        if not protocol or not getattr(protocol, "STATUS", None):
            return
        sys_cfg = self._config.get("SYSTEMS", {}).get(system, {})
        lang = sys_cfg.get("ANNOUNCEMENT_LANGUAGE", "en_GB")
        pairs = self.read_single_file(self._audio_path, lang, file_number)
        if not pairs:
            logger.warning("(%s) AMBE file not found or empty: %s/ondemand/%s.ambe", system, lang, file_number)
            return
        logger.info("(%s) Playing on-demand AMBE file: %s (ID: %s)", system, file_number, file_number)
        time.sleep(1)
        _say = [pairs]
        speech = self.pkt_gen(bytes_3(5000), bytes_3(9), bytes_4(9), 1, _say)
        time.sleep(1)
        _slot = protocol.STATUS.get(2)
        if not _slot:
            return
        _source_id = bytes_3(5000)
        _dst_id = bytes_3(9)
        _next_time = time.time()
        _pkt_count = 0
        for pkt in speech:
            _next_time += 0.058
            delay = _next_time - time.time()
            if delay > 0.001:
                time.sleep(delay)
            self._call_from_reactor(protocol.send_voice_packet, pkt, _source_id, _dst_id, _slot)
            _pkt_count += 1
        logger.info("(%s) On-demand playback complete: %s (%d packets)", system, file_number, _pkt_count)

    def disconnected_voice(self, system: str) -> None:
        """Send 'disconnected' / 'linked to reflector' voice (legacy disconnectedVoice). Run from thread."""
        if not self._get_protocols or not self._call_from_reactor or not self._audio_path:
            return
        protocol = self._get_protocols().get(system)
        if not protocol or not getattr(protocol, "STATUS", None):
            return
        sys_cfg = self._config.get("SYSTEMS", {}).get(system, {})
        _lang = sys_cfg.get("ANNOUNCEMENT_LANGUAGE", "en_GB")
        words_by_lang = self.get_ambe_words(_lang, self._audio_path)
        if _lang not in words_by_lang:
            return
        words = words_by_lang[_lang]
        silence = words.get("silence")
        if not silence:
            return
        _say = [silence, silence]
        default_refl = int(sys_cfg.get("DEFAULT_REFLECTOR", 0))
        if default_refl > 0:
            _say.append(silence)
            _say.append(words.get("linkedto") or silence)
            _say.append(silence)
            _say.append(words.get("to") or silence)
            _say.append(silence)
            _say.append(silence)
            for digit in str(default_refl):
                _say.append(words.get(digit) or silence)
                _say.append(silence)
        else:
            _say.append(words.get("notlinked") or silence)
        _say.append(silence)
        speech = self.pkt_gen(bytes_3(5000), bytes_3(9), bytes_4(9), 1, _say)
        time.sleep(1)
        _slot = protocol.STATUS.get(2)
        if not _slot:
            return
        logger.debug("(%s) Sending disconnected voice", system)
        _next_time = time.time()
        for pkt in speech:
            _next_time += 0.058
            _delay = _next_time - time.time()
            if _delay > 0.001:
                time.sleep(_delay)
            self._call_from_reactor(protocol.send_voice_packet, pkt, bytes_3(5000), bytes_3(9), _slot)
        logger.debug("(%s) disconnected voice thread end", system)

    def apply_voice_config(self) -> None:
        """Start/stop announcement and TTS LoopingCalls from ``config["VOICE"]``."""
        g = self._config.get("VOICE", {})
        if not self._start_looping_call:
            return
        announcements = g.get("ANNOUNCEMENTS") or []
        if not isinstance(announcements, list):
            announcements = []
        for ann_idx in list(self._ann_tasks.keys()):
            if ann_idx >= len(announcements) or not (isinstance(announcements[ann_idx], dict) and announcements[ann_idx].get("ENABLED")):
                try:
                    if getattr(self._ann_tasks[ann_idx], "running", False):
                        self._ann_tasks[ann_idx].stop()
                except Exception as e:
                    logger.warning("(VOICE-RELOAD) stop announcement task %s failed: %s", ann_idx + 1, e)
                del self._ann_tasks[ann_idx]
                logger.info("(VOICE-RELOAD) ANNOUNCEMENT-%s stopped", ann_idx + 1)
        for ann_idx, item in enumerate(announcements):
            if not isinstance(item, dict) or not item.get("ENABLED"):
                continue
            label = "ANNOUNCEMENT-{}".format(ann_idx + 1)
            if ann_idx in self._ann_tasks:
                try:
                    if getattr(self._ann_tasks[ann_idx], "running", False):
                        self._ann_tasks[ann_idx].stop()
                except Exception as e:
                    logger.warning("(VOICE-RELOAD) stop %s failed: %s", label, e)
                del self._ann_tasks[ann_idx]
                logger.info("(VOICE-RELOAD) %s stopped", label)
            mode = item.get("MODE", "interval")
            interval = 30.0 if mode == "hourly" else float(item.get("INTERVAL", 60))
            lc = self._start_looping_call(lambda ai=ann_idx: self.scheduled_announcement(ai), interval, False)
            self._ann_tasks[ann_idx] = lc
            logger.info(
                "(VOICE-RELOAD) %s enabled - mode: %s, file: %s, TG: %s",
                label, mode, item.get("FILE"), item.get("TG"),
            )
        tts_list = g.get("TTS_ANNOUNCEMENTS") or []
        if not isinstance(tts_list, list):
            tts_list = []
        for tts_idx in list(self._tts_tasks.keys()):
            if tts_idx >= len(tts_list) or not (isinstance(tts_list[tts_idx], dict) and tts_list[tts_idx].get("ENABLED")):
                try:
                    if getattr(self._tts_tasks[tts_idx], "running", False):
                        self._tts_tasks[tts_idx].stop()
                except Exception as e:
                    logger.warning("(VOICE-RELOAD) stop TTS task %s failed: %s", tts_idx + 1, e)
                del self._tts_tasks[tts_idx]
                logger.info("(VOICE-RELOAD) TTS-%s stopped", tts_idx + 1)
        for tts_idx, item in enumerate(tts_list):
            if not isinstance(item, dict) or not item.get("ENABLED"):
                continue
            label = "TTS-{}".format(tts_idx + 1)
            if tts_idx in self._tts_tasks:
                try:
                    if getattr(self._tts_tasks[tts_idx], "running", False):
                        self._tts_tasks[tts_idx].stop()
                except Exception as e:
                    logger.warning("(VOICE-RELOAD) stop %s failed: %s", label, e)
                del self._tts_tasks[tts_idx]
                logger.info("(VOICE-RELOAD) %s stopped", label)
            mode = item.get("MODE", "interval")
            interval = 30.0 if mode == "hourly" else float(item.get("INTERVAL", 60))
            lc = self._start_looping_call(lambda ti=tts_idx: self.scheduled_tts_announcement(ti), interval, False)
            self._tts_tasks[tts_idx] = lc
            logger.info(
                "(VOICE-RELOAD) %s enabled - mode: %s, file: %s, TG: %s",
                label, mode, item.get("FILE"), item.get("TG"),
            )
