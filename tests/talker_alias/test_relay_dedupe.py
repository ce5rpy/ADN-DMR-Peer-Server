# ADN DMR Peer Server - tests talker alias relay dedupe
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

"""Talker Alias DMRA relay and log deduplication."""

from __future__ import annotations

from adn_server.application.routing_use_cases import RoutingUseCases
from adn_server.domain import bytes_3, bytes_4
from adn_server.infrastructure.acl_router import InMemoryAclRouter
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder
from adn_server.domain.dmr.bptc import encode_emblc

from tests.harness.scenarios import make_talker_alias_use_cases, talker_alias_config
from tests.talker_alias.test_mmdvm_wire import mmdvm_wire_blocks


def test_should_resend_passthrough_only_after_inject() -> None:
    ta = make_talker_alias_use_cases(talker_alias_config())
    stream_id = bytes_4(0xA1B2C3D4)

    assert ta.should_resend_passthrough_dmra("SYSTEM", stream_id) is True
    ta.mark_dmra_sent("SYSTEM", stream_id, kind="inject")
    assert ta.should_resend_passthrough_dmra("SYSTEM", stream_id) is True
    ta.mark_dmra_sent("SYSTEM", stream_id, kind="passthrough")
    assert ta.should_resend_passthrough_dmra("SYSTEM", stream_id) is False


def test_on_dmra_fragment_stored_relays_passthrough_once() -> None:
    """Second completion callback must not re-send passthrough DMRA on the same stream."""
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    config["SYSTEMS"]["MASTER-A"]["REPEAT"] = True
    blocks = mmdvm_wire_blocks("CE5RPY")
    sent: list[str] = []
    stream_id = bytes_4(0xB1B2B3B4)

    def _send_dmra(
        target_system: str,
        packets: list[bytes],
        exclude_peer: bytes | None = None,
        **kwargs: object,
    ) -> int:
        sent.append(target_system)
        return 1

    class _Proto:
        STATUS = {
            2: {
                "TX_STREAM_ID": stream_id,
                "TX_TGID": bytes_3(52090),
            }
        }

    bridge = RoutingUseCases(
        InMemoryAclRouter(),
        config,
        InMemorySubscriptionStore(),
        send_dmra_to_system=_send_dmra,
        get_protocols=lambda: {"MASTER-A": _Proto()},
        get_dmra_blocks=lambda _sys, _sid: blocks,
        encode_emblc=encode_emblc,
        ta_emblc_encoder=default_ta_emblc_encoder,
    )
    peer = bytes_4(1001)
    rf_src = bytes_3(3120001)

    bridge.on_dmra_fragment_stored("MASTER-A", peer, rf_src, stream_id)
    first_count = len(sent)
    assert first_count == 1

    bridge.on_dmra_fragment_stored("MASTER-A", peer, rf_src, stream_id)
    assert len(sent) == first_count
