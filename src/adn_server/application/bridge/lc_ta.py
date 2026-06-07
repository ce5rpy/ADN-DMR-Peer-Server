# ADN DMR Peer Server - bridge LC / Talker Alias (V2-P0-004)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Embedded LC rewrite and Talker Alias bridge coordination (no Twisted)."""

from __future__ import annotations

import logging
from typing import Any

from bitarray import bitarray

from ...domain.talker_alias import DMRA_BLOCK_COUNT
from ...domain import int_id
from ..talker_alias_use_cases import passthrough_complete, talker_alias_settings
from .helpers import EMB_LC_SLICE

logger = logging.getLogger(__name__)


class BridgeLcTaMixin:
    """Talker Alias DMRA relay and embedded LC overlay on forward legs."""

    def _get_stream_dmra_blocks(self, source_system: str, stream_id: bytes) -> dict[int, bytes] | None:
        if not self._get_dmra_blocks:
            return None
        return self._get_dmra_blocks(source_system, stream_id)

    def _both_ta_key(self, source_system: str, stream_id: bytes) -> tuple[str, bytes]:
        return (source_system, stream_id)

    def _source_cannot_carry_ta(self, source_system: str) -> bool:
        """OpenBridge carries no Talker Alias (no DMRA UDP nor embedded LC TA).

        In `both` mode there is nothing to wait for, so inject the template right away
        instead of deferring (OBP streams are often short and would expire first).
        """
        return self._config.get("SYSTEMS", {}).get(source_system, {}).get("MODE") == "OPENBRIDGE"

    def _cancel_both_ta_wait(self, source_system: str, stream_id: bytes) -> None:
        wait = self._both_ta_wait.pop(self._both_ta_key(source_system, stream_id), None)
        if wait and wait.get("timer") and getattr(wait["timer"], "cancel", None):
            try:
                wait["timer"].cancel()
            except Exception:
                pass

    def _register_both_ta_wait(
        self,
        source_system: str,
        target_system: str,
        rf_src: bytes,
        stream_id: bytes,
        source_peer: bytes,
    ) -> None:
        """Defer DMRA UDP + embed inject until MMDVM fragments arrive (both mode)."""
        if not self._call_later:
            return
        key = self._both_ta_key(source_system, stream_id)
        wait = self._both_ta_wait.setdefault(
            key,
            {"rf_src": rf_src, "peer": source_peer, "targets": set()},
        )
        wait["rf_src"] = rf_src
        wait["peer"] = source_peer
        wait["targets"].add(target_system)
        if wait.get("timer"):
            return
        # Wait long enough to detect a slow source TA (MMDVM emits TA ~1 s in) before
        # falling back to inject; passthrough is applied earlier via on_dmra_fragment_stored.
        wait["timer"] = self._call_later(2.0, self._finalize_both_ta, source_system, stream_id)

    def _finalize_both_ta(self, source_system: str, stream_id: bytes) -> None:
        key = self._both_ta_key(source_system, stream_id)
        wait = self._both_ta_wait.pop(key, None)
        if not wait:
            return
        rf_src = wait["rf_src"]
        peer = wait["peer"]
        blocks = self._get_stream_dmra_blocks(source_system, stream_id)
        # No source TA within the window: fall back to inject (template).
        fallback_inject = not (blocks and passthrough_complete(blocks))
        for target_system in wait["targets"]:
            if not self._talker_alias.should_send_on_vhead(target_system, stream_id):
                continue
            self._send_talker_alias_to_target(
                source_system, target_system, rf_src, stream_id, peer,
                force=True, fallback_inject=fallback_inject,
            )
        self._apply_both_ta_embed(source_system, rf_src, stream_id, force_inject=fallback_inject)

    def _apply_both_ta_embed(
        self,
        source_system: str,
        rf_src: bytes,
        stream_id: bytes,
        *,
        force_inject: bool = False,
    ) -> None:
        """Install embed LC state once the TA decision is known (passthrough or inject)."""
        if not self._get_protocols:
            return
        for proto in self._get_protocols().values():
            status = getattr(proto, "STATUS", None)
            if not isinstance(status, dict):
                continue
            for st in status.values():
                if not isinstance(st, dict):
                    continue
                if st.get("TX_STREAM_ID") != stream_id or st.get("TX_RFS") != rf_src:
                    continue
                if st.get("TX_TA_ON"):
                    continue
                target = st.get("_ta_target_system", source_system)
                self._init_talker_alias_embed(
                    st, source_system, target, rf_src, stream_id, force_inject=force_inject,
                )

    def on_dmra_fragment_stored(
        self,
        source_system: str,
        peer_id: bytes,
        rf_src: bytes,
        stream_id: bytes,
    ) -> None:
        """Source TA may complete after VHEAD (DMRA UDP or decoded from voice).

        Once the buffer is complete, overlay the source TA on the outgoing embedded LC
        (passthrough/both). For `both` with a pending wait, also relay DMRA now and cancel
        the inject fallback.
        """
        if talker_alias_settings(self._config, source_system)["mode"] not in ("both", "passthrough"):
            return
        blocks = self._get_stream_dmra_blocks(source_system, stream_id)
        if not blocks or not passthrough_complete(blocks):
            return
        key = self._both_ta_key(source_system, stream_id)
        wait = self._both_ta_wait.get(key)
        if not wait:
            self._apply_both_ta_embed(source_system, rf_src, stream_id)
            return
        wait["peer"] = peer_id
        self._cancel_both_ta_wait(source_system, stream_id)
        for target_system in wait["targets"]:
            if self._talker_alias.should_send_on_vhead(target_system, stream_id):
                self._send_talker_alias_to_target(
                    source_system, target_system, rf_src, stream_id, peer_id, force=True,
                )
        self._apply_both_ta_embed(source_system, rf_src, stream_id)

    def _send_talker_alias_to_target(
        self,
        source_system: str,
        target_system: str,
        rf_src: bytes,
        stream_id: bytes,
        source_peer: bytes,
        *,
        force: bool = False,
        fallback_inject: bool = False,
    ) -> None:
        """Emit DMRA to an HBP target on VHEAD (once per target stream)."""
        if not self._send_dmra_to_system:
            return
        tgt_mode = self._config.get("SYSTEMS", {}).get(target_system, {}).get("MODE")
        if tgt_mode not in ("MASTER", "PEER"):
            return
        if not self._talker_alias.should_send_on_vhead(target_system, stream_id):
            return
        if (
            not force
            and talker_alias_settings(self._config, source_system)["mode"] == "both"
            and not (self._get_stream_dmra_blocks(source_system, stream_id) and passthrough_complete(
                self._get_stream_dmra_blocks(source_system, stream_id) or {}
            ))
        ):
            if self._source_cannot_carry_ta(source_system):
                # OBP source can never supply TA: inject the template immediately.
                fallback_inject = True
            else:
                self._register_both_ta_wait(
                    source_system, target_system, rf_src, stream_id, source_peer,
                )
                return
        packets = self._talker_alias.packets_for_stream(
            source_system,
            rf_src,
            stream_id,
            self._get_dmra_blocks,
            target_system=target_system,
            fallback_inject=fallback_inject,
        )
        if not packets:
            return
        exclude = source_peer if target_system == source_system else None
        try:
            peer_count = self._send_dmra_to_system(target_system, packets, exclude_peer=exclude)
        except Exception as e:
            logger.warning("(ROUTER) send_dmra_to_system %s failed: %s", target_system, e)
            return
        self._talker_alias.mark_dmra_sent(target_system, stream_id)
        sid = int_id(stream_id)
        if peer_count:
            logger.debug(
                "(%s) *TALKER ALIAS* stream %s sent %d DMRA block(s) to %d peer(s)",
                target_system, sid, len(packets), peer_count,
            )
        elif exclude:
            logger.debug(
                "(%s) *TALKER ALIAS* stream %s no DMRA sent (source peer %s excluded on repeat)",
                target_system, sid, int_id(exclude),
            )

    def send_talker_alias_local_repeat(
        self,
        system_name: str,
        source_peer: bytes,
        rf_src: bytes,
        stream_id: bytes,
    ) -> None:
        """Inject/pass-through TA to other peers on this MASTER (REPEAT path)."""
        self._send_talker_alias_to_target(
            system_name, system_name, rf_src, stream_id, source_peer,
        )

    def clear_talker_alias_stream(self, system_name: str, stream_id: bytes) -> None:
        """Release per-stream TA dedupe state after VTERM."""
        self._cancel_both_ta_wait(system_name, stream_id)
        self._talker_alias.clear_stream(system_name, stream_id)
        if not self._get_protocols:
            return
        proto = self._get_protocols().get(system_name)
        if proto is not None and hasattr(proto, "clear_ta_stream_buffer"):
            proto.clear_ta_stream_buffer(stream_id)
        if proto is None:
            return
        status = getattr(proto, "STATUS", None)
        if not isinstance(status, dict):
            return
        for slot in (1, 2):
            st = status.get(slot)
            if isinstance(st, dict) and st.get("TX_STREAM_ID") == stream_id:
                self._clear_talker_alias_embed(st)

    def _init_talker_alias_embed(
        self,
        st: dict[str, Any],
        source_system: str,
        target_system: str,
        rf_src: bytes,
        stream_id: bytes,
        *,
        force_inject: bool = False,
    ) -> None:
        """Prepare per-stream embedded TA state for DMRD voice injection.

        The group LC is always rewritten for the destination TG by ``_rewrite_embed_lc``;
        here we only set ``TX_TA_EMB`` when a Talker Alias should be overlaid. The source
        TA (passthrough/both) is re-encoded from its decoded DMRA/voice blocks once they
        arrive; the template is used for ``inject`` and the ``both`` fallback. If no TA is
        available yet (e.g. at VHEAD, before the source TA has been decoded), TX_TA_EMB is
        left unset and only the destination group LC is emitted until it becomes available.
        """
        st["_ta_source_system"] = source_system
        st["_ta_target_system"] = target_system
        settings = talker_alias_settings(self._config, source_system)
        if not settings["enabled"]:
            return
        target_mode = self._config.get("SYSTEMS", {}).get(target_system, {}).get("MODE")
        if (
            settings["mode"] == "both"
            and self._source_cannot_carry_ta(source_system)
            and target_mode in ("MASTER", "PEER")
        ):
            # OBP source can never supply TA: inject the template immediately.
            force_inject = True
        st.pop("TX_TA_EMB", None)
        st.pop("TX_TA_PHASE", None)
        st.pop("TX_TA_ON", None)
        emblcs = self._talker_alias.embedded_emblc_for_stream(
            source_system,
            rf_src,
            stream_id,
            self._get_dmra_blocks,
            target_system=target_system,
            fallback_inject=force_inject,
        )
        if emblcs:
            st["TX_TA_EMB"], st["TX_TA_BLOCK_COUNT"] = emblcs
            st["TX_TA_PHASE"] = 0
            # First B1–B4 cycle carries group LC; TA on the next cycle.
            st["TX_TA_ON"] = False

    def _rewrite_embed_lc(
        self,
        dmrbits: bitarray,
        st: dict[str, Any],
        dtype_vseq: int,
        emb_key: str,
    ) -> None:
        """Replace embedded LC on voice bursts B–E (legacy bridge.py parity).

        Group-call superframes always carry the **destination** group LC (``emb_key``),
        re-encoded for the rewritten TGID — this is required for the voice to be accepted
        by the receiving MMDVM (a mismatched embedded LC causes packet loss). When a
        Talker Alias is available (``TX_TA_EMB``: injected template or the source TA
        re-encoded from its DMRA/voice blocks) it is overlaid on alternate superframes.
        """
        if dtype_vseq not in (1, 2, 3, 4):
            return
        ta_emb = st.get("TX_TA_EMB")
        if ta_emb is not None and st.get("TX_TA_ON"):
            phase = st.get("TX_TA_PHASE", 0)
            block_count = st.get("TX_TA_BLOCK_COUNT", DMRA_BLOCK_COUNT)
            frag = ta_emb[phase][dtype_vseq]
            if dtype_vseq == 4:
                st["TX_TA_ON"] = False
                st["TX_TA_PHASE"] = (phase + 1) % block_count
        else:
            frag = st[emb_key][dtype_vseq]
            if dtype_vseq == 4 and ta_emb is not None:
                st["TX_TA_ON"] = True
        dmrbits[EMB_LC_SLICE] = frag

    def _clear_talker_alias_embed(self, st: dict[str, Any]) -> None:
        st.pop("TX_TA_EMB", None)
        st.pop("TX_TA_PHASE", None)
        st.pop("TX_TA_BLOCK_COUNT", None)
        st.pop("TX_TA_ON", None)

