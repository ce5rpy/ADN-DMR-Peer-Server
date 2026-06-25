"""Tests for scripts/freedmr_cfg_to_yaml.py."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from freedmr_cfg_to_yaml import dump_yaml, parse_freedmr_cfg  # noqa: E402


def _write_cfg(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "test.cfg"
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
    return path


def test_converts_global_echo_and_obp(tmp_path: Path) -> None:
    cfg = _write_cfg(
        tmp_path,
        """
        [GLOBAL]
        SERVER_ID: 73010
        USE_ACL: True
        TGID_TS2_ACL: PERMIT:ALL

        [REPORTS]
        REPORT: True
        REPORT_CLIENTS: 127.0.0.1

        [LOGGER]
        LOG_FILE: /var/log/FreeDMR/FreeDMR.log
        LOG_NAME: FreeDMR

        [ALIASES]
        TRY_DOWNLOAD: True
        STALE_DAYS: 1

        [ECHO]
        MODE: MASTER
        ENABLED: True
        PORT: 54917
        TS2_STATIC: 9990
        TGID_TS2_ACL: PERMIT:9990
        GENERATOR: 0

        [OBP-CR]
        MODE: OPENBRIDGE
        ENABLED: False
        PORT: 62052
        NETWORK_ID: 71210
        PASSPHRASE: passw0rd
        TARGET_IP: freedmrcr.net
        TARGET_PORT: 62026
        TGID_ACL: DENY :0-82,9990-9999
        TGID_TS1_ACL: DENY :0-89
        PROTO_VER: 5
        """,
    )
    out = parse_freedmr_cfg(cfg)

    assert out["GLOBAL"]["SERVER_ID"] == 73010
    assert out["GLOBAL"]["TALKER_ALIAS"] is False
    assert out["REPORTS"]["REPORT_CLIENTS"] == "127.0.0.1"
    assert out["LOGGER"]["LOG_FILE"] == "/var/log/adn-server/adn-server.log"
    assert out["LOGGER"]["LOG_NAME"] == "adn-server"
    assert out["ALIASES"]["KEYS_FILE"] == "keys.json"

    echo = out["SYSTEMS"]["ECHO"]
    assert echo["MODE"] == "MASTER"
    assert echo["TS2_STATIC"] == "9990"
    assert echo["TGID_TS2_ACL"] == "PERMIT:9990"

    obp = out["SYSTEMS"]["OBP-CR"]
    assert obp["ENABLED"] is False
    assert obp["TGID_ACL"] == "DENY:0-82,9990-9999"
    assert obp["TGID_TS1_ACL"] == "DENY:0-89"
    assert obp["PROTO_VER"] == 5


def test_includes_disabled_systems(tmp_path: Path) -> None:
    cfg = _write_cfg(
        tmp_path,
        """
        [OBP-OFF]
        MODE: OPENBRIDGE
        ENABLED: False
        PORT: 62099
        NETWORK_ID: 1
        PASSPHRASE: x
        TARGET_IP: 1.2.3.4
        TARGET_PORT: 62099
        """,
    )
    out = parse_freedmr_cfg(cfg)
    assert "OBP-OFF" in out["SYSTEMS"]
    assert out["SYSTEMS"]["OBP-OFF"]["ENABLED"] is False


def test_preserves_section_and_key_order(tmp_path: Path) -> None:
    cfg = _write_cfg(
        tmp_path,
        """
        [GLOBAL]
        PATH: ./
        PING_TIME: 10
        SERVER_ID: 73010

        [REPORTS]
        REPORT: True

        [ALLSTAR]
        ENABLED: False

        [ECHO]
        MODE: MASTER
        ENABLED: True
        PORT: 54917
        TS2_STATIC: 9990

        [OBP-CR]
        MODE: OPENBRIDGE
        ENABLED: False
        PORT: 62052
        NETWORK_ID: 71210
        PASSPHRASE: passw0rd
        TARGET_IP: freedmrcr.net
        TARGET_PORT: 62026
        PROTO_VER: 5
        """,
    )
    out = parse_freedmr_cfg(cfg)

    assert list(out.keys()) == ["GLOBAL", "REPORTS", "ALLSTAR", "SYSTEMS"]
    assert list(out["GLOBAL"].keys())[:3] == ["PATH", "PING_TIME", "SERVER_ID"]
    assert list(out["SYSTEMS"].keys()) == ["ECHO", "OBP-CR"]
    assert list(out["SYSTEMS"]["ECHO"].keys())[:4] == ["MODE", "ENABLED", "PORT", "TS2_STATIC"]

    text = dump_yaml(out)
    yaml_keys = [line.rstrip(":") for line in text.splitlines() if line.endswith(":") and not line.startswith("#")]
    assert yaml_keys[:4] == ["GLOBAL", "REPORTS", "ALLSTAR", "SYSTEMS"]


def test_security_fields_are_strings(tmp_path: Path) -> None:
    cfg = _write_cfg(
        tmp_path,
        """
        [GLOBAL]
        URL_SECURITY: 143.47.40.69
        PORT_SECURITY: 7070
        PASS_SECURITY: secret
        """,
    )
    out = parse_freedmr_cfg(cfg)
    assert out["GLOBAL"]["URL_SECURITY"] == "143.47.40.69"
    assert out["GLOBAL"]["PORT_SECURITY"] == "7070"
    assert out["GLOBAL"]["PASS_SECURITY"] == "secret"
    assert isinstance(out["GLOBAL"]["PORT_SECURITY"], str)


def test_fixture_matches_cfg_section_order() -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample_freedmr.cfg"
    out = parse_freedmr_cfg(fixture)
    expected_top = ["GLOBAL", "REPORTS", "LOGGER", "ALIASES", "ALLSTAR", "SYSTEMS"]
    assert list(out.keys()) == expected_top
    assert list(out["SYSTEMS"].keys()) == ["SYSTEM", "ECHO", "OBP-ES", "OBP-UY"]
    assert list(out["GLOBAL"].keys())[:5] == ["PATH", "PING_TIME", "MAX_MISSED", "USE_ACL", "REG_ACL"]
    assert out["GLOBAL"]["PORT_SECURITY"] == "7070"
    assert isinstance(out["GLOBAL"]["PORT_SECURITY"], str)


def test_dump_yaml_is_parseable(tmp_path: Path) -> None:
    cfg = _write_cfg(
        tmp_path,
        """
        [GLOBAL]
        SERVER_ID: 1
        [SYSTEM]
        MODE: MASTER
        ENABLED: True
        PORT: 56400
        PASSPHRASE: secret
        GENERATOR: 1
        """,
    )
    text = dump_yaml(parse_freedmr_cfg(cfg))
    loaded = yaml.safe_load(text.split("\n", 2)[2])
    assert loaded["SYSTEMS"]["SYSTEM"]["PORT"] == 56400
