# ADN DMR Peer Server - tests infrastructure config reload udp
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

"""Hot reload UDP bind: GENERATOR collapse and deferred port release."""

from __future__ import annotations

from typing import Any

import pytest
from twisted.internet import defer

from adn_server.infrastructure.config_loader import YamlConfigLoader
from adn_server.infrastructure.config_reload import (
    ReloadResult,
    _generator_collapse_renames,
    reload_server_config,
)

pytestmark = pytest.mark.usefixtures("reactor")


class _FakePort:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stopListening(self) -> defer.Deferred:
        self.stop_calls += 1
        return defer.succeed(None)


class _FakeProto:
    def __init__(self, name: str) -> None:
        self.name = name
        self.dereg_called = False

    def dereg(self) -> None:
        self.dereg_called = True

    def apply_system_config(self, _config: dict[str, Any]) -> None:
        return None


def _base_config() -> dict[str, Any]:
    return {
        "GLOBAL": {},
        "SYSTEMS": {
            "D-APRS-0": {
                "MODE": "MASTER",
                "ENABLED": True,
                "IP": "",
                "PORT": 52555,
                "PEERS": {"peer": {"CONNECTION": "YES"}},
            },
            "D-APRS-1": {
                "MODE": "MASTER",
                "ENABLED": True,
                "IP": "",
                "PORT": 52556,
            },
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "IP": "127.0.0.1",
                "PORT": 54917,
            },
        },
    }


def _incoming_collapsed_d_aprs() -> dict[str, Any]:
    return {
        "GLOBAL": {},
        "SYSTEMS": {
            "D-APRS": {
                "MODE": "MASTER",
                "ENABLED": True,
                "GENERATOR": 1,
                "IP": "",
                "PORT": 52555,
            },
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "IP": "127.0.0.1",
                "PORT": 54917,
            },
        },
    }


def test_generator_collapse_maps_instance_zero_to_parent() -> None:
    old = _base_config()["SYSTEMS"]
    new = _incoming_collapsed_d_aprs()["SYSTEMS"]
    renames = _generator_collapse_renames(old, new, {"D-APRS-0", "D-APRS-1", "ECHO"})
    assert renames == {"D-APRS-0": "D-APRS"}


@pytest.fixture
def reactor():
    from twisted.internet import reactor as tw_reactor

    yield tw_reactor


def test_reload_collapsed_generator_migrates_listener_without_rebind() -> None:
    """GENERATOR 2 -> 1: keep D-APRS-0 UDP socket, remove only D-APRS-1."""
    config = _base_config()
    protocols = {
        "D-APRS-0": _FakeProto("D-APRS-0"),
        "D-APRS-1": _FakeProto("D-APRS-1"),
        "ECHO": _FakeProto("ECHO"),
    }
    port0 = _FakePort()
    port1 = _FakePort()
    transports = {"D-APRS-0": port0, "D-APRS-1": port1, "ECHO": _FakePort()}
    listen_calls: list[tuple[str, int]] = []

    class _Loader(YamlConfigLoader):
        def load(self, _path: str) -> dict[str, Any]:
            return _incoming_collapsed_d_aprs()

    def _listen(name: str, bind: Any, _proto: Any) -> _FakePort:
        listen_calls.append((name, bind.port))
        return _FakePort()

    result_holder: list[ReloadResult] = []

    def _done(result: ReloadResult) -> None:
        result_holder.append(result)

    reload_server_config(
        config,
        "adn-server.yaml",
        _Loader(),
        protocols,
        transports,
        create_protocol=lambda name: _FakeProto(name),
        listen_udp=_listen,
        stop_listener=lambda port: port.stopListening() if port else None,
    ).addCallback(_done)

    from twisted.internet import reactor

    reactor.runUntilCurrent()

    assert len(result_holder) == 1
    result = result_holder[0]
    assert result.removed == ["D-APRS-1"]
    assert "D-APRS" in result.updated
    assert "D-APRS-0" not in result.removed
    assert listen_calls == []
    assert port1.stop_calls == 1
    assert port0.stop_calls == 0
    assert "D-APRS" in protocols
    assert "D-APRS-0" not in protocols
    assert transports["D-APRS"] is port0


def test_reload_defers_rebind_until_stop_completes() -> None:
    """Port change must wait for stopListening before listenUDP on the new port."""
    config = {
        "GLOBAL": {},
        "SYSTEMS": {
            "APR": {
                "MODE": "MASTER",
                "ENABLED": True,
                "IP": "",
                "PORT": 52555,
                "PEERS": {},
            },
        },
    }
    protocols = {"APR": _FakeProto("APR")}
    listen_calls: list[int] = []
    stop_fired = defer.Deferred()

    class _SlowPort(_FakePort):
        def stopListening(self) -> defer.Deferred:
            self.stop_calls += 1
            return stop_fired

    transports: dict[str, Any] = {"APR": _SlowPort()}

    class _Loader(YamlConfigLoader):
        def load(self, _path: str) -> dict[str, Any]:
            return {
                "GLOBAL": {},
                "SYSTEMS": {
                    "APR": {
                        "MODE": "MASTER",
                        "ENABLED": True,
                        "IP": "",
                        "PORT": 52556,
                    },
                },
            }

    def _listen(_name: str, bind: Any, _proto: Any) -> _FakePort:
        listen_calls.append(bind.port)
        return _FakePort()

    reload_server_config(
        config,
        "adn-server.yaml",
        _Loader(),
        protocols,
        transports,
        create_protocol=lambda name: _FakeProto(name),
        listen_udp=_listen,
        stop_listener=lambda port: port.stopListening() if port else None,
    )

    from twisted.internet import reactor

    reactor.runUntilCurrent()
    assert listen_calls == []

    stop_fired.callback(None)
    reactor.runUntilCurrent()
    assert listen_calls == [52556]
