# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro: arranque del programa.

Abre la interfaz (carpeta ui/) en una ventana propia de Windows usando pywebview
(Microsoft Edge WebView2). Si eso no está disponible, la abre en el navegador.

Modo de autoprueba (lo usa GitHub Actions para revisar el .exe):
    RadarTendenciasPro.exe --prueba resultado.json
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
import urllib.request


def _autoprueba(ruta_salida: str) -> int:
    """Arranca el servidor, crea un mercado de prueba y corre un análisis real con internet."""
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="radar_prueba_")   # no tocar datos reales
    import servidor  # noqa: E402  (después de cambiar APPDATA)

    resultado = {"ok": False, "pasos": {}}
    try:
        _, puerto = servidor.iniciar()
        base = f"http://127.0.0.1:{puerto}"

        def post(accion, datos=None):
            req = urllib.request.Request(f"{base}/api/{accion}", data=json.dumps(datos or {}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())

        def esperar(tid, limite=420):
            fin = time.time() + limite
            while time.time() < fin:
                t = post("trabajo", {"id": tid})
                if t["estado"] != "corriendo":
                    return t
                time.sleep(2)
            return {"estado": "tiempo agotado"}

        with urllib.request.urlopen(base + "/", timeout=20) as r:
            resultado["pasos"]["interfaz"] = r.status == 200 and b"Radar de Tendencias" in r.read()
        resultado["pasos"]["estado"] = post("estado")["ok"]
        sug = esperar(post("mercado/sugerir", {"nombre": "salones de fiestas"})["trabajo"])
        resultado["pasos"]["sugerir"] = {"estado": sug["estado"], "error": sug.get("error"),
                                         "marcadas": [p["texto"] for p in (sug.get("resultado") or {}).get("palabras", [])
                                                      if p["marcada"]][:12]}
        plantilla = servidor.m.PLANTILLAS_MERCADO["Salones de fiestas y eventos"]
        resultado["pasos"]["guardar"] = post("mercado/guardar", {"nombre": "Prueba salones",
                                                                  "palabras": plantilla["palabras"][:4],
                                                                  "excluir": plantilla["excluir"]})["ok"]
        an = esperar(post("analizar")["trabajo"])
        rep = an.get("resultado") or {}
        resultado["pasos"]["analizar"] = {
            "estado": an["estado"], "error": an.get("error"), "errores_secciones": rep.get("errores"),
            "avisos": rep.get("avisos"),
            "palabras": [(p["palabra"], p["veredicto"], p.get("cambio"), p.get("popularidad")) for p in rep.get("palabras", [])],
            "despegan": {k: [x["busqueda"] for x in v][:6] for k, v in (rep.get("despegan") or {}).items()},
            "preguntas": [x["pregunta"] for x in rep.get("preguntas", [])][:8],
            "hoy_total": rep.get("hoy_total"), "noticias_total": (rep.get("noticias") or {}).get("total"),
            "redes": {k: {"estado": v.get("estado"), "error": (v.get("error") or "")[:120],
                          "veredictos": [(p["palabra"], p["veredicto"]) for p in v.get("palabras", [])][:3],
                          "suben": [x["busqueda"] for x in v.get("suben", [])][:4],
                          "sugerencias": [x["texto"] for x in v.get("sugerencias", [])][:4]}
                      for k, v in ((rep.get("redes") or {}).get("redes") or {}).items()},
            "coinciden": [(c["busqueda"], c["fuentes"]) for c in (rep.get("redes") or {}).get("coinciden", [])][:5],
        }
        resultado["pasos"]["analizar"]["despegan"] = {k: v[:3] for k, v in resultado["pasos"]["analizar"]["despegan"].items()}
        resultado["ok"] = an["estado"] == "listo" and bool(rep.get("palabras"))
    except Exception:  # noqa: BLE001
        resultado["traza"] = traceback.format_exc()
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1, default=str)
    return 0 if resultado["ok"] else 1


def _respaldo_navegador(url: str, motivo: str) -> None:
    """Sin ventana propia: abre el navegador y deja una ventanita para cerrar el programa."""
    import webbrowser

    import servidor
    servidor.registrar_error(f"No se pudo abrir la ventana propia, se usa el navegador.\n{motivo}")
    webbrowser.open(url)
    try:
        import tkinter as tk
        r = tk.Tk()
        r.title("Radar de Tendencias Pro")
        r.geometry("440x150")
        tk.Label(r, text="Radar de Tendencias Pro está abierto en tu navegador.\n"
                         "Deja esta ventana abierta mientras lo usas.\nCiérrala para salir del programa.",
                 font=("Segoe UI", 10), justify="center").pack(expand=True)
        tk.Button(r, text="Volver a abrir", command=lambda: webbrowser.open(url)).pack(pady=(0, 14))
        r.mainloop()
    except Exception:  # noqa: BLE001
        while True:
            time.sleep(3600)


def _prueba_ventana(ruta_salida: str) -> int:
    """Abre la ventana real, revisa que la interfaz cargue y se cierra sola."""
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="radar_ventana_")
    import servidor
    import webview
    _, puerto = servidor.iniciar()
    res = {"ok": False}
    ventana = webview.create_window("Prueba", f"http://127.0.0.1:{puerto}/", width=1200, height=800)

    def revisar():
        try:
            time.sleep(6)
            res["titulo"] = ventana.evaluate_js("document.title")
            res["menu"] = ventana.evaluate_js("document.querySelectorAll('#menu button').length")
            res["texto"] = ventana.evaluate_js("document.querySelector('#contenido').innerText.slice(0, 120)")
            res["ok"] = res["menu"] == 7 and "Bienvenido" in (res["texto"] or "")
        except Exception:  # noqa: BLE001
            res["traza"] = traceback.format_exc()
        finally:
            with open(ruta_salida, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
            ventana.destroy()

    webview.start(revisar)
    return 0 if res["ok"] else 1


def main() -> int:
    if "--prueba-ventana" in sys.argv:
        i = sys.argv.index("--prueba-ventana")
        return _prueba_ventana(sys.argv[i + 1] if len(sys.argv) > i + 1 else "prueba_ventana.json")
    if "--prueba" in sys.argv:
        i = sys.argv.index("--prueba")
        salida = sys.argv[i + 1] if len(sys.argv) > i + 1 else "prueba_radar.json"
        return _autoprueba(salida)

    if sys.platform == "win32":
        try:  # texto nítido con escala de pantalla 125 %, 150 %…
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass

    import motor as m
    import servidor
    try:
        _, puerto = servidor.iniciar()
    except Exception:  # noqa: BLE001
        servidor.registrar_error(traceback.format_exc())
        raise
    url = f"http://127.0.0.1:{puerto}/"

    try:
        import webview
    except Exception:  # noqa: BLE001
        _respaldo_navegador(url, traceback.format_exc())
        return 0
    try:
        webview.create_window(m.APP_NOMBRE, url, width=1380, height=900, min_size=(1100, 700),
                              background_color="#F4F7FC", text_select=True)
        webview.start(private_mode=False, storage_path=os.path.join(m.APP_DIR, "ventana"))
    except Exception:  # noqa: BLE001
        _respaldo_navegador(url, traceback.format_exc())
    return 0


if __name__ == "__main__":
    sys.exit(main())
