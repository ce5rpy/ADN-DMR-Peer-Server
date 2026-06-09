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
