"""CLI and integrated parrot entry (Phase 4)."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from adn_server.main import main


def test_parrot_flag_routes_to_run_parrot() -> None:
    with (
        patch("adn_server.main.run_parrot") as mock_run,
        patch("adn_server.main.YamlConfigLoader") as mock_loader_cls,
        patch("adn_server.main.setup_logging") as mock_log,
    ):
        mock_loader_cls.return_value.load.return_value = {"GLOBAL": {"SERVER_ID": 9990}, "LOGGER": {}}
        mock_log.return_value = _FakeLogger()
        with patch.object(sys, "argv", ["adn-server", "--parrot", "-c", "/tmp/adn-parrot.yaml"]):
            main()
    mock_run.assert_called_once()


def test_no_proxy_skips_proxy_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """--no-proxy must not call start_proxy_service at bridge startup."""
    import adn_server.main as main_mod

    calls: list[str] = []

    def _track(*_a, **_k):
        calls.append("proxy")
        raise AssertionError("proxy should not start")

    monkeypatch.setattr(main_mod, "start_proxy_service", _track)
    monkeypatch.setattr(main_mod, "run_parrot", lambda *_a, **_k: None)
    monkeypatch.setattr(main_mod.reactor, "run", lambda: None)
    monkeypatch.setattr(main_mod, "ReportServerFactory", lambda *a, **k: _FakeReportFactory())
    monkeypatch.setattr(main_mod, "create_report_mqtt_publisher", lambda *_: None)
    monkeypatch.setattr(main_mod, "start_report_queue_worker", lambda *_a, **_k: None)
    monkeypatch.setattr(main_mod, "DefaultAliasLoader", _FakeAliasLoader)
    monkeypatch.setattr(main_mod, "PickleSubMapStore", _FakeSubMapStore)
    monkeypatch.setattr(main_mod, "JsonKeysStore", lambda *_: None)
    monkeypatch.setattr(main_mod, "DefaultSecurityDownloader", lambda *_: None)
    monkeypatch.setattr(main_mod, "UserPasswordsLoader", lambda *_: _FakeUserPw())
    monkeypatch.setattr(main_mod, "DefaultVoiceProvider", lambda *_: None)
    monkeypatch.setattr(main_mod, "RecordingHandler", lambda *_: None)
    monkeypatch.setattr(main_mod, "IdentUseCases", lambda *_: _FakeIdent())
    monkeypatch.setattr(main_mod, "HBPProtocolFactory", lambda *a, **k: object())

    config = {
        "GLOBAL": {"SERVER_ID": 1},
        "LOGGER": {},
        "ALIASES": {"PATH": "."},
        "REPORTS": {"REPORT": False},
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

    def set_bridges(self, *_a, **_k):
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
