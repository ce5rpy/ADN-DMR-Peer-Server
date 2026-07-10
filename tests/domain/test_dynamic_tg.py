"""Domain rules for peer_dynamic_tgs rows."""

from __future__ import annotations

from adn_server.domain.dynamic_tg import DynamicTgEntry, is_persisted_dynamic_row


def test_is_persisted_dynamic_row_rejects_reload_control() -> None:
    assert not is_persisted_dynamic_row(
        DynamicTgEntry(
            int_id=1,
            system_name="SYS",
            slot=0,
            tgid=0,
            single_mode=False,
            expires_at=None,
            updated_at=1.0,
            need_reload=True,
        )
    )
    assert is_persisted_dynamic_row(
        DynamicTgEntry(
            int_id=1,
            system_name="SYS",
            slot=2,
            tgid=7305,
            single_mode=True,
            expires_at=9_999.0,
            updated_at=1.0,
        )
    )
