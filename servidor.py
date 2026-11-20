# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro - servidor interno.

La ventana del programa es una página web local (carpeta ui/) que habla con este
servidor en 127.0.0.1. Las tareas largas corren en segundo plano como "trabajos"
y la interfaz consulta su avance (porcentaje + paso) para la barra de carga.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import mimetypes
import os
import re
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import analisis as an
import motor as m

try:
    import winsound  # solo Windows
except ImportError:  # pragma: no cover
    winsound = None


def ruta_recurso(*partes: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *partes)


def registrar_error(texto: str) -> str:
    os.makedirs(m.APP_DIR, exist_ok=True)
    ruta = os.path.join(m.APP_DIR, "errores.log")
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(f"\n[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] v{m.APP_VERSION}\n{texto}\n")
    return ruta


def _json(obj):
    """Convierte fechas y conjuntos para poder mandarlos como JSON."""
    return json.loads(json.dumps(obj, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)))


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", m.normalizar(texto)).strip("-") or "mercado"


# ---------------------------------------------------------------------------
# Estado compartido
# ---------------------------------------------------------------------------
class Estado:
    def __init__(self):
        self.lock = threading.RLock()
        self.cfg = m.cargar_config()
        self.db = m.BaseDatos()
        self.gt = self._cliente_trends()
        self.trabajos: dict[str, dict] = {}
        self.tablas: dict[str, tuple] = {}       # archivos de ventas abiertos
        self.avisos: list[dict] = []             # picos detectados para mostrar en la interfaz
        self.escaneando = False
        self.ultimo_escaneo = None

    def _cliente_trends(self):
        return m.GoogleTrends(self.cfg.get("pais") or "MX", self.cfg.get("idioma", "es-419"),
                              int(self.cfg.get("zona_horaria_min", 360)))

    def guardar(self):
        with self.lock:
            m.guardar_config(self.cfg)
            self.gt = self._cliente_trends()

    @property
    def mercado(self):
        return m.mercado_activo(self.cfg)

    # ---------------------------------------------------- trabajos en segundo plano
    def trabajo(self, nombre: str, fn, *args) -> str:
        tid = uuid.uuid4().hex[:10]
        t = {"id": tid, "nombre": nombre, "estado": "corriendo", "pct": 0, "paso": "Empezando…",
             "resultado": None, "error": None, "inicio": time.time()}
        self.trabajos[tid] = t

        def avanzar(pct, paso):
            t["pct"], t["paso"] = max(t["pct"], min(99, int(pct))), paso

        def correr():
            try:
                t["resultado"] = _json(fn(avanzar, *args))
                t["pct"], t["estado"] = 100, "listo"
            except m.ErrorFuente as e:
                t["error"], t["estado"] = str(e), "error"
            except Exception as e:  # noqa: BLE001
                registrar_error(traceback.format_exc())
                t["error"], t["estado"] = f"Error inesperado: {e}", "error"

        threading.Thread(target=correr, daemon=True).start()
        return tid

    # ---------------------------------------------------- análisis guardado
    def ruta_analisis(self, nombre: str) -> str:
        return os.path.join(m.APP_DIR, "analisis", _slug(nombre) + ".json")

    def ultimo_analisis(self):
        mer = self.mercado
        if not mer:
            return None
        try:
            with open(self.ruta_analisis(mer.nombre), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None


E: Estado | None = None


# ---------------------------------------------------------------------------
# Acciones (una función por botón de la interfaz)
# ---------------------------------------------------------------------------
def accion_estado(_d):
    cfg = E.cfg
    mer = E.mercado
    return {
        "version": m.APP_VERSION, "app": m.APP_NOMBRE, "pais": cfg.get("pais"), "idioma": cfg.get("idioma"),
        "mercados": [{"nombre": n, **d} for n, d in sorted((cfg.get("mercados") or {}).items())],
        "activo": mer.nombre if mer else "",
        "config": {k: cfg.get(k) for k in ("pais", "idioma", "intervalo_min", "umbral_z", "sonido", "auto_escaneo")},
        "tiene_youtube": bool(cfg.get("youtube_api_key")), "tiene_pinterest": bool(cfg.get("pinterest_token")),
        "plantillas": m.PLANTILLAS_MERCADO, "carpeta": m.APP_DIR,
    }


def accion_config(d):
    with E.lock:
        for k in ("pais", "idioma", "youtube_api_key", "pinterest_token"):
            if k in d and d[k] is not None:
                E.cfg[k] = str(d[k]).strip()
        if "intervalo_min" in d:
            E.cfg["intervalo_min"] = max(15, int(d["intervalo_min"]))
        if "umbral_z" in d:
            E.cfg["umbral_z"] = min(5.0, max(1.0, float(d["umbral_z"])))
        for k in ("sonido", "auto_escaneo"):
            if k in d:
                E.cfg[k] = bool(d[k])
        E.guardar()
    return accion_estado({})


def accion_config_claves(_d):
    return {"youtube_api_key": E.cfg.get("youtube_api_key", ""), "pinterest_token": E.cfg.get("pinterest_token", "")}


def accion_sugerir(d):
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        raise m.ErrorFuente("Escribe el nombre de tu mercado.")

    def trabajo(avanzar):
        avanzar(15, f"Buscando cómo busca la gente «{nombre}» en Google…")
        r = an.sugerir_palabras(nombre, E.cfg.get("pais") or "MX", E.cfg.get("idioma", "es-419"))
        avanzar(95, "Ordenando sugerencias…")
        return r

    return {"trabajo": E.trabajo("sugerir", trabajo)}


def accion_guardar_mercado(d):
    nombre = " ".join((d.get("nombre") or "").split())
    if not nombre:
        raise m.ErrorFuente("Ponle nombre a tu mercado.")
    palabras = [" ".join(p.split()) for p in d.get("palabras", []) if p and p.strip()]
    if not palabras:
        raise m.ErrorFuente("Elige al menos una palabra para tu mercado.")
    mer = m.Mercado(nombre, palabras, d.get("excluir", []), d.get("pinterest", ""))
    with E.lock:
        mercados = E.cfg.setdefault("mercados", {})
        anterior = d.get("nombre_anterior")
        if anterior and anterior != nombre:
            mercados.pop(anterior, None)
        mercados[nombre] = mer.a_dict()
        E.cfg["mercado_activo"] = nombre
        E.guardar()
    return accion_estado({})


def accion_activar(d):
    with E.lock:
        nombre = d.get("nombre") or ""
        E.cfg["mercado_activo"] = nombre if nombre in (E.cfg.get("mercados") or {}) else ""
        E.guardar()
    return accion_estado({})


def accion_borrar_mercado(d):
    with E.lock:
        nombre = d.get("nombre") or ""
        (E.cfg.get("mercados") or {}).pop(nombre, None)
        if E.cfg.get("mercado_activo") == nombre:
            E.cfg["mercado_activo"] = next(iter(sorted(E.cfg.get("mercados") or {})), "")
        E.guardar()
        try:
            os.remove(E.ruta_analisis(nombre))
        except OSError:
            pass
    return accion_estado({})


def accion_excluir(d):
    """«No es de mi mercado»: agrega la búsqueda a las palabras a ignorar."""
    texto = (d.get("texto") or "").strip()
    mer = E.mercado
    if not mer or not texto:
        raise m.ErrorFuente("No hay mercado activo.")
    with E.lock:
        datos = E.cfg["mercados"][mer.nombre]
        if texto not in datos.setdefault("excluir", []):
            datos["excluir"].append(texto)
        E.guardar()
    return {"excluir": E.cfg["mercados"][mer.nombre]["excluir"]}


def accion_analizar(_d):
    mer = E.mercado
    if not mer:
        raise m.ErrorFuente("Primero crea o elige tu mercado.")
    cfg = dict(E.cfg)

    def trabajo(avanzar):
        rep = an.analizar_mercado(cfg, mer, E.gt, avanzar)
        if cfg.get("pinterest_token"):
            try:
                pins = m.pinterest_tendencias(cfg["pinterest_token"], cfg.get("pais") or "MX", "growing",
                                              mer.pinterest)
                propias = [p for p in pins if mer.coincide(p["palabra"])]
                rep["pinterest"] = (propias or pins)[:15] if mer.pinterest else propias[:15]
            except m.ErrorFuente as e:
                rep["errores"]["pinterest"] = str(e)
        os.makedirs(os.path.dirname(E.ruta_analisis(mer.nombre)), exist_ok=True)
        with open(E.ruta_analisis(mer.nombre), "w", encoding="utf-8") as f:
            json.dump(_json(rep), f, ensure_ascii=False)
        return rep

    return {"trabajo": E.trabajo("analizar", trabajo)}


def accion_ultimo_analisis(_d):
    return {"analisis": E.ultimo_analisis()}


def accion_comparar(d):
    terminos = [" ".join(t.split()) for t in d.get("terminos", []) if t and t.strip()][:5]
    if not terminos:
        raise m.ErrorFuente("Escribe al menos una palabra para comparar.")
    tiempo = m.PERIODOS_TRENDS.get(d.get("periodo"), "today 3-m")
    mer = E.mercado
    if mer and d.get("ajustar", True):
        terminos = list(dict.fromkeys(mer.ajustar_termino(t) for t in terminos))
    juntas = bool(d.get("juntas"))
    umbral = float(E.cfg.get("umbral_z", 2.0))

    def trabajo(avanzar):
        if juntas:
            avanzar(20, "Consultando Google Trends…")
            fechas, series = E.gt.interes_en_el_tiempo(terminos, tiempo)
            return {"juntas": True, "fechas": [f.isoformat() for f in fechas],
                    "series": [{"palabra": t, "serie": series[t], **an.veredicto(series[t], umbral)}
                               for t in terminos]}
        res, aviso = an.interes_por_palabra(
            E.gt, terminos, tiempo,
            lambda i, n, p: avanzar(5 + 90 * i / n, f"Midiendo «{p}» ({i + 1} de {n})"), umbral)
        orden = {t: i for i, t in enumerate(terminos)}
        res.sort(key=lambda r: orden.get(r["palabra"], 99))
        return {"juntas": False, "series": res, "aviso": aviso}

    return {"trabajo": E.trabajo("comparar", trabajo), "terminos": terminos}


def accion_redes(d):
    tema = (d.get("tema") or "").strip()
    dias = int(d.get("dias") or 7)
    mer = E.mercado
    if not tema and not mer:
        raise m.ErrorFuente("Escribe un tema o elige tu mercado.")
    cfg = dict(E.cfg)
    umbral = float(cfg.get("umbral_z", 2.0))

    def trabajo(avanzar):
        salida = {"tema": f"{tema} en {mer.nombre}" if (tema and mer) else (tema or mer.nombre), "errores": {}}
        avanzar(10, "Buscando noticias…")
        try:
            q = mer.consulta_noticias(tema) if mer else tema
            notas = m.menciones_noticias(q, dias, cfg.get("pais") or "MX", cfg.get("idioma", "es-419"))
            fechas, cuentas = m.conteo_por_dia(notas, max(dias, 2))
            p = m.detectar_pico(cuentas, umbral, 1)
            salida["noticias"] = {"total": len(notas), "pico": bool(p["es_pico"]), "normal": p["normal"],
                                  "por_dia": [[f.isoformat(), c] for f, c in zip(fechas, cuentas)],
                                  "items": [{"fecha": n["fecha"], "titulo": n["titulo"], "medio": n["medio"],
                                             "url": n["url"]} for n in notas[:40]]}
        except m.ErrorFuente as e:
            salida["errores"]["noticias"] = str(e)
        if cfg.get("youtube_api_key"):
            avanzar(55, "Buscando videos en YouTube…")
            try:
                q = mer.consulta_youtube(tema) if mer else tema
                vids = m.youtube_tendencia(cfg["youtube_api_key"], q, dias, cfg.get("pais") or "MX",
                                           cfg.get("idioma", "es").split("-")[0], 50 if mer else 25, mer)
                salida["videos"] = [{k: v for k, v in x.items() if k != "texto"} for x in vids[:25]]
            except m.ErrorFuente as e:
                salida["errores"]["videos"] = str(e)
        else:
            salida["videos"] = None
        return salida

    return {"trabajo": E.trabajo("redes", trabajo)}


def accion_datos_leer(d):
    nombre = d.get("nombre") or "datos.csv"
    contenido = base64.b64decode(d.get("contenido") or "")
    ext = os.path.splitext(nombre)[1].lower() or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(contenido)
        ruta = tmp.name
    try:
        enc, filas = m.leer_tabla(ruta)
    finally:
        try:
            os.remove(ruta)
        except OSError:
            pass
    tid = uuid.uuid4().hex[:8]
    E.tablas = {tid: (enc, filas)}          # solo guardamos el último archivo
    g = m.adivinar_columnas(enc)
    return {"id": tid, "archivo": nombre, "encabezados": enc, "filas": len(filas),
            "sugeridas": {k: (enc[v] if v is not None else None) for k, v in g.items()},
            "muestra": [[str(c) if c is not None else "" for c in f] for f in filas[:5]]}


def accion_datos_analizar(d):
    if d.get("id") not in E.tablas:
        raise m.ErrorFuente("Vuelve a abrir el archivo.")
    enc, filas = E.tablas[d["id"]]
    i_f = enc.index(d["fecha"])
    i_v = enc.index(d["valor"]) if d.get("valor") in enc else None
    i_c = enc.index(d["categoria"]) if d.get("categoria") in enc else None
    freq = d.get("freq", "W")
    a = m.agrupar(filas, i_f, i_v, i_c, freq, bool(d.get("incompleto", True)))
    vals, per = a["valores"], a["periodos"]
    n = m.ventana_efectiva(freq, len(per))
    pr = m.pronostico(per, vals, max(1, int(d.get("pronostico", 4))), freq)
    ranking = m.ranking_categorias(a["por_categoria"], n) if a["por_categoria"] else []
    for r in ranking:
        if r["cambio"] == float("inf"):
            r["cambio"] = "nuevo"
    i_max = max(range(len(vals)), key=vals.__getitem__)
    prom = (sum(vals) / len(vals)) or 1
    return {
        "periodos": [p.isoformat() for p in per], "valores": vals,
        "media_movil": m.media_movil(vals, {"D": 7, "W": 4, "M": 3}[freq]) if len(vals) > 3 else [],
        "pronostico": {"periodos": [f.isoformat() for f in pr["fechas"]], "valores": pr["valores"]},
        "kpis": {"total": sum(vals), "promedio": sum(vals) / len(vals), "crecimiento": m.crecimiento(vals, n),
                 "ventana": n, "mejor": {"periodo": per[i_max].isoformat(), "valor": vals[i_max]},
                 "pendiente_pct": pr["pendiente"] / prom * 100, "factores_dia": pr.get("factores_dia")},
        "ranking": ranking, "por_categoria": a["por_categoria"],
        "incompleto": a["periodo_incompleto_excluido"], "descartadas": a["descartadas"], "freq": freq,
    }


def accion_alertas(_d):
    hist = E.db.historial(200)
    return {"terminos": E.db.terminos(), "auto": bool(E.cfg.get("auto_escaneo")),
            "intervalo": E.cfg.get("intervalo_min", 60), "ultimo": E.ultimo_escaneo, "escaneando": E.escaneando,
            "historial": [{"fecha": h[0], "termino": h[1], "fuente": h[2], "valor": h[3], "normal": h[4], "z": h[5],
                           "cambio": h[6], "pico": bool(h[7]), "detalle": h[8]} for h in hist]}


def accion_alerta_agregar(d):
    for t in d.get("terminos", []) or [d.get("termino", "")]:
        if t and t.strip():
            E.db.agregar_termino(t.strip())
    return accion_alertas({})


def accion_alerta_desde_mercado(_d):
    mer = E.mercado
    if not mer:
        raise m.ErrorFuente("Primero crea o elige tu mercado.")
    for p in mer.palabras[:6]:
        E.db.agregar_termino(p)
    return accion_alertas({})


def accion_alerta_quitar(d):
    E.db.quitar_termino(d.get("termino", ""))
    return accion_alertas({})


def escanear(avanzar=None):
    if E.escaneando:
        raise m.ErrorFuente("Ya se está revisando la lista.")
    terminos = E.db.terminos()
    if not terminos:
        raise m.ErrorFuente("Agrega al menos una palabra a vigilar.")
    E.escaneando = True
    try:
        mer, todas = E.mercado, []
        for i, t in enumerate(terminos):
            if avanzar:
                avanzar(100 * i / len(terminos), f"Revisando «{t}» ({i + 1} de {len(terminos)})")
            for lect in m.escanear_termino(t, E.cfg, E.gt, mer):
                E.db.guardar_lectura(lect)
                todas.append(lect)
            time.sleep(2)
        picos = [lect for lect in todas if lect["es_pico"]]
        if picos:
            E.avisos.append({"fecha": dt.datetime.now().isoformat(timespec="minutes"),
                             "picos": [{"termino": p["termino"], "fuente": p["fuente"], "detalle": p["detalle"],
                                        "cambio": p["cambio"]} for p in picos]})
            if E.cfg.get("sonido", True) and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except RuntimeError:
                    pass
        E.ultimo_escaneo = dt.datetime.now().isoformat(timespec="minutes")
        return {"lecturas": len(todas), "picos": len(picos)}
    finally:
        E.escaneando = False


def accion_alerta_escanear(_d):
    return {"trabajo": E.trabajo("alertas", escanear)}


def accion_avisos(_d):
    avisos, E.avisos = E.avisos, []
    return {"avisos": avisos}


def accion_trabajo(d):
    t = E.trabajos.get(d.get("id", ""))
    if not t:
        raise m.ErrorFuente("Ese proceso ya no existe.")
    return {k: t[k] for k in ("id", "nombre", "estado", "pct", "paso", "resultado", "error")} | \
        {"segundos": round(time.time() - t["inicio"])}


def accion_abrir(d):
    url = d.get("url") or ""
    if url.startswith(("http://", "https://")):
        webbrowser.open(url)
    elif url == "carpeta":
        os.makedirs(m.APP_DIR, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(m.APP_DIR)  # noqa: S606
    return {"ok": True}


def accion_exportar(d):
    """Guarda una tabla como CSV en Descargas y abre la carpeta."""
    carpeta = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(carpeta):
        carpeta = os.path.expanduser("~")
    nombre = re.sub(r"[^\w\-]+", "_", d.get("nombre") or "radar") + f"_{dt.date.today()}.csv"
    ruta = os.path.join(carpeta, nombre)
    m.exportar_csv(ruta, d.get("columnas", []), d.get("filas", []))
    if hasattr(os, "startfile"):
        try:
            os.startfile(carpeta)  # noqa: S606
        except OSError:
            pass
    return {"ruta": ruta}


def accion_actualizacion(_d):
    return {"nueva": m.buscar_actualizacion()}


ACCIONES = {
    "estado": accion_estado, "config": accion_config, "config/claves": accion_config_claves,
    "mercado/sugerir": accion_sugerir, "mercado/guardar": accion_guardar_mercado,
    "mercado/activar": accion_activar, "mercado/borrar": accion_borrar_mercado, "mercado/excluir": accion_excluir,
    "analizar": accion_analizar, "analisis/ultimo": accion_ultimo_analisis, "comparar": accion_comparar,
    "redes": accion_redes, "datos/leer": accion_datos_leer, "datos/analizar": accion_datos_analizar,
    "alertas": accion_alertas, "alertas/agregar": accion_alerta_agregar,
    "alertas/desde_mercado": accion_alerta_desde_mercado, "alertas/quitar": accion_alerta_quitar,
    "alertas/escanear": accion_alerta_escanear, "avisos": accion_avisos, "trabajo": accion_trabajo,
    "abrir": accion_abrir, "exportar": accion_exportar, "actualizacion": accion_actualizacion,
}


# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------
class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *_a):     # silencioso
        pass

    def _responder(self, codigo, cuerpo: bytes, tipo="application/json; charset=utf-8"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta in ("/", "/index.html"):
            ruta = "/index.html"
        archivo = os.path.normpath(ruta_recurso("ui", ruta.lstrip("/")))
        if not archivo.startswith(os.path.normpath(ruta_recurso("ui"))) or not os.path.isfile(archivo):
            return self._responder(404, b"No encontrado", "text/plain")
        tipo = mimetypes.guess_type(archivo)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        with open(archivo, "rb") as f:
            self._responder(200, f.read(), tipo)

    def do_POST(self):
        nombre = urlparse(self.path).path.removeprefix("/api/")
        fn = ACCIONES.get(nombre)
        if not fn:
            return self._responder(404, b'{"error": "No existe"}')
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            datos = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
            resultado = {"ok": True, **_json(fn(datos))}
        except m.ErrorFuente as e:
            resultado = {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            ruta = registrar_error(traceback.format_exc())
            resultado = {"ok": False, "error": f"Error inesperado: {e}. Detalle en {ruta}"}
        self._responder(200, json.dumps(resultado, ensure_ascii=False).encode("utf-8"))


def _vigilancia_automatica():
    """Revisa la lista de alertas cada N minutos si está activado."""
    proxima = time.time() + 120
    while True:
        time.sleep(30)
        if not E.cfg.get("auto_escaneo") or time.time() < proxima:
            continue
        proxima = time.time() + max(15, int(E.cfg.get("intervalo_min", 60))) * 60
        try:
            if E.db.terminos() and not E.escaneando:
                escanear()
        except Exception:  # noqa: BLE001
            registrar_error(traceback.format_exc())


def iniciar(puerto: int = 0) -> tuple[ThreadingHTTPServer, int]:
    """Arranca el servidor en un hilo. Regresa (servidor, puerto)."""
    global E
    E = Estado()
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=_vigilancia_automatica, daemon=True).start()
    return srv, srv.server_address[1]
