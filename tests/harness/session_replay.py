"""JSONL session replay for deterministic bridge tests.

Session file format (one JSON object per line):

- ``meta`` — optional first line: ``config``, ``bridges``, ``apply_startup_bridges``, ``expect``
- ``ingress`` — inject one packet: ``channel`` (hbp|obp|unit), ``system``, ``dt`` (clock advance
  seconds before inject), and either ``packet`` shortcut or ``spec`` fields for PacketSpec
- ``packet`` shortcuts: ``voice_head``, ``voice_burst``, ``voice_term`` (+ ``base``, ``seq``, …)

Capture tap (dev only; anonymize before commit)::

    CAPTURE=1 pytest tests/replay/test_session_replay.py::test_capture_startup_voice_session -q

Writes ``tests/fixtures/sessions/_capture/<name>.jsonl`` (gitignored).
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from adn_server.domain import bytes_3, int_id
from adn_server.domain.hbp_protocol import (
    HBPF_DATA_SYNC,
    HBPF_SLT_VHEAD,
    HBPF_SLT_VTERM,
    HBPF_VOICE,
)

from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    minimal_config,
    patch_bridge_wall_time,
)

SESSION_VERSION = 1
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sessions"
_CAPTURE_DIR = FIXTURES_DIR / "_capture"

_FRAME_ALIASES: dict[str, tuple[int, int]] = {
    "vhead": (HBPF_DATA_SYNC, HBPF_SLT_VHEAD),
    "voice": (HBPF_VOICE, 0),
    "vterm": (HBPF_DATA_SYNC, HBPF_SLT_VTERM),
}


@dataclass
class SessionExpect:
    forwards: dict[str, int] = field(default_factory=dict)
    dst_id: int | None = None


@dataclass
class SessionMeta:
    version: int = SESSION_VERSION
    name: str = ""
    config: dict[str, Any] | None = None
    bridges: dict[str, list[dict[str, Any]]] | None = None
    apply_startup_bridges: bool = False
    expect: SessionExpect = field(default_factory=SessionExpect)


@dataclass
class IngressEvent:
    channel: str
    system: str
    dt: float = 0.0
    packet: str | None = None
    base: dict[str, Any] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)
    seq: int | None = None
    dtype_vseq: int | None = None


@dataclass
class SessionDefinition:
    meta: SessionMeta
    events: list[IngressEvent] = field(default_factory=list)


def bridges_from_json(raw: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    bridges: dict[str, list[dict[str, Any]]] = {}
    for key, entries in raw.items():
        out_entries: list[dict[str, Any]] = []
        for ent in entries:
            row = dict(ent)
            tgid = row.get("TGID")
            if isinstance(tgid, int):
                row["TGID"] = bytes_3(tgid)
            for list_field in ("ON", "OFF", "RESET"):
                if list_field in row:
                    row[list_field] = [
                        bytes_3(v) if isinstance(v, int) else v for v in row[list_field]
                    ]
            out_entries.append(row)
        bridges[key] = out_entries
    return bridges


def bridges_to_json(bridges: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for key, entries in bridges.items():
        serialized: list[dict[str, Any]] = []
        for ent in entries:
            row = dict(ent)
            tgid = row.get("TGID")
            if isinstance(tgid, bytes):
                row["TGID"] = int_id(tgid)
            for list_field in ("ON", "OFF", "RESET"):
                if list_field in row:
                    row[list_field] = [
                        int_id(v) if isinstance(v, bytes) else v for v in row[list_field]
                    ]
            serialized.append(row)
        out[key] = serialized
    return out


def _parse_meta(obj: dict[str, Any]) -> SessionMeta:
    expect_raw = obj.get("expect") or {}
    expect = SessionExpect(
        forwards=dict(expect_raw.get("forwards") or {}),
        dst_id=expect_raw.get("dst_id"),
    )
    return SessionMeta(
        version=int(obj.get("version", SESSION_VERSION)),
        name=str(obj.get("name", "")),
        config=obj.get("config"),
        bridges=obj.get("bridges"),
        apply_startup_bridges=bool(obj.get("apply_startup_bridges")),
        expect=expect,
    )


def _parse_ingress(obj: dict[str, Any]) -> IngressEvent:
    return IngressEvent(
        channel=str(obj["channel"]),
        system=str(obj["system"]),
        dt=float(obj.get("dt", 0.0)),
        packet=obj.get("packet"),
        base=dict(obj.get("base") or {}),
        spec=dict(obj.get("spec") or {}),
        seq=obj.get("seq"),
        dtype_vseq=obj.get("dtype_vseq"),
    )


def load_session(path: str | Path) -> SessionDefinition:
    meta = SessionMeta()
    events: list[IngressEvent] = []
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            obj = json.loads(line)
            kind = obj.get("type")
            if kind == "meta":
                meta = _parse_meta(obj)
            elif kind == "ingress":
                events.append(_parse_ingress(obj))
            else:
                raise ValueError(f"{path}:{line_no}: unknown record type {kind!r}")
    if not events:
        raise ValueError(f"{path}: no ingress events")
    return SessionDefinition(meta=meta, events=events)


def _spec_from_dict(raw: dict[str, Any]) -> PacketSpec:
    kwargs = dict(raw)
    if "frame" in kwargs:
        frame_key = str(kwargs.pop("frame"))
        ft, dv = _FRAME_ALIASES.get(frame_key, (kwargs.get("frame_type"), kwargs.get("dtype_vseq")))
        if ft is not None:
            kwargs["frame_type"] = ft
        if dv is not None:
            kwargs["dtype_vseq"] = dv
    if "payload" in kwargs and isinstance(kwargs["payload"], str):
        kwargs["payload"] = bytes.fromhex(kwargs["payload"])
    return PacketSpec(**kwargs)


def _base_spec(event: IngressEvent) -> PacketSpec:
    if event.spec:
        return _spec_from_dict(event.spec)
    return _spec_from_dict(event.base)


def _event_to_spec(event: IngressEvent) -> PacketSpec:
    base = _base_spec(event)
    shortcut = event.packet
    if shortcut == "voice_head":
        return DeterministicScenario.voice_head_spec(base)
    if shortcut == "voice_burst":
        return DeterministicScenario.voice_burst_spec(
            base,
            seq=int(event.seq if event.seq is not None else 1),
            dtype_vseq=int(event.dtype_vseq if event.dtype_vseq is not None else 1),
        )
    if shortcut == "voice_term":
        return DeterministicScenario.voice_term_spec(
            base,
            seq=int(event.seq if event.seq is not None else 99),
        )
    if shortcut:
        raise ValueError(f"unknown packet shortcut {shortcut!r}")
    return base


class SessionReplayer:
    def __init__(self, session: SessionDefinition) -> None:
        self.session = session

    @classmethod
    def from_path(cls, path: str | Path) -> SessionReplayer:
        return cls(load_session(path))

    def run(self) -> DeterministicScenario:
        meta = self.session.meta
        bridges = bridges_from_json(meta.bridges) if meta.bridges else None
        scenario = DeterministicScenario(
            config=meta.config or minimal_config(("MASTER-A", "MASTER-B")),
            bridges=bridges,
        )
        if meta.apply_startup_bridges:
            scenario.bridge.apply_startup_bridges()

        with patch_bridge_wall_time(scenario.clock):
            for event in self.session.events:
                if event.dt:
                    scenario.clock.advance(event.dt)
                spec = _event_to_spec(event)
                if event.channel == "hbp":
                    scenario.inject_hbp(event.system, spec)
                elif event.channel == "obp":
                    scenario.inject_obp(event.system, spec)
                elif event.channel == "unit":
                    scenario.inject_unit(event.system, spec)
                else:
                    raise ValueError(f"unknown channel {event.channel!r}")
        return scenario

    def assert_expectations(self, scenario: DeterministicScenario) -> None:
        expect = self.session.meta.expect
        for system, count in expect.forwards.items():
            assert_forwarded(
                scenario,
                system,
                count=count,
                dst_id=expect.dst_id,
            )


def replay_session(path: str | Path) -> DeterministicScenario:
    replayer = SessionReplayer.from_path(path)
    scenario = replayer.run()
    replayer.assert_expectations(scenario)
    return scenario


def iter_fixture_sessions() -> Iterator[Path]:
    if not FIXTURES_DIR.is_dir():
        return
    yield from sorted(FIXTURES_DIR.glob("*.jsonl"))


def config_to_json(config: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe config (ints for SERVER_ID / NETWORK_ID bytes, empty passphrase strings)."""
    out = copy.deepcopy(config)
    global_cfg = out.get("GLOBAL")
    if isinstance(global_cfg, dict):
        sid = global_cfg.get("SERVER_ID")
        if isinstance(sid, bytes):
            global_cfg["SERVER_ID"] = int.from_bytes(sid, "big")
    for syscfg in out.get("SYSTEMS", {}).values():
        if not isinstance(syscfg, dict):
            continue
        nid = syscfg.get("NETWORK_ID")
        if isinstance(nid, bytes):
            syscfg["NETWORK_ID"] = int.from_bytes(nid, "big")
        pp = syscfg.get("PASSPHRASE")
        if isinstance(pp, bytes):
            syscfg["PASSPHRASE"] = ""
    return out


