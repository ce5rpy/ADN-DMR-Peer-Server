"""Talker Alias embedded LC (encode_emblc) paths."""

from __future__ import annotations

from tests.harness.scenarios import make_talker_alias_use_cases, talker_alias_config
from tests.talker_alias.test_passthrough import _complete_blocks, _passthrough_config
from adn_server.domain import bytes_3, bytes_4


def test_embedded_emblc_inject_mode_returns_blocks() -> None:
    ta = make_talker_alias_use_cases(talker_alias_config())
    stream_id = bytes_4(0xD1D1D1D1)

    result = ta.embedded_emblc_for_stream(
        "MASTER-A",
        bytes_3(3120001),
        stream_id,
        lambda _s, _st: None,
        target_system="MASTER-B",
    )

    assert result is not None
    emblcs, count = result
    assert 1 <= count <= 4
    assert len(emblcs) == count


def test_embedded_emblc_disabled_returns_none() -> None:
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS"] = False
    ta = make_talker_alias_use_cases(config)

    assert (
        ta.embedded_emblc_for_stream(
            "MASTER-A",
            bytes_3(3120001),
            bytes_4(0xD2D2D2D2),
            lambda _s, _st: None,
        )
        is None
    )


def test_embedded_emblc_passthrough_reencodes_source_ta() -> None:
    """passthrough overlays the source TA (re-encoded) once its blocks are complete."""
    config = _passthrough_config()
    ta = make_talker_alias_use_cases(config)
    blocks = _complete_blocks("CE5RPY embed")

    # No source TA yet -> only the destination group LC is sent (None overlay).
    assert (
        ta.embedded_emblc_for_stream(
            "MASTER-A", bytes_3(3120001), bytes_4(0xD3D3D3D3), lambda _s, _st: None,
        )
        is None
    )
    # Source TA complete -> re-encode it as the overlay.
    result = ta.embedded_emblc_for_stream(
        "MASTER-A", bytes_3(3120001), bytes_4(0xD3D3D3D4), lambda _s, _st: blocks,
    )
    assert result is not None
    emblcs, count = result
    assert count >= 1
    assert len(emblcs) == count


def test_embedded_emblc_both_source_ta_then_fallback() -> None:
    """both overlays the source TA when present, and the template when none arrives."""
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    ta = make_talker_alias_use_cases(config)
    blocks = _complete_blocks("Radio TA")

    # Source TA present -> overlay the source TA (re-encoded).
    source = ta.embedded_emblc_for_stream(
        "MASTER-A", bytes_3(9999999), bytes_4(0xD4D4D4D4), lambda _s, _st: blocks,
    )
    assert source is not None
    # No source TA yet -> legacy both injects the template embedded LC at VHEAD.
    assert (
        ta.embedded_emblc_for_stream(
            "MASTER-A", bytes_3(9999999), bytes_4(0xD4D4D4D5), lambda _s, _st: None,
        )
        is not None
    )
    # No source TA, fallback -> inject the template embedded LC.
    fallback = ta.embedded_emblc_for_stream(
        "MASTER-A",
        bytes_3(9999999),
        bytes_4(0xD5D5D5D5),
        lambda _s, _st: None,
        fallback_inject=True,
    )
    assert fallback is not None
    emblcs, count = fallback
    assert count >= 1
    assert len(emblcs) == count
