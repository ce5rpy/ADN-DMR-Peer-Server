# ADN DMR Peer Server - tests talker alias format
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

"""Talker Alias formatting and stream state."""

from __future__ import annotations

from tests.harness.deterministic import PacketSpec
from tests.harness.scenarios import make_talker_alias_use_cases, talker_alias_config

from adn_server.application.talker_alias_use_cases import format_talker_alias_text
from adn_server.domain import bytes_3


def test_format_talker_alias_from_subscriber_profile() -> None:
    config = talker_alias_config()
    text = format_talker_alias_text(config, bytes_3(3120001))
    assert text == "CE5RPY Rodrigo"


def test_talker_alias_clear_stream_allows_resend() -> None:
    ta = make_talker_alias_use_cases(talker_alias_config())
    stream_id = PacketSpec(stream_id=0x93939393).data()[16:20]
    key = ("MASTER-B", stream_id)

    assert ta.should_send_on_vhead("MASTER-B", stream_id) is True
    ta.mark_dmra_sent("MASTER-B", stream_id, kind="inject")
    assert ta.should_send_on_vhead("MASTER-B", stream_id) is False

    ta.clear_stream("MASTER-B", stream_id)
    assert key not in ta._sent_streams
    assert ta.should_send_on_vhead("MASTER-B", stream_id) is True


def test_clear_dmra_sent_preserves_embed_log_dedupe() -> None:
    ta = make_talker_alias_use_cases(talker_alias_config())
    stream_id = PacketSpec(stream_id=0x93939393).data()[16:20]
    ta._embed_logged.add(("MASTER-A", "MASTER-B", stream_id))

    ta.clear_dmra_sent("MASTER-B", stream_id)
    assert ("MASTER-A", "MASTER-B", stream_id) in ta._embed_logged
