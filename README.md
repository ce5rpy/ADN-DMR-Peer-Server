# ADN DMR Peer Server

Clean Architecture rewrite of the ADN DMR conference bridge. Same behaviour as the original server; configuration is YAML.

## License

GPL v3. Derived from ADN DMR Server / HBlink.

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
