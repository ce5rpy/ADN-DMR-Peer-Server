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
