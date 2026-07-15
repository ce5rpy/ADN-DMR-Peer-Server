# Rendimiento (2.x)

**adn-server 2.x** y **adn-monitor 2.x** consumen menos CPU y RAM que **adn-dmr-server**
y el stack antiguo de monitor/proxy. No hace falta ajustar nada — las mejoras vienen de
cómo están hechos el enrutado, los informes y el proxy integrado.

Empareja **servidor 2.x con monitor 2.x** para aprovechar también el lado del panel.

## Qué mejoró

| Mejora | Qué ganas |
|--------|-----------|
| **Enrutado de voz más eficiente** | Con tráfico de grupo intenso el servidor hace menos trabajo por paquete — sobre todo en proxies con muchos hotspots y en nodos con muchos OpenBridge. |
| **Proxy hotspot integrado** | Un solo proceso `adn-server` en lugar de servidor + **adn-proxy** aparte — menos RAM y operación más simple. Ver [Proxy hotspot](../user-guide/hotspot-proxy.md). |
| **Sin timer legacy de 26 s** | Las TG estáticas se refrescan por eventos (arranque, recarga de config, OPTIONS del peer), no con un bucle de fondo cada 26 segundos. Ver [Comportamiento y temporizadores](behaviour-and-timers.md). |
| **Cable al monitor más liviano** | **Informe v2** envía JSON compacto en lugar de volcados pickle pesados. Ver [Protocolo de informes v2](../protocols/report-v2.md). |
| **Monitor 2.x** | Estado de panel más compacto, menos crecimiento de memoria con el panel abierto días. Ver [Arquitectura del monitor](../../monitor/architecture.md). |

## Servidores con muchos OpenBridge (2.3.3+)

Si tienes **muchos OpenBridge** y actualizas desde un **2.x** anterior a **2.3.3 o
superior**, un nodo en producción con carga OBP comparable mostró aproximadamente:

| | Antes (2.x) | Después (2.3.3+) |
|--|-------------|------------------|
| **CPU** | línea base | **~25% de la línea base** |
| **RAM** | línea base | **~75% de la línea base** |

Las cifras exactas dependen del tráfico y del hardware; tómalo como referencia, no como garantía.

## Cuándo se nota más

| Tu red | Efecto |
|--------|--------|
| Instalación pequeña, pocos peers, poco tráfico | Moderado — el stack es más liviano en general. |
| **Proxy inject con muchos hotspots** | **Ganancia clara de CPU** con voz de grupo activa. |
| **Muchos OpenBridge, tráfico mesh continuo** | **Ganancia clara de CPU y RAM** tras **2.3.3+** (ver tabla anterior). |
| **Muchos hotspots conectando a la vez** | Menos carga en servidor y monitor en ráfagas de login. |
| **Monitor abierto 24/7** | RAM más baja y estable en **adn-monitor 2.x**. |

Crypto, AMBE y el trabajo de cable OpenBridge siguen costando CPU en tramos OBP
cargados — las optimizaciones de routing quitan trabajo redundante de bridges, no el
codec de voz ni el cifrado.

## Lecturas relacionadas

- [Proxy hotspot](../user-guide/hotspot-proxy.md) — `PROXY` integrado
- [Monitor e informes](../user-guide/monitoring.md) — emparejar informe v2
- [Comportamiento y temporizadores](behaviour-and-timers.md) — OPTIONS por eventos
- Notas de versión: `CHANGELOG.md` en la raíz del repositorio
