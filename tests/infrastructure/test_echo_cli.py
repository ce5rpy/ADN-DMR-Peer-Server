# ADN DMR Peer Server - tests infrastructure echo cli
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

"""CLI and integrated echo entry."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from adn_server.main import main


def test_echo_flag_routes_to_run_echo() -> None:
    with (
        patch("adn_server.main.run_echo") as mock_run,
        patch("adn_server.main.YamlConfigLoader") as mock_loader_cls,
        patch("adn_server.main.setup_logging") as mock_log,
    ):
        mock_loader_cls.return_value.load.return_value = {"GLOBAL": {"SERVER_ID": 9990}, "LOGGER": {}}
        mock_log.return_value = _FakeLogger()
        with patch.object(sys, "argv", ["adn-server", "--echo", "-c", "/tmp/adn-echo.yaml"]):
            main()
    mock_run.assert_called_once()


def test_no_proxy_skips_proxy_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """--no-proxy must not call start_proxy_service at bridge startup."""
    import adn_server.infrastructure.bootstrap.peer_server as peer_mod
    import adn_server.main as main_mod
    from twisted.internet import reactor

    calls: list[str] = []

    def _track(*_a, **_k):
        calls.append("proxy")
        raise AssertionError("proxy should not start")

    monkeypatch.setattr(peer_mod, "start_proxy_service", _track)
    monkeypatch.setattr(main_mod, "run_echo", lambda *_a, **_k: None)
    monkeypatch.setattr(reactor, "run", lambda: None)
    monkeypatch.setattr(peer_mod, "ReportServerFactory", lambda *a, **k: _FakeReportFactory())
    monkeypatch.setattr(peer_mod, "create_report_mqtt_publisher", lambda *_: None)
    monkeypatch.setattr(peer_mod, "start_report_queue_worker", lambda *_a, **_k: None)
    monkeypatch.setattr(peer_mod, "DefaultAliasLoader", _FakeAliasLoader)
    monkeypatch.setattr(peer_mod, "PickleSubMapStore", _FakeSubMapStore)
    monkeypatch.setattr(peer_mod, "JsonKeysStore", lambda *_: None)
    monkeypatch.setattr(peer_mod, "DefaultSecurityDownloader", lambda *_: None)
    monkeypatch.setattr(peer_mod, "UserPasswordsLoader", lambda *_: _FakeUserPw())
    monkeypatch.setattr(peer_mod, "DefaultVoiceProvider", lambda *_: None)
    monkeypatch.setattr(peer_mod, "RecordingHandler", lambda *_: None)
    monkeypatch.setattr(peer_mod, "IdentUseCases", lambda *_: _FakeIdent())
    monkeypatch.setattr(peer_mod, "HBPProtocolFactory", lambda *a, **k: object())
    monkeypatch.setattr(peer_mod, "ensure_database_sync", lambda *_a, **_k: True)
    monkeypatch.setattr(peer_mod, "create_mysql_pool", lambda *_a, **_k: object())
    monkeypatch.setattr(peer_mod, "MysqlDynamicTgRepository", lambda *_a, **_k: object())

    config = {
        "GLOBAL": {"SERVER_ID": 1},
        "LOGGER": {},
        "ALIASES": {"PATH": "."},
        "REPORTS": {"REPORT": False},
        "DATABASE": {
            "DB_SERVER": "localhost",
            "DB_USERNAME": "hbmon",
            "DB_PASSWORD": "x",
            "DB_NAME": "hbmon",
            "DB_PORT": 3306,
        },
        "PROXY": {"LISTEN_PORT": 62031, "TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {"MODE": "MASTER", "ENABLED": True, "IP": "127.0.0.1", "PORT": 62030, "MAX_PEERS": 4},
        },
    }

    with patch("adn_server.main.YamlConfigLoader") as mock_loader_cls:
        loader = mock_loader_cls.return_value
        loader.load.return_value = config
        loader.load_voice_config.return_value = None
        with patch("adn_server.main.setup_logging") as mock_log:
            mock_log.return_value = _FakeLogger()
            with patch.object(sys, "argv", ["adn-server", "--no-proxy", "-c", "/tmp/adn-server.yaml"]):
                try:
                    main()
                except Exception:
                    pass
    assert calls == []


class _FakeLogger:
    def info(self, *_a, **_k):
        pass

    def debug(self, *_a, **_k):
        pass

    def error(self, *_a, **_k):
        pass

    def warning(self, *_a, **_k):
        pass


class _FakeReportFactory:
    def set_systems(self, *_a, **_k):
        pass

    def set_routing_table(self, *_a, **_k):
        pass

    def set_config(self, *_a, **_k):
        pass


class _FakeAliasLoader:
    def load_aliases(self, *_a, **_k):
        return ({}, {}, {}, {}, {}, {})

    def load_subscriber_profiles(self, *_a, **_k):
        return {}


class _FakeSubMapStore:
    def load(self, *_a, **_k):
        return {}


class _FakeUserPw:
    def load(self, *_a, **_k):
        pass


class _FakeIdent:
    def run_ident(self):
        pass
