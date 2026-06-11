# ADN DMR Peer Server - bridge HBP forward path
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""HBP ingress packet control and unit-data forward (no Twisted imports)."""

from __future__ import annotations

import logging
from hashlib import blake2b

from ...domain import HBPF_SLT_VTERM, STREAM_TO, int_id

logger = logging.getLogger(__name__)


class HbpForwardMixin:
    """routerHBP group voice ingress controls and sendDataToHBP."""

    def _hbp_group_voice_ingress_controls(
        self,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        seq: int,
        slot: int,
        stream_id: bytes,
        data: bytes,
        pkt_time: float,
    ) -> bool:
        """Legacy routerHBP group/vcsbk packet control (~3270-3399).

        Returns True when the packet may proceed to bridge routing; False when dropped.
        Uses ingress ``pkt_time`` (UDP receive time) for rate/timeout parity with legacy.
        """
        protocols = self._get_protocols() if self._get_protocols else {}
        src_proto = protocols.get(system_name)
        if not src_proto:
            return True
        systems_cfg = self._config.get("SYSTEMS", {})
        _slot_st = getattr(src_proto, "STATUS", {}).get(slot, {})
        _is_new_stream = stream_id != _slot_st.get("RX_STREAM_ID")
        if _is_new_stream:
            _slot_st["packets"] = 0
            _slot_st["loss"] = 0
            _slot_st["crcs"] = set()
            _slot_st["LOOPLOG"] = False
            _slot_st.pop("_bcsq", None)
            _slot_st["lastSeq"] = False
            _slot_st["lastData"] = False
            if (
                _slot_st.get("RX_TYPE") != HBPF_SLT_VTERM
                and pkt_time < (_slot_st.get("RX_TIME", 0) + STREAM_TO)
                and rf_src != _slot_st.get("RX_RFS", b"\x00")
            ):
                logger.warning(
                    "(%s) Packet received with STREAM ID: %s <FROM> SUB: %s PEER: %s <TO> TGID %s, SLOT %s collided with existing call",
                    system_name, int_id(stream_id), int_id(rf_src), int_id(peer_id), int_id(dst_id), slot,
                )
                return False
            _slot_st["RX_START"] = pkt_time
        _slot_st["packets"] = _slot_st.get("packets", 0) + 1
        _pkts = _slot_st["packets"]
        _rx_start = _slot_st.get("RX_START", pkt_time)
        if _pkts > 18 and _rx_start < pkt_time:
            _rate = _pkts / (pkt_time - _rx_start)
            if _rate > 25:
                logger.warning(
                    "(%s) *PacketControl* RATE DROP! Stream ID: %s TGID: %s",
                    system_name, int_id(stream_id), int_id(dst_id),
                )
                _slot_st["LAST"] = pkt_time
                return False
        if _rx_start + 180 < pkt_time:
            if not _slot_st.get("LOOPLOG"):
                logger.info(
                    "(%s) HBP *SOURCE TIMEOUT* STREAM ID: %s, TG: %s, TS: %s, IGNORE THIS SOURCE",
                    system_name, int_id(stream_id), int_id(dst_id), slot,
                )
                _slot_st["LOOPLOG"] = True
            _slot_st["LAST"] = pkt_time
            return False
        for other_name, proto in protocols.items():
            if other_name == system_name:
                continue
            omode = systems_cfg.get(other_name, {}).get("MODE")
            ostatus = getattr(proto, "STATUS", None)
            if not ostatus:
                continue
            if omode != "OPENBRIDGE":
                for _sysslot in ostatus:
                    ss = ostatus.get(_sysslot)
                    if isinstance(ss, dict) and stream_id == ss.get("RX_STREAM_ID"):
                        if not _slot_st.get("LOOPLOG"):
                            logger.debug(
                                "(%s) HBP *LoopControl* FIRST HBP: %s, STREAM ID: %s, TG: %s, TS: %s, IGNORE THIS SOURCE",
                                system_name, other_name, int_id(stream_id), int_id(dst_id), _sysslot,
                            )
                            _slot_st["LOOPLOG"] = True
                        _slot_st["LAST"] = pkt_time
                        return False
            else:
                if (
                    stream_id in ostatus
                    and "1ST" in ostatus[stream_id]
                    and ostatus[stream_id].get("TGID") == dst_id
                ):
                    if not _slot_st.get("LOOPLOG"):
                        logger.debug(
                            "(%s) HBP *LoopControl* FIRST OBP %s, STREAM ID: %s, TG %s, IGNORE THIS SOURCE",
                            system_name, other_name, int_id(stream_id), int_id(dst_id),
                        )
                        _slot_st["LOOPLOG"] = True
                    _slot_st["LAST"] = pkt_time
                    if (
                        systems_cfg.get(system_name, {}).get("ENHANCED_OBP")
                        and "_bcsq" not in _slot_st
                    ):
                        if hasattr(src_proto, "_obp_send_bcsq"):
                            src_proto._obp_send_bcsq(dst_id, stream_id)
                        _slot_st["_bcsq"] = True
                    return False
        if _slot_st.get("lastData") and _slot_st["lastData"] == data and seq > 1:
            _slot_st["loss"] = _slot_st.get("loss", 0) + 1
            logger.debug(
                "(%s) *PacketControl* last packet is a complete duplicate, discarding. Stream ID: %s TGID: %s",
                system_name, int_id(stream_id), int_id(dst_id),
            )
            return False
        if seq and seq == _slot_st.get("lastSeq"):
            _slot_st["loss"] = _slot_st.get("loss", 0) + 1
            return False
        if seq and _slot_st.get("lastSeq") and seq != 1 and seq < _slot_st.get("lastSeq", 0):
            _slot_st["loss"] = _slot_st.get("loss", 0) + 1
            return False
        _h = blake2b(digest_size=16)
        _h.update(data)
        _pkt_crc = _h.digest()
        if seq > 0 and "crcs" in _slot_st and _pkt_crc in _slot_st["crcs"]:
            _slot_st["loss"] = _slot_st.get("loss", 0) + 1
            return False
        if seq and _slot_st.get("lastSeq") and seq > (_slot_st.get("lastSeq", 0) + 1):
            _slot_st["loss"] = _slot_st.get("loss", 0) + 1
        _slot_st["lastSeq"] = seq
        _slot_st["lastData"] = data
        if "crcs" in _slot_st:
            _slot_st["crcs"].add(_pkt_crc)
        return True


    def _send_data_to_hbp(
        self,
        source_system: str,
        d_system: str,
        d_slot: int,
        dst_id: bytes,
        tmp_bits: int,
        data: bytes,
        dmrpkt: bytes,
        rf_src: bytes,
        stream_id: bytes,
        peer_id: bytes,
    ) -> None:
        """Legacy sendDataToHBP: forward a unit-data packet to an HBP (MASTER/PEER) target."""
        _tmp_data = b"".join([data[:15], tmp_bits.to_bytes(1, "big"), data[16:20], dmrpkt])
        try:
            self._send_to_system(d_system, _tmp_data)
        except Exception as exc:
            logger.warning("(%s) send_data_to_hbp %s failed: %s", source_system, d_system, exc)
            return
        logger.debug("(%s) UNIT Data Bridged to HBP System: %s DST_ID: %s", source_system, d_system, int_id(dst_id))
        self._send_routing_event(
            "UNIT DATA,DATA,TX,{},{},{},{},{},{}".format(
                d_system, int_id(stream_id), int_id(peer_id), int_id(rf_src), 1, int_id(dst_id),
            )
        )

