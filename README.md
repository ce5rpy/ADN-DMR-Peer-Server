# ADN DMR Peer Server

Clean Architecture rewrite of the ADN DMR conference bridge. Same behaviour as the original server; configuration is YAML.

## License

GPL v3. Derived from FreeDMR / HBlink.

## Requirements

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

## Configuration

Copy `adn-server.example.yaml` to `adn-server.yaml` and edit with your settings. Production config is not committed.

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
