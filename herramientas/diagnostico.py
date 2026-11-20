"""Prueba cada fuente de datos con internet real y guarda lo que regresa en diagnostico/resultado.json.
Lo corre GitHub Actions (workflow diagnostico.yml)."""
import json, os, sys, time, traceback, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import motor as m

salida = {"fecha": dt.datetime.now().isoformat(), "pruebas": {}}

def prueba(nombre, fn):
    t = time.time()
    try:
        r = fn()
        salida["pruebas"][nombre] = {"ok": True, "seg": round(time.time() - t, 1), "resultado": r}
    except Exception as e:
        salida["pruebas"][nombre] = {"ok": False, "seg": round(time.time() - t, 1), "error": f"{type(e).__name__}: {e}",
                                      "traza": traceback.format_exc()[-1500:]}
    print(nombre, "OK" if salida["pruebas"][nombre]["ok"] else salida["pruebas"][nombre]["error"], flush=True)

def ser(x):
    return json.loads(json.dumps(x, default=str))

prueba("autocompletar_bodas", lambda: ser(m.ideas_palabras("bodas", modificadores=["", " precio", " cerca de mi"])))
prueba("autocompletar_xv", lambda: ser(m.ideas_palabras("xv", modificadores=["", " años"])))
prueba("sugerir_bodas", lambda: m.sugerir_palabras_mercado("bodas"))
prueba("sugerir_xv_anos", lambda: m.sugerir_palabras_mercado("xv años"))
prueba("tendencias_hoy", lambda: ser(m.tendencias_del_dia("MX")[:8]))
prueba("noticias_bodas", lambda: ser(m.menciones_noticias('bodas ("salón de fiestas" OR boda)', 7)[:5]))
gt = m.GoogleTrends("MX", "es-419", 360)
prueba("trends_interes_1", lambda: ser({k: v[-10:] for k, v in gt.interes_en_el_tiempo(["bodas"], "today 3-m")[1].items()}))
time.sleep(3)
prueba("trends_interes_5", lambda: ser({k: v[-5:] for k, v in gt.interes_en_el_tiempo(["bodas", "xv años", "boda civil", "salón de fiestas", "bautizo"], "today 3-m")[1].items()}))
time.sleep(3)
prueba("trends_relacionadas", lambda: ser(gt.relacionadas("bodas", "today 3-m")))
time.sleep(3)
prueba("trends_7d", lambda: ser({k: v[-10:] for k, v in gt.interes_en_el_tiempo(["xv años"], "now 7-d")[1].items()}))

os.makedirs("diagnostico", exist_ok=True)
with open("diagnostico/resultado.json", "w", encoding="utf-8") as f:
    json.dump(salida, f, ensure_ascii=False, indent=1)
