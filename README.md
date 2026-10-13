# Monitor de internet (Python)

Mide la calidad de tu conexión a lo largo del tiempo —**velocidad de bajada y subida, latencia (ping), jitter y pérdida de paquetes**— guarda el historial y arma un reporte HTML con gráficos y las "horas malas". Sirve para saber cuándo tienes lag al jugar y para reclamarle a tu proveedor con datos en la mano.

Funciona en Windows, Linux o macOS con Python 3.8 o superior. **No necesita instalar nada**: usa solo la librería estándar de Python.

---

## Tabla de contenidos
- [Para qué sirve](#para-qué-sirve)
- [Qué mide](#qué-mide)
- [Instalación](#instalación)
- [Uso](#uso)
- [El reporte](#el-reporte)
- [Configuración (config.json)](#configuración-configjson)
- [Dejarlo midiendo solo](#dejarlo-midiendo-solo)
- [Cómo lee los resultados](#cómo-lee-los-resultados)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Preguntas frecuentes](#preguntas-frecuentes)
- [Conceptos aplicados](#conceptos-aplicados)
- [Aviso](#aviso)

---

## Para qué sirve

"Mi internet anda mal" no sirve para reclamar; "entre las 21:00 y las 22:00 tengo 15 % de pérdida de paquetes y la latencia sube a 250 ms" sí. Este monitor toma mediciones cada cierto tiempo, las guarda y te muestra en un gráfico cuándo tu conexión empeora. Útil para elegir la hora de jugar, para pillar si el problema es tuyo o del proveedor, y para tener evidencia si tienes que reclamar.

---

## Qué mide

- **Latencia (ping):** cuánto demora en responder un servidor confiable. Latencia alta = lag.
- **Jitter:** qué tan estable es ese ping. Un jitter alto se siente como "tirones" aunque el promedio sea bueno.
- **Pérdida de paquetes:** cuántos paquetes no llegan. Es lo que más se nota al jugar o en videollamadas.
- **Velocidad de bajada y subida:** en Mbps, midiendo contra los servidores de Cloudflare.

---

## Instalación

No hay instalación. Solo necesitas Python 3.8+ y la carpeta con los archivos. Doble clic en `MedirAhora.cmd`.

> Si no tienes Python, instálalo desde [python.org](https://www.python.org/downloads/) marcando "Add Python to PATH".

---

## Uso

| Acción | Qué hace |
| --- | --- |
| **`MedirAhora.cmd`** | Toma una medición y abre el reporte |
| **`Monitorear.cmd`** | Mide cada 15 minutos sin parar (deja la ventana abierta mientras juegas) |
| **`VerReporte.cmd`** | Solo abre el último reporte, sin medir |

Por línea de comandos:

```bash
python monitor_internet.py            # una medición + reporte
python monitor_internet.py --continuo # mide cada X minutos (según config.json)
python monitor_internet.py --reporte  # solo regenera el reporte
```

---

## El reporte

Se abre en el navegador (`reportes/reporte.html`) y muestra:

- **Resumen** arriba: número de mediciones, latencia media, bajada media, pérdida media, % con problemas y, si configuras tu plan, qué porcentaje de lo contratado estás recibiendo.
- **Tres gráficos** en el tiempo: latencia, velocidad de bajada y pérdida de paquetes, con una línea de umbral.
- **Peores momentos:** la tabla con las mediciones donde la conexión estuvo mal.

---

## Configuración (config.json)

Se crea solo la primera vez. Ábrelo con el Bloc de notas:

| Opción | Qué controla |
| --- | --- |
| `hosts_ping` | A qué servidores se hace ping (por defecto Cloudflare y Google) |
| `pings_por_medicion` | Cuántos pings por medición (más = más preciso, más lento) |
| `mb_descarga` / `mb_subida` | Cuántos MB usa el test de velocidad |
| `medir_subida` | `true`/`false` para medir también la subida |
| `plan_contratado_mbps` | Tu plan en Mbps (ej. `200`). En `0` no compara. Si lo pones, el reporte muestra el % que recibes |
| `umbral_latencia_ms` | Sobre este valor una medición cuenta como "con problema" |
| `umbral_perdida_pct` | Lo mismo para la pérdida de paquetes |
| `umbral_velocidad_mbps` | Marca problema si la bajada cae bajo este valor (`0` = ignorar) |
| `minutos_entre_mediciones` | Cada cuánto mide en modo continuo |

Consejo: pon tu `plan_contratado_mbps` para que el reporte te diga si estás recibiendo lo que pagas.

---

## Dejarlo midiendo solo

Dos opciones:

1. **Mientras juegas:** abre `Monitorear.cmd` y déjalo en segundo plano; mide cada 15 minutos.
2. **Siempre:** crea una tarea en el Programador de tareas que ejecute, en esta carpeta, `python monitor_internet.py --no-abrir` cada 15 o 30 minutos. Así junta datos todo el día sin abrir ventanas.

---

## Cómo lee los resultados

- **Latencia** bajo ~50 ms: excelente para jugar. Sobre ~100 ms se nota el lag.
- **Jitter** alto: la conexión "salta" aunque el promedio sea bueno; típico de WiFi saturado.
- **Pérdida de paquetes** sobre 1–2 %: es lo que más arruina juegos y llamadas.
- Si ves **franjas rojas repetidas a la misma hora**, probablemente es saturación del proveedor; ese patrón es tu mejor argumento para reclamar.

---

## Estructura del proyecto

```
monitor-internet/
├─ monitor_internet.py   # mide y genera el reporte
├─ MedirAhora.cmd        # una medición
├─ Monitorear.cmd        # medición continua
├─ VerReporte.cmd        # abre el último reporte
├─ config.json           # opciones (se crea solo)
├─ README.md
└─ datos/ , reportes/    # se crean solos (no se suben)
```

---

## Preguntas frecuentes

**¿Necesito instalar speedtest u otra cosa?** No. El test de velocidad usa los servidores públicos de Cloudflare por HTTPS, con la librería estándar de Python.

**¿Consume muchos datos?** Cada medición descarga ~15 MB (ajustable en `config.json`). Si tienes plan con límite, baja `mb_descarga`.

**¿Por qué me da menos velocidad que otras páginas?** Un solo flujo HTTP suele marcar algo menos que un test con múltiples conexiones; lo importante aquí es la **tendencia** y las caídas, no el número exacto.

**El ping sale vacío.** Algunos equipos bloquean ICMP. Prueba con otros `hosts_ping` o revisa tu firewall.

---

## Conceptos aplicados

Medición de calidad de red (latencia, jitter, pérdida de paquetes), parseo de la salida de `ping` en español e inglés, test de ancho de banda por HTTP, series de tiempo en CSV, generación de gráficos en **SVG sin dependencias** y reportes HTML.

---

## Aviso

Mide tu propia conexión. Es una herramienta de diagnóstico doméstico, no una medición oficial certificada; para un reclamo formal, acompáñala de las mediciones del propio proveedor cuando corresponda.
