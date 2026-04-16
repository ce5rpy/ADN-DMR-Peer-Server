# Parrot (reproducción)

## Qué es

**Parrot** es un **punto de entrada separado** (`adn-parrot.py` / `parrot_main`) que graba voz de **grupo** entrante y la reproduce (eco / parrot), independiente del proceso principal del bridge.

## Configuración

- Copiar **`adn-parrot.example.yaml`** → **`adn-parrot.yaml`** (no versionada).
- Ejecutar:

```bash
python adn-parrot.py -c adn-parrot.yaml
```

## Relación con TG 9990 / ECHO

El servidor principal puede exponer un bridge **ECHO** en **TG 9990** para eco en banda. **Parrot** es un **servicio independiente** con su propia config — usa uno u otro según el despliegue.

## Documentación

Esta página es el resumen incluido en el repositorio; amplía las notas de despliegue localmente si hace falta.
