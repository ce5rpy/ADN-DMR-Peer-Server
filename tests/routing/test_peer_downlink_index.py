# ADN DMR Peer Server - tests routing peer downlink index
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

"""Peer downlink index: inject-only fan-out narrowing."""

from __future__ import annotations

from adn_server.application.routing.peer_downlink_index import (
    build_peer_downlink_index,
    cached_peer_static_tgs,
    invalidate_peer_options_cache,
)
from adn_server.domain import bytes_4


def _peer(options: str) -> dict:
    return {"CONNECTION": "YES", "OPTIONS": options.encode()}


def test_build_index_maps_static_tgs_per_slot() -> None:
    p1 = bytes_4(730044401)
    p2 = bytes_4(730044402)
    peers = {
        p1: _peer("TS2=52090,314569;"),
        p2: _peer("TS2=730170;"),
    }
    idx = build_peer_downlink_index(peers, {})
    assert p1 in idx.candidates(2, 52090, connected_count=5)
    assert p2 not in idx.candidates(2, 52090, connected_count=5)
    assert p2 in idx.candidates(2, 730170, connected_count=5)
    assert len(idx.candidates(2, 52090, connected_count=5)) == 1


def test_single_connected_peer_returns_all() -> None:
    p1 = bytes_4(730044401)
    peers = {p1: _peer("TS2=91;")}
    idx = build_peer_downlink_index(peers, {})
    assert idx.candidates(2, 52090, connected_count=1) == frozenset({p1})


def test_options_cache_invalidates_on_rpto() -> None:
    peer = _peer("TS2=52090;")
    cached_peer_static_tgs(peer)
    assert "_CACHED_OPTIONS_STATIC" in peer
    peer["OPTIONS"] = b"TS2=730170;"
    invalidate_peer_options_cache(peer)
    ts1, ts2 = cached_peer_static_tgs(peer)
    assert "730170" in ts2
