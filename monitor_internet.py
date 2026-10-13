#!/usr/bin/env python3
"""
Monitor de internet
Autor: Diego Molina (github.com/DiegoEsteban20)

Mide la calidad de tu conexión a lo largo del tiempo:
  - Latencia (ping) y jitter (qué tan estable es el ping)
  - Pérdida de paquetes
  - Velocidad de bajada y de subida

Guarda cada medición en datos/historial.csv y arma un reporte HTML con
gráficos y las "horas malas", útil para saber cuándo hay lag al jugar o
para reclamarle al proveedor con datos.

Uso:
  python monitor_internet.py            una medición y actualiza el reporte
  python monitor_internet.py --continuo cada X minutos (según config.json)
  python monitor_internet.py --reporte  solo regenera el reporte desde el historial
  python monitor_internet.py --no-abrir  no abre el reporte al terminar

No necesita instalar nada: usa solo la librería estándar de Python.
"""
import argparse
import csv
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
DIR_DATOS = os.path.join(BASE, "datos")
DIR_REPORTES = os.path.join(BASE, "reportes")
ARCH_HIST = os.path.join(DIR_DATOS, "historial.csv")
ARCH_CONFIG = os.path.join(BASE, "config.json")

CONFIG_DEF = {
    "hosts_ping": ["1.1.1.1", "8.8.8.8"],
    "pings_por_medicion": 10,
    "mb_descarga": 15,
    "medir_subida": True,
    "mb_subida": 5,
    "plan_contratado_mbps": 0,
    "umbral_latencia_ms": 80,
    "umbral_perdida_pct": 2,
    "umbral_velocidad_mbps": 0,
    "minutos_entre_mediciones": 15,
}

COLUMNAS = ["fecha", "latencia_ms", "jitter_ms", "perdida_pct", "bajada_mbps", "subida_mbps", "estado"]


# ------------------------------------------------------------------ config
def leer_config():
    cfg = dict(CONFIG_DEF)
    if os.path.exists(ARCH_CONFIG):
        try:
            with open(ARCH_CONFIG, encoding="utf-8") as fh:
                cfg.update(json.load(fh))
        except Exception as e:
            print(f"  Aviso: no pude leer config.json ({e}); uso valores por defecto")
    return cfg


