# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro - servidor interno.

La ventana del programa es una página web local (carpeta ui/) que habla con este
servidor en 127.0.0.1. Las consultas largas corren en segundo plano como "trabajos"
y la interfaz consulta su avance (porcentaje + paso) para la barra de carga.
"""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import analisis as an
import motor as m


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


# ---------------------------------------------------------------------------
# Estado compartido
# ---------------------------------------------------------------------------
class Estado:
    def __init__(self):
        self.lock = threading.RLock()
        self.cfg = m.cargar_config()
        self.trabajos: dict[str, dict] = {}
        self._quitar_restos_de_versiones_viejas()

    def _quitar_restos_de_versiones_viejas(self):
        """Las versiones 1.x guardaban mercados, análisis y alertas en esta carpeta. Ya no se usan."""
        for nombre in ("analisis", "radar.db"):
            ruta = os.path.join(m.APP_DIR, nombre)
            if os.path.isdir(ruta):
                shutil.rmtree(ruta, ignore_errors=True)
            elif os.path.isfile(ruta):
                try:
                    os.remove(ruta)
                except OSError:
                    pass

    def guardar(self):
        with self.lock:
            m.guardar_config(self.cfg)

    # ---------------------------------------------------- trabajos en segundo plano
    def trabajo(self, nombre: str, fn) -> str:
        """fn recibe una función avanzar(pct, paso) y regresa el resultado."""
        tid = uuid.uuid4().hex[:10]
        t = {"id": tid, "nombre": nombre, "estado": "corriendo", "pct": 0, "paso": "Empezando…",
             "resultado": None, "error": None, "inicio": time.time()}
        self.trabajos[tid] = t

        def avanzar(pct, paso):
            t["pct"], t["paso"] = max(t["pct"], min(99, int(pct))), paso

        def correr():
            try:
                t["resultado"] = _json(fn(avanzar))
                t["pct"], t["estado"] = 100, "listo"
            except m.ErrorFuente as e:
                t["error"], t["estado"] = str(e), "error"
            except Exception as e:  # noqa: BLE001
                registrar_error(traceback.format_exc())
                t["error"], t["estado"] = f"Error inesperado: {e}", "error"

        threading.Thread(target=correr, daemon=True).start()
        return tid


E: Estado | None = None


# ---------------------------------------------------------------------------
# Acciones (una función por botón de la interfaz)
# ---------------------------------------------------------------------------
CLAVES_AJUSTES = ("pais", "youtube_api_key", "pinterest_token", "instagram_token", "instagram_usuario")


def _resumen_claves(cfg: dict) -> dict:
    return {"youtube": bool(cfg["youtube_api_key"]), "pinterest": bool(cfg["pinterest_token"]),
            "instagram": bool(cfg["instagram_token"] and cfg["instagram_usuario"])}


def accion_estado(_d):
    cfg = E.cfg
    return {"version": m.APP_VERSION, "pais": cfg["pais"],
            "paises": [{"codigo": c, "nombre": n} for c, n in m.PAISES.items()],
            "claves": _resumen_claves(cfg),
            "pegados": {red: {"fecha": v.get("fecha"), "lineas": v.get("lineas")} for red, v in cfg["pegados"].items()}}


def accion_config_claves(_d):
    return {k: E.cfg.get(k, "") for k in CLAVES_AJUSTES}


def accion_config(d):
    with E.lock:
        if d.get("pais") and d["pais"] not in m.PAISES:
            raise m.ErrorFuente("Ese país no está en la lista.")
        for k in CLAVES_AJUSTES:
            if k in d:
                E.cfg[k] = str(d[k] or "").strip()
        E.guardar()
    return accion_estado({})


def accion_probar_instagram(_d):
    cfg = E.cfg
    r = m.instagram_hashtag(cfg["instagram_token"], cfg["instagram_usuario"], "viral", 3)
    return {"ok": True, "publicaciones": len(r["publicaciones"])}


def _pais_de(d) -> str:
    pais = (d.get("pais") or E.cfg["pais"]).upper()
    if pais != m.MUNDO and pais not in m.PAISES:
        raise m.ErrorFuente("Ese país no está en la lista.")
    return pais


def accion_virales(d):
    cfg, pais, filtro = dict(E.cfg), _pais_de(d), (d.get("filtro") or "")[:80]
    return {"trabajo": E.trabajo("virales", lambda av: an.virales(cfg, pais, filtro, av))}


def accion_por_lugar(d):
    seleccion = [str(p).upper() for p in (d.get("paises") or [])][:20]
    if not seleccion:
        raise m.ErrorFuente("Elige al menos un país o el mundo.")
    return {"trabajo": E.trabajo("por_lugar", lambda av: an.por_lugar(seleccion, av))}


def accion_ia(d):
    cfg, pais = dict(E.cfg), _pais_de(d)
    if pais == m.MUNDO:
        raise m.ErrorFuente("Las tendencias de IA se miden por país. Elige uno.")
    return {"trabajo": E.trabajo("ia", lambda av: an.tendencias_ia(cfg, pais, av))}


def accion_copys(d):
    return {"copys": an.generar_copys(d.get("tema", ""), d.get("formato", ""), d.get("tono", ""),
                                      [str(h)[:40] for h in (d.get("hashtags") or [])][:12])}


def accion_hashtags(d):
    cfg, pais = dict(E.cfg), _pais_de(d)
    if pais == m.MUNDO:
        pais = "MX"       # YouTube e Instagram funcionan por país; el mundo se consulta por países en «Por lugar»
    temas = [str(t)[:60] for t in (d.get("temas") or [])][:3]
    return {"trabajo": E.trabajo("hashtags", lambda av: an.hashtags_tendencia(cfg, pais, temas, av))}


def accion_pegar(d):
    red = (d.get("red") or "").lower()
    if red not in ("tiktok", "facebook"):
        raise m.ErrorFuente("Esa red no se puede analizar aquí.")
    texto = d.get("texto") or ""
    if len(texto.strip()) < 40:
        raise m.ErrorFuente("Pega más texto: abre la página, presiona Ctrl+A y luego Ctrl+C.")
    pegado = an.analizar_pegado(red, texto)
    with E.lock:
        E.cfg["pegados"][red] = pegado
        E.guardar()
    return {"pegado": pegado}


def accion_pegados_borrar(d):
    with E.lock:
        red = (d.get("red") or "").lower()
        if red:
            E.cfg["pegados"].pop(red, None)
        else:
            E.cfg["pegados"] = {}
        E.guardar()
    return accion_estado({})


def accion_pegados_ver(d):
    red = (d.get("red") or "").lower()
    if red not in E.cfg["pegados"]:
        raise m.ErrorFuente("Todavía no has pegado nada de esa red.")
    return {"pegado": E.cfg["pegados"][red]}


def accion_trabajo(d):
    t = E.trabajos.get(d.get("id", ""))
    if not t:
        raise m.ErrorFuente("Ese proceso ya no existe.")
    return {k: t[k] for k in ("id", "nombre", "estado", "pct", "paso", "resultado", "error")} | \
        {"segundos": round(time.time() - t["inicio"])}


def accion_abrir(d):
    url = d.get("url") or ""
    if url.startswith(("http://", "https://")) and d.get("dentro"):
        # Ventana dentro del programa (misma sesión de la ventana: inicia sesión una vez y se recuerda)
        try:
            import webview
            if webview.windows:
                webview.create_window(d.get("titulo") or "Radar de Tendencias Pro", url, width=1200, height=850)
                return {"ok": True, "dentro": True}
        except Exception:  # noqa: BLE001
            pass
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
    "config/probar_instagram": accion_probar_instagram,
    "virales": accion_virales, "por_lugar": accion_por_lugar, "ia": accion_ia,
    "copys": accion_copys, "hashtags": accion_hashtags,
    "pegar": accion_pegar, "pegados/ver": accion_pegados_ver, "pegados/borrar": accion_pegados_borrar,
    "trabajo": accion_trabajo, "abrir": accion_abrir, "exportar": accion_exportar,
    "actualizacion": accion_actualizacion,
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


def iniciar(puerto: int = 0) -> tuple[ThreadingHTTPServer, int]:
    """Arranca el servidor en un hilo. Regresa (servidor, puerto)."""
    global E
    E = Estado()
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]
