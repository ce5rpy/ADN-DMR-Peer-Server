# ADN Parrot (Playback)

Exact port of the legacy `playback.py` to clean architecture.
Records incoming group voice calls and plays them back to the sender.

## Architecture

```
Hotspot ──► adn-server (MASTER :56400)
                │
                ├── bridge routes TG 9990 to ECHO
                │
                └── ECHO (PEER :54917) ──► adn-parrot (MASTER :54915)
                                                  │
                                                  ├── records DMRD packets
                                                  ├── waits 2 s
                                                  └── plays back with new stream ID
```

The parrot runs a **MASTER** system. The `ECHO` **PEER** (defined in `adn-server.yaml`)
connects to it. When a user transmits to TG 9990, the bridge forwards the call to
the ECHO peer, which relays it to the parrot master. The parrot records all packets,
then replays them back through the same path.

## Files

| File | Description |
|---|---|
| `adn-parrot.py` | Launcher script (like `adn-server.py`) |
| `adn-parrot.example.yaml` | Example config (copy to `adn-parrot.yaml`) |
| `src/adn_server/parrot_main.py` | Entrypoint: config loading, protocol setup, reactor |
| `src/adn_server/application/playback_use_cases.py` | Recording/playback logic (port of `playback.py`) |

## Configuration

Copy the example and set your passphrase:

```bash
cp adn-parrot.example.yaml adn-parrot.yaml
```

The config defines a single MASTER system (`PARROT`) that listens on `127.0.0.1:54915`.
The passphrase must match the one used by the ECHO peer in `adn-server.yaml`.

Key settings:

```yaml
SYSTEMS:
  PARROT:
    MODE: MASTER
    PORT: 54915            # must match ECHO.MASTER_PORT in adn-server.yaml
    PASSPHRASE: passw0rd   # must match ECHO.PASSPHRASE in adn-server.yaml
    MAX_PEERS: 1
    ALLOW_UNREG_ID: true
```

## Running

```bash
# Direct
python adn-parrot.py
python adn-parrot.py -c /path/to/adn-parrot.yaml
python adn-parrot.py --logging DEBUG

# systemd
sudo systemctl start adn-parrot
sudo systemctl enable adn-parrot
```

### systemd service

Create `/etc/systemd/system/adn-parrot.service`:

```ini
[Unit]
Description=ADN DMR Parrot (playback)
After=multi-user.target adn-server.service

[Service]
User=root
Type=simple
Restart=always
RestartSec=3
SyslogIdentifier=adn-parrot
WorkingDirectory=/opt/new-adn-server
ExecStart=/usr/bin/python3 /opt/adn-server/adn-parrot.py -c /opt/adn-server/adn-parrot.yaml

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now adn-parrot
```

## Playback flow

1. ECHO peer receives DMRD from master, forwards to parrot
2. Parrot detects new `stream_id` → starts recording
3. Parrot receives voice terminator → stops recording
4. Waits 2 seconds
5. Generates new `stream_id`, replays all packets with `sleep(0.06)` between each
6. ECHO peer receives playback, master repeats to hotspot

## Compatibility

The parrot uses the standard HBP protocol. Any legacy `playback.py` instance running
on another server can connect to our MASTER systems, and our ECHO peer can connect to
any legacy parrot master. The protocol is identical.

## Logs

Default log file: `/var/log/adn-server/parrot.log`

Successful startup looks like:

```
INFO  ADN Parrot -- SYSTEM STARTING...
DEBUG MASTER instance created: PARROT, <HBPProtocol ...>
INFO  (PARROT) Repeater Logging in with Radio ID: 9990, 127.0.0.1:54917
INFO  (PARROT) Peer 9990 has completed the login exchange successfully
INFO  (PARROT) Peer b'ECHO    ' (9990) has sent repeater configuration
```

Recording/playback:

```
INFO  (PARROT) *START RECORDING* STREAM ID: 12345 SUB: 7301001 TGID 9990, TS 2
INFO  (PARROT) *END   RECORDING* STREAM ID: 12345
INFO  (PARROT) *START  PLAYBACK* STREAM ID: 67890 Duration: 3.2
INFO  (PARROT) *END    PLAYBACK* STREAM ID: 67890
```