def crear_config_si_falta():
    if not os.path.exists(ARCH_CONFIG):
        with open(ARCH_CONFIG, "w", encoding="utf-8") as fh:
            json.dump(CONFIG_DEF, fh, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ ping
def medir_ping(host, cantidad):
    """Devuelve (latencia_media, jitter, perdida_pct) o (None, None, 100) si no hay respuesta."""
    es_windows = os.name == "nt"
    if es_windows:
        cmd = ["ping", "-n", str(cantidad), host]
    else:
        cmd = ["ping", "-c", str(cantidad), host]
    try:
        salida = subprocess.run(cmd, capture_output=True, timeout=cantidad * 2 + 10).stdout
    except Exception:
        return None, None, 100.0
    # decodificar tolerante a idioma/codificación del sistema
    texto = None
    for enc in ("utf-8", "cp850", "latin-1"):
        try:
            texto = salida.decode(enc)
            break
        except Exception:
            continue
    if texto is None:
        texto = salida.decode("utf-8", errors="replace")

    # tiempos individuales: "tiempo=12ms", "time=12ms", "time<1ms"
    tiempos = []
    for m in re.finditer(r"(?:tiempo|time)=\s*(\d+)\s*ms", texto, re.IGNORECASE):
        tiempos.append(float(m.group(1)))
    for _ in re.finditer(r"(?:tiempo|time)<\s*1\s*ms", texto, re.IGNORECASE):
        tiempos.append(0.5)

    # pérdida: "0% perdidos" / "0% loss" / "(0% ...)"
    perdida = None
    mp = re.search(r"\((\d+)\s*%\s*(?:perdidos|loss|p[eé]rdida)", texto, re.IGNORECASE)
    if mp:
        perdida = float(mp.group(1))
    else:
        mp = re.search(r"(\d+)\s*%\s*(?:packet loss|p[eé]rdida)", texto, re.IGNORECASE)
        if mp:
            perdida = float(mp.group(1))

    if not tiempos:
        return None, None, 100.0 if perdida is None else perdida
    latencia = round(statistics.mean(tiempos), 1)
    jitter = round(statistics.pstdev(tiempos), 1) if len(tiempos) > 1 else 0.0
    if perdida is None:
        perdida = round((cantidad - len(tiempos)) / cantidad * 100, 1)
    return latencia, jitter, perdida


def medir_ping_varios(hosts, cantidad):
    """Prueba varios hosts y se queda con el mejor resultado (el de menor pérdida/latencia)."""
    mejor = (None, None, 100.0)
    for h in hosts:
        lat, jit, per = medir_ping(h, cantidad)
        if lat is None:
            continue
        if mejor[0] is None or per < mejor[2] or (per == mejor[2] and lat < mejor[0]):
            mejor = (lat, jit, per)
    return mejor


# ------------------------------------------------------------------ velocidad
def medir_bajada(mb):
    """Descarga ~mb MB desde Cloudflare y devuelve Mbps, o None si falla."""
    bytes_pedidos = int(mb * 1_000_000)
    url = f"https://speed.cloudflare.com/__down?bytes={bytes_pedidos}"
    req = urllib.request.Request(url, headers={"User-Agent": "MonitorInternet/1.0"})
    try:
        inicio = time.perf_counter()
        total = 0
        with urllib.request.urlopen(req, timeout=30) as r:
            while True:
                trozo = r.read(65536)
                if not trozo:
                    break
                total += len(trozo)
        dur = time.perf_counter() - inicio
        if dur <= 0 or total == 0:
            return None
        return round(total * 8 / dur / 1_000_000, 1)
    except Exception:
        return None


def medir_subida(mb):
    """Sube ~mb MB a Cloudflare y devuelve Mbps, o None si falla."""
    datos = b"0" * int(mb * 1_000_000)
    url = "https://speed.cloudflare.com/__up"
    req = urllib.request.Request(url, data=datos, method="POST",
                                 headers={"User-Agent": "MonitorInternet/1.0",
                                          "Content-Type": "application/octet-stream"})
    try:
        inicio = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        dur = time.perf_counter() - inicio
        if dur <= 0:
            return None
        return round(len(datos) * 8 / dur / 1_000_000, 1)
    except Exception:
        return None


# ------------------------------------------------------------------ evaluación
def evaluar(cfg, latencia, perdida, bajada):
    """Devuelve 'OK' o 'PROBLEMA' según los umbrales."""
    if latencia is None or perdida >= 100:
        return "SIN CONEXION"
    problema = False
    if perdida > cfg["umbral_perdida_pct"]:
        problema = True
    if latencia > cfg["umbral_latencia_ms"]:
        problema = True
    if cfg["umbral_velocidad_mbps"] and bajada is not None and bajada < cfg["umbral_velocidad_mbps"]:
        problema = True
    if cfg["plan_contratado_mbps"] and bajada is not None and bajada < cfg["plan_contratado_mbps"] * 0.5:
        problema = True
    return "PROBLEMA" if problema else "OK"


# ------------------------------------------------------------------ historial
def guardar(fila):
    os.makedirs(DIR_DATOS, exist_ok=True)
    nuevo = not os.path.exists(ARCH_HIST)
    with open(ARCH_HIST, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def leer_historial():
    if not os.path.exists(ARCH_HIST):
        return []
    with open(ARCH_HIST, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ medición
def una_medicion(cfg, abrir=True):
    print(f"[{datetime.now():%H:%M:%S}] Midiendo...", flush=True)
    lat, jit, per = medir_ping_varios(cfg["hosts_ping"], cfg["pings_por_medicion"])
    baj = medir_bajada(cfg["mb_descarga"]) if (lat is not None) else None
    sub = medir_subida(cfg["mb_subida"]) if (cfg["medir_subida"] and lat is not None) else None
    estado = evaluar(cfg, lat, per, baj)

    fila = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latencia_ms": "" if lat is None else lat,
        "jitter_ms": "" if jit is None else jit,
        "perdida_pct": per,
        "bajada_mbps": "" if baj is None else baj,
        "subida_mbps": "" if sub is None else sub,
        "estado": estado,
    }
    guardar(fila)

    def fmt(v, u):
        return f"{v}{u}" if v not in (None, "") else "—"
    print(f"  Latencia {fmt(lat,' ms')} | Jitter {fmt(jit,' ms')} | "
          f"Pérdida {per}% | Bajada {fmt(baj,' Mbps')} | Subida {fmt(sub,' Mbps')} | {estado}")

    ruta = generar_reporte(cfg)
    if abrir and ruta:
        webbrowser.open("file:///" + ruta.replace("\\", "/"))
    return fila


# ------------------------------------------------------------------ reporte (SVG, sin dependencias)
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def svg_linea(puntos, titulo, unidad, color, umbral=None, alto=180, ancho=760):
    """puntos: lista de (etiqueta, valor|None). Dibuja una línea simple en SVG."""
    vals = [v for _, v in puntos if v is not None]
    if not vals:
        return f'<div class="chart"><h3>{titulo}</h3><p class="vacio">Sin datos</p></div>'
    vmax = max(vals + ([umbral] if umbral else []))
    vmin = min(vals + [0])
    rango = (vmax - vmin) or 1
    mL, mR, mT, mB = 48, 12, 16, 28
    w, h = ancho - mL - mR, alto - mT - mB
    n = len(puntos)
    paso = w / max(n - 1, 1)

    def x(i):
        return mL + i * paso

    def y(v):
        return mT + h - (v - vmin) / rango * h

    # línea
    d = []
    ult = None
    for i, (_, v) in enumerate(puntos):
        if v is None:
            ult = None
            continue
        cmd = "M" if ult is None else "L"
        d.append(f"{cmd}{x(i):.1f},{y(v):.1f}")
        ult = v
    linea = " ".join(d)

    # grilla + etiquetas eje Y (3 valores)
    grid = []
    for k in range(4):
        val = vmin + rango * k / 3
        yy = y(val)
        grid.append(f'<line x1="{mL}" y1="{yy:.1f}" x2="{mL+w}" y2="{yy:.1f}" class="grid"/>')
        grid.append(f'<text x="{mL-6}" y="{yy+3:.1f}" class="ytick">{val:.0f}</text>')

    umb = ""
    if umbral:
        yu = y(umbral)
        umb = (f'<line x1="{mL}" y1="{yu:.1f}" x2="{mL+w}" y2="{yu:.1f}" class="umbral"/>'
               f'<text x="{mL+w}" y="{yu-4:.1f}" class="umbral-txt">umbral {umbral}{unidad}</text>')

    # etiquetas eje X: primera, media, última
    xticks = []
    for i in (0, n // 2, n - 1):
        et = puntos[i][0]
        xticks.append(f'<text x="{x(i):.1f}" y="{alto-8}" class="xtick">{et}</text>')

    puntos_svg = []
    for i, (_, v) in enumerate(puntos):
        if v is not None:
            puntos_svg.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2" fill="{color}"/>')

    return f'''<div class="chart"><h3>{titulo} <span class="u">({unidad})</span></h3>
<svg viewBox="0 0 {ancho} {alto}" class="svg">
{''.join(grid)}
{umb}
<path d="{linea}" fill="none" stroke="{color}" stroke-width="2"/>
{''.join(puntos_svg)}
{''.join(xticks)}
</svg></div>'''


def generar_reporte(cfg):
    filas = leer_historial()
    if not filas:
        return None
    os.makedirs(DIR_REPORTES, exist_ok=True)
    ruta = os.path.join(DIR_REPORTES, "reporte.html")

    recientes = filas[-96:]  # últimas ~24 h si mide cada 15 min
    def etq(f):
        return f["fecha"][11:16]  # HH:MM

    p_lat = [(etq(f), _num(f["latencia_ms"])) for f in recientes]
    p_baj = [(etq(f), _num(f["bajada_mbps"])) for f in recientes]
    p_per = [(etq(f), _num(f["perdida_pct"])) for f in recientes]

    lat_vals = [v for _, v in p_lat if v is not None]
    baj_vals = [v for _, v in p_baj if v is not None]
    per_vals = [v for _, v in p_per if v is not None]
    problemas = [f for f in filas if f["estado"] in ("PROBLEMA", "SIN CONEXION")]

    def prom(xs):
        return round(statistics.mean(xs), 1) if xs else "—"

    tiles = [
        ("Mediciones", len(filas)),
        ("Latencia media", f"{prom(lat_vals)} ms"),
        ("Bajada media", f"{prom(baj_vals)} Mbps"),
        ("Pérdida media", f"{prom(per_vals)} %"),
        ("Con problemas", f"{len(problemas)} ({round(len(problemas)/len(filas)*100)}%)"),
    ]
    if cfg["plan_contratado_mbps"] and baj_vals:
        pct = round(prom(baj_vals) / cfg["plan_contratado_mbps"] * 100)
        tiles.append((f"% del plan ({cfg['plan_contratado_mbps']} Mbps)", f"{pct}%"))

    tiles_html = "".join(
        f'<div class="tile"><div class="tval">{v}</div><div class="tlab">{k}</div></div>'
        for k, v in tiles)

    # peores momentos (top 10 por latencia o pérdida)
    def mala(f):
        return (_num(f["perdida_pct"]) or 0, _num(f["latencia_ms"]) or 0)
    peores = sorted([f for f in filas if f["estado"] != "OK"], key=mala, reverse=True)[:10]
    filas_peores = "".join(
        f"<tr><td>{f['fecha']}</td><td>{f['latencia_ms'] or '—'}</td>"
        f"<td>{f['perdida_pct']}</td><td>{f['bajada_mbps'] or '—'}</td>"
        f"<td>{f['subida_mbps'] or '—'}</td><td class='st-{f['estado'].split()[0].lower()}'>{f['estado']}</td></tr>"
        for f in peores) or "<tr><td colspan='6'>Sin problemas registrados 🎉</td></tr>"

    chart_lat = svg_linea(p_lat, "Latencia (ping)", "ms", "#2563eb", cfg["umbral_latencia_ms"])
    chart_baj = svg_linea(p_baj, "Velocidad de bajada", "Mbps", "#16a34a",
                          cfg["plan_contratado_mbps"] or cfg["umbral_velocidad_mbps"] or None)
    chart_per = svg_linea(p_per, "Pérdida de paquetes", "%", "#dc2626", cfg["umbral_perdida_pct"])

    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de internet</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f1f5f9;color:#0f172a}}
.wrap{{max-width:820px;margin:0 auto;padding:20px}}
h1{{margin:0 0 4px}}
.sub{{color:#64748b;margin:0 0 18px}}
.tiles{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}}
.tile{{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px}}
.tval{{font-size:22px;font-weight:700}}
.tlab{{color:#64748b;font-size:12px;margin-top:2px}}
.chart{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;margin-bottom:14px}}
.chart h3{{margin:0 0 6px;font-size:15px}} .u{{color:#94a3b8;font-weight:400;font-size:12px}}
.svg{{width:100%;height:auto}}
.grid{{stroke:#eef2f7}} .ytick,.xtick{{fill:#94a3b8;font-size:10px}} .xtick{{text-anchor:middle}} .ytick{{text-anchor:end}}
.umbral{{stroke:#f59e0b;stroke-dasharray:4 3}} .umbral-txt{{fill:#f59e0b;font-size:10px;text-anchor:end}}
.vacio{{color:#94a3b8}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0}}
th,td{{padding:7px 10px;text-align:left;font-size:13px;border-bottom:1px solid #eef2f7}}
th{{background:#0f172a;color:#fff}}
.st-problema{{color:#b45309;font-weight:600}} .st-sin{{color:#b91c1c;font-weight:600}}
h2{{font-size:16px;margin:18px 0 8px}}
.pie{{color:#94a3b8;font-size:12px;margin-top:16px}}
</style></head><body><div class="wrap">
<h1>Monitor de internet</h1>
<p class="sub">Actualizado {datetime.now():%d-%m-%Y %H:%M} · {len(filas)} mediciones</p>
<div class="tiles">{tiles_html}</div>
{chart_lat}{chart_baj}{chart_per}
<h2>Peores momentos</h2>
<table><tr><th>Fecha</th><th>Latencia ms</th><th>Pérdida %</th><th>Bajada Mbps</th><th>Subida Mbps</th><th>Estado</th></tr>
{filas_peores}</table>
<p class="pie">Latencia alta o pérdida de paquetes = lag al jugar. Si ves muchas franjas rojas a la misma hora,
es un buen dato para reclamarle a tu proveedor.</p>
</div></body></html>"""
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(html)
    return ruta


# ------------------------------------------------------------------ main
def main():
    p = argparse.ArgumentParser(description="Monitor de calidad de internet")
    p.add_argument("--continuo", action="store_true", help="mide cada X minutos sin parar")
    p.add_argument("--reporte", action="store_true", help="solo regenera el reporte")
    p.add_argument("--no-abrir", action="store_true", help="no abre el reporte al terminar")
    a = p.parse_args()

    crear_config_si_falta()
    cfg = leer_config()

    if a.reporte:
        ruta = generar_reporte(cfg)
        if ruta:
            print(f"Reporte: {ruta}")
            if not a.no_abrir:
                webbrowser.open("file:///" + ruta.replace("\\", "/"))
        else:
            print("Todavía no hay mediciones.")
        return

    if a.continuo:
        minutos = cfg["minutos_entre_mediciones"]
        print(f"Monitoreando cada {minutos} min. Cierra esta ventana para detener.\n")
        try:
            while True:
                una_medicion(cfg, abrir=False)
                time.sleep(max(minutos, 1) * 60)
        except KeyboardInterrupt:
            print("\nDetenido.")
        return

    una_medicion(cfg, abrir=not a.no_abrir)


if __name__ == "__main__":
    main()
