# ADN DMR Peer Server

Clean Architecture rewrite of the ADN DMR conference bridge. Same behaviour as the original server; configuration is YAML.

## License

GPL v3. Derived from FreeDMR / HBlink.

## Requirements

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`
- **ffmpeg** (system package) — required for voice/TTS. Install via your distro:
  - Debian/Ubuntu: `apt install ffmpeg`
  - openSUSE: `zypper install ffmpeg`
  - Fedora/RHEL: `dnf install ffmpeg` or `yum install ffmpeg`

## Configuration

Copy `adn-server.example.yaml` to `adn-server.yaml` and edit with your settings. Production config is not committed.

### Voice configuration

Voice features (announcements, TTS, recording) use a separate config file. Copy `adn-voice.example.yaml` to `adn-voice.yaml` and edit. If the file does not exist, voice features are disabled (no error). Changes are hot-reloaded every 15 seconds.

- **Each item** (ANNOUNCEMENTS, TTS_ANNOUNCEMENTS) has its own `LANGUAGE` and `ENABLED: true` to activate.
- **ANNOUNCEMENT_LANGUAGES** is optional (for voice ident only); announcements/TTS work without it.
- **TTS** requires ffmpeg + vocoder (TTS_VOCODER_CMD or TTS_AMBESERVER_HOST). Pipeline: `.txt` → gTTS → `.mp3` → ffmpeg → `.wav` → vocoder → `.ambe`. First time: create `Audio/<LANG>/ondemand/<FILE>.txt` with the text. See [docs/TTS_SETUP.md](docs/TTS_SETUP.md).

## Run

```bash
pip install -r requirements.txt
python adn-server.py
```

Options:

```bash
python adn-server.py -c /path/to/adn-server.yaml
python adn-server.py --logging DEBUG
```

## Parrot (Playback)

A separate entrypoint records incoming group voice and plays it back (echo/parrot).

```bash
cp adn-parrot.example.yaml adn-parrot.yaml
python adn-parrot.py
```

See [docs/PARROT.md](docs/PARROT.md) for architecture, configuration and systemd setup.
