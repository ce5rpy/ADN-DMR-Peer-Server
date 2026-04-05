# Parrot (playback)

## What it is

**Parrot** is a **separate entrypoint** (`adn-parrot.py` / `parrot_main`) that records incoming **group** voice and plays it back (echo / parrot), independent of the main bridge process.

## Configuration

- Copy **`adn-parrot.example.yaml`** → **`adn-parrot.yaml`** (not committed).
- Run:

```bash
python adn-parrot.py -c adn-parrot.yaml
```

## Relation to TG 9990 / ECHO

The main server may expose an **ECHO** bridge on **TG 9990** for in-band echo. **Parrot** is a **standalone** service with its own config — use one or the other according to your deployment.

## Documentation

This page is the summary shipped with the repository; extend your deployment notes locally as needed.
