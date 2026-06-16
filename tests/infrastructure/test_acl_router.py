# ADN DMR Peer Server - tests infrastructure acl router
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

"""ACL range checks (legacy acl_check parity)."""

from __future__ import annotations

from adn_server.infrastructure.acl_router import InMemoryAclRouter


def test_acl_permit_in_range() -> None:
    router = InMemoryAclRouter()
    assert router.acl_check(100, (True, [(1, 200)])) is True


def test_acl_deny_out_of_range() -> None:
    router = InMemoryAclRouter()
    assert router.acl_check(300, (True, [(1, 200)])) is False


def test_acl_invert_action() -> None:
    router = InMemoryAclRouter()
    assert router.acl_check(50, (False, [(1, 100)])) is False
    assert router.acl_check(150, (False, [(1, 100)])) is True


def test_acl_bytes_id() -> None:
    router = InMemoryAclRouter()
    assert router.acl_check(b"\x00\x00\x64", (True, [(1, 200)])) is True
