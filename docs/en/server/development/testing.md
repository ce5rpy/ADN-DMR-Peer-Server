# Testing

Regression tests live under **`tests/`**, **one topic per file**, grouped by domain (`bridge/`, `hbp/`, `obp/`, …). See **[`tests/README.md`](../../../tests/README.md)** for the full file index.

They use an in-process **deterministic harness** (no Twisted reactor, no UDP sockets).

## Install dev dependencies

```bash
python3 -m pip install -e ".[dev]"
```

Use the project interpreter, e.g. `/opt/.pyenv/versions/3.11.8/bin/python3`.

## Run tests

Full suite:

```bash
python3 -m pytest tests/ -q
```

**By domain** (while working on one area):

```bash
python3 -m pytest tests/bridge/ -q
python3 -m pytest tests/hbp/ -q
python3 -m pytest tests/parrot/ -q
```

**By file** (recommended for point checks):

```bash
python3 -m pytest tests/bridge/test_unit_data_routing.py -q
python3 -m pytest tests/parrot/test_rekey_playback.py -q
```

**Single test**:

```bash
python3 -m pytest tests/bridge/test_startup_bridges.py::test_startup_bridge_routes_voice_after_apply -q
```

Collect only:

```bash
python3 -m pytest tests/ --collect-only -q
```

## Markers

Registered in `pyproject.toml`:

| Marker | Use |
|--------|-----|
| `@pytest.mark.behavior` | Integration-style regression (P0/P1) |
| `@pytest.mark.smoke` | Quick routing smoke checks |

## Harness overview

| Component | Role |
|-----------|------|
| `DeterministicScenario` | Wires `BridgeUseCases` with fakes and packet capture |
| `inject_hbp` / `inject_unit` / `inject_obp` | Public ingress paths into `dmrd_received` |
| `PacketCapture` | Records outbound `send_to_system` + parsed DMR fields |
| `FakeReportSender` + `ReportingUseCases` | Reporting events (via `scenario.report_factory.events`) |
| `tests/harness/assertions.py` | Reusable asserts: `assert_forwarded`, `assert_report_event`, … |

Full audit (scores, red-test table, inventory): internal `docs-priv/en/test-audit.md` in maintainer checkouts.

## Writing a regression test

1. Docstring: **Regression:** if X breaks, this test fails because Y.
2. Prefer a **dedicated file** (or the smallest existing file for the same topic).
3. Enter through a public path (`inject_*`, use-case API, or `@pytest.mark.unit` for pure domain).
4. Assert an **observable** outcome (capture, `master.sent`, report strings), not only private flags.
5. Add a negative path where behaviour differs.
6. **Red-test:** break the production condition → test must fail → revert.
7. Mark `@pytest.mark.behavior` or `@pytest.mark.unit`.

Do not chase coverage percentage; chase regressions operators would notice on RF.

## v2 policy

Each v2 feature branch should include or extend regression tests in the same PR. Baseline task **V2-TST-001** tracks bringing `tests/` into the repo on `develop`.
