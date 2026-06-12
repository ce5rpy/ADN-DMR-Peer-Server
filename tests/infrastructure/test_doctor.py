# ADN DMR Peer Server - tests infrastructure doctor
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

"""adn-server --doctor checks."""

from __future__ import annotations

import textwrap


from adn_server.infrastructure.doctor import collect_findings, run_doctor


def test_doctor_parrot_requires_peer_system(tmp_path) -> None:
    cfg = tmp_path / "adn-parrot.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            GLOBAL:
              SERVER_ID: 9990
            LOGGER:
              LOG_LEVEL: INFO
            SYSTEMS:
              ECHO:
                MODE: MASTER
                ENABLED: true
            """
        ),
        encoding="utf-8",
    )
    code = run_doctor(str(cfg), str(tmp_path), parrot=True, version="test")
    assert code == 1


def test_doctor_ok_minimal_peer(tmp_path) -> None:
    cfg = tmp_path / "adn-server.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            GLOBAL:
              SERVER_ID: 1
            LOGGER:
              LOG_LEVEL: INFO
            REPORTS:
              REPORT: false
            SYSTEMS:
              P1:
                MODE: PEER
                ENABLED: true
                MASTER_IP: 127.0.0.1
                MASTER_PORT: 56400
            """
        ),
        encoding="utf-8",
    )
    code = run_doctor(str(cfg), str(tmp_path), version="test")
    assert code == 0


def test_collect_findings_peer_mesh_protocol() -> None:
    config = {
        "GLOBAL": {"SERVER_ID": 1},
        "SYSTEMS": {
            "P1": {
                "MODE": "PEER",
                "ENABLED": True,
                "MASTER_IP": "127.0.0.1",
                "MASTER_PORT": 56400,
                "MESH_PROTOCOL": "dmre_v5",
            }
        },
    }
    findings = collect_findings(config, project_root=".", config_path="cfg.yaml")
    peer_msgs = [f.message for f in findings if f.section == "peer"]
    assert any("MESH_PROTOCOL=dmre_v5" in m for m in peer_msgs)
