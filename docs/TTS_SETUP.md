# TTS (Text-to-Speech) Setup

TTS announcements convert text files to AMBE and play them on a talkgroup at intervals or hourly.

## Pipeline

```
.txt → gTTS → .mp3 → ffmpeg → .wav (8kHz mono) → vocoder/AMBEServer → .ambe → broadcast
```

## First-time setup

1. **Create the text file** in `Audio/<LANGUAGE>/ondemand/<FILE>.txt`

   Example for `FILE: texto1` and `LANGUAGE: es_ES`:
   ```
   Audio/es_ES/ondemand/texto1.txt
   ```

   Put the text you want spoken in that file (UTF-8).

2. **Configure encoding** — choose one:
   - **Physical AMBE (DV3000)**: set `TTS_AMBESERVER_HOST` to the host where [AMBEServer](https://github.com/marrold/AMBEServer) runs (connected to the DV3000).
   - **Software vocoder**: set `TTS_VOCODER_CMD` with a command like `/usr/local/bin/md380-vocoder -e {wav} {ambe}`.

3. **Enable the TTS item** in `TTS_ANNOUNCEMENTS`:
   ```yaml
   TTS_ANNOUNCEMENTS:
     - ENABLED: true
       FILE: texto1
       TG: 2
       MODE: interval
       INTERVAL: 60
       LANGUAGE: es_ES
   ```

## How it works

- **First run**: The system reads `texto1.txt`, generates speech (gTTS), converts to WAV, encodes to AMBE via the configured vocoder/AMBEServer, saves `texto1.ambe`, and broadcasts it.
- **Later runs**: If `texto1.ambe` exists and is newer than `texto1.txt`, it uses the cached AMBE file directly (no conversion).
- **Update text**: Edit `texto1.txt` and save. On the next interval, the system will regenerate `texto1.ambe` because the .txt is newer.

## Physical AMBE (AMBEServer)

When using a DV3000 or similar hardware via AMBEServer:

1. Run AMBEServer on a host with the DV3000 connected (USB/serial).
2. In `adn-voice.yaml`:
   ```yaml
   TTS_AMBESERVER_HOST: "192.168.1.10"   # host where AMBEServer runs
   TTS_AMBESERVER_PORT: 2460              # default
   ```
3. Ensure the ADN server can reach that host:port (UDP).

### Troubleshooting physical AMBE

| Symptom | Check |
|--------|-------|
| "Text file not found" | Create `Audio/<LANG>/ondemand/<FILE>.txt` (e.g. `Audio/es_ES/ondemand/texto1.txt`) |
| "AMBEServer failed, trying external vocoder..." | AMBEServer unreachable or timeout. Verify host/port, firewall, AMBEServer running. |
| "Could not encode to AMBE" | Neither AMBEServer nor TTS_VOCODER_CMD worked. Set one of them. |
| "Timeout connecting to AMBEServer" | Network/firewall; AMBEServer not listening; DV3000 not connected. |
| No audio plays | Check logs for "(TTS) Playing TTS file" — if present, broadcast succeeded; check TG and bridge targets. |

### Log messages

- `(TTS) Converting text to AMBE: ...` — first-time conversion in progress
- `(TTS) Using AMBEServer host:port` — using physical AMBE
- `(TTS) Using cached AMBE` — .ambe exists and is newer than .txt
- `(TTS) AMBEServer failed, trying external vocoder...` — AMBEServer failed; fallback to TTS_VOCODER_CMD if set

## Dependencies

- **gTTS**: `pip install gTTS`
- **ffmpeg**: system package (`apt install ffmpeg` etc.)
- **AMBEServer** (physical AMBE): [marrold/AMBEServer](https://github.com/marrold/AMBEServer) on a host with DV3000
