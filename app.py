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


TEXTO_PRUEBA = """Vals sorpresa de xv años con chambelanes #xvaños #vals #chambelanes
1.2M
vestido lila para xv años #vestidoxv #xvaños
856K
baile sorpresa xv años 2026 #bailesorpresa #vals"""


def _autoprueba(ruta_salida: str) -> int:
    """Arranca el servidor y revisa cada sección con internet real (lo corre GitHub Actions)."""
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

        vir = esperar(post("virales", {"pais": "MX"})["trabajo"])
        v = vir.get("resultado") or {}
        resultado["pasos"]["virales"] = {
            "estado": vir["estado"], "error": vir.get("error"), "errores": v.get("errores"),
            "temas": [(t["tema"], t["paises"]) for t in v.get("temas", [])][:8],
            "videos": len(v.get("videos") or []), "pinterest": len(v.get("pinterest") or [])}

        lug = esperar(post("por_lugar", {"paises": ["MX", "US", "ES"]})["trabajo"])
        lu = lug.get("resultado") or {}
        resultado["pasos"]["por_lugar"] = {
            "estado": lug["estado"], "error": lug.get("error"), "errores": lu.get("errores"),
            "repetidos": [(r["tema"], r["paises"]) for r in lu.get("repetidos", [])][:5]}

        cop = post("copys", {"tema": "vals de xv años", "formato": "Reel o TikTok", "tono": "Cercano",
                             "hashtags": ["xvaños"]})
        resultado["pasos"]["copys"] = {"ok": cop["ok"], "variantes": len((cop.get("copys") or {}).get("variantes", []))}

        pg = post("pegar", {"red": "tiktok", "texto": TEXTO_PRUEBA})
        resultado["pasos"]["pegar"] = {"ok": pg["ok"], "error": pg.get("error"),
                                       "hashtags": [h["hashtag"] for h in (pg.get("pegado") or {}).get("hashtags", [])][:5]}

        ht = esperar(post("hashtags", {"pais": "MX", "temas": ["vals"]})["trabajo"])
        h = ht.get("resultado") or {}
        resultado["pasos"]["hashtags"] = {"estado": ht["estado"], "error": ht.get("error"),
                                          "mejores": [x["hashtag"] for x in h.get("mejores", [])][:8],
                                          "errores": h.get("errores")}

        ia = esperar(post("ia", {"pais": "MX"})["trabajo"])
        i = ia.get("resultado") or {}
        resultado["pasos"]["ia"] = {"estado": ia["estado"], "error": ia.get("error"),
                                    "terminos": [(t["palabra"], t["veredicto"]) for t in i.get("terminos", [])][:6],
                                    "subiendo": [x["busqueda"] for x in i.get("subiendo", [])][:4],
                                    "noticias": len(i.get("noticias") or []), "errores": i.get("errores")}

        # Lo obligatorio: virales, por lugar, copys, lo pegado y hashtags. La IA depende de Google y solo se informa.
        resultado["ok"] = (vir["estado"] == "listo" and bool(v.get("temas")) and lug["estado"] == "listo"
                           and bool(lu.get("por_pais")) and cop["ok"] and pg["ok"] and ht["estado"] == "listo")
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
            res["texto"] = ventana.evaluate_js("document.querySelector('.logo').innerText")
            res["ok"] = (res["menu"] or 0) >= 7 and "Radar" in (res["texto"] or "")
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
    cargo = {"ok": False}
    try:
        ventana = webview.create_window(m.APP_NOMBRE, url, width=1380, height=900, min_size=(1100, 700),
                                        background_color="#F4F7FC", text_select=True)
        ventana.events.loaded += lambda: cargo.update(ok=True)
        webview.start(private_mode=False, storage_path=os.path.join(m.APP_DIR, "ventana"))
    except Exception:  # noqa: BLE001
        _respaldo_navegador(url, traceback.format_exc())
        return 0
    if not cargo["ok"]:
        # La ventana se cerró sin llegar a mostrar la interfaz (por ejemplo, falta WebView2)
        _respaldo_navegador(url, "La ventana propia no llegó a cargar la interfaz.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