def _json_sanitize(val: Any) -> Any:
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace") if val else ""
    if isinstance(val, dict):
        return {k: _json_sanitize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_json_sanitize(v) for v in val]
    if isinstance(val, tuple):
        return [_json_sanitize(v) for v in val]
    return val


@dataclass
class SessionCapture:
    meta: SessionMeta
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_ingress(self, event: IngressEvent) -> None:
        row: dict[str, Any] = {
            "type": "ingress",
            "channel": event.channel,
            "system": event.system,
            "dt": event.dt,
        }
        if event.packet:
            row["packet"] = event.packet
        if event.base:
            row["base"] = event.base
        if event.spec:
            row["spec"] = event.spec
        if event.seq is not None:
            row["seq"] = event.seq
        if event.dtype_vseq is not None:
            row["dtype_vseq"] = event.dtype_vseq
        self.events.append(row)

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta_row: dict[str, Any] = {
            "type": "meta",
            "version": self.meta.version,
            "name": self.meta.name,
            "apply_startup_bridges": self.meta.apply_startup_bridges,
        }
        if self.meta.config is not None:
            meta_row["config"] = config_to_json(self.meta.config)
        if self.meta.bridges is not None:
            meta_row["bridges"] = _json_sanitize(self.meta.bridges)
        if self.meta.expect.forwards or self.meta.expect.dst_id is not None:
            meta_row["expect"] = {
                "forwards": self.meta.expect.forwards,
                "dst_id": self.meta.expect.dst_id,
            }
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(meta_row, separators=(",", ":")) + "\n")
            for row in self.events:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    @staticmethod
    def capture_path(name: str) -> Path:
        safe = name.replace("/", "_").replace("::", "__")
        return _CAPTURE_DIR / f"{safe}.jsonl"


def capture_enabled() -> bool:
    return os.environ.get("CAPTURE", "").strip().lower() in ("1", "true", "yes")
