# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro - motor de datos.

Aquí vive todo lo que NO es interfaz: consultas a las fuentes
(Google Trends, autocompletado de Google, Pinterest Trends, YouTube,
Google Noticias), el análisis de tus propios datos de venta y la base
de datos de alertas. La interfaz (app.py) solo llama a estas funciones.
"""
from __future__ import annotations

import csv
import datetime as dt
import email.utils
import json
import math
import os
import sqlite3
import statistics
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET

import requests

# ---------------------------------------------------------------------------
# Configuración y rutas
# ---------------------------------------------------------------------------
APP_NOMBRE = "Radar de Tendencias Pro"
APP_VERSION = "1.1.0"   # GitHub Actions lo reemplaza con la versión de la etiqueta (v1.2.3)
REPO_URL = "https://github.com/danimakerbro-cloud/radar-tendencias-pro"
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RadarTendenciasPro")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DB_PATH = os.path.join(APP_DIR, "radar.db")

CONFIG_DEFECTO = {
    "pais": "MX",                # código de país para Google/YouTube/Pinterest ("" = mundial)
    "idioma": "es-419",          # idioma de la interfaz de Google (es-419 = español de Latinoamérica)
    "zona_horaria_min": 360,     # minutos de diferencia con UTC (CDMX = 360)
    "youtube_api_key": "",
    "pinterest_token": "",
    "intervalo_min": 60,         # escaneo automático de alertas
    "umbral_z": 2.0,             # qué tan fuerte debe ser un pico para avisar
    "sonido": True,
    "mercados": {},              # {nombre: {"palabras": [...], "excluir": [...], "pinterest": "..."}}
    "mercado_activo": "",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def cargar_config() -> dict:
    cfg = json.loads(json.dumps(CONFIG_DEFECTO))   # copia profunda: no tocar los valores por defecto
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def guardar_config(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class ErrorFuente(Exception):
    """Error entendible para mostrar al usuario."""


def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "es-MX,es;q=0.9,en;q=0.6"})
    return s


def _gl(pais: str) -> str:
    return (pais or "US").upper()


def _texto_respuesta(r: requests.Response) -> str:
    """Decodifica sin depender de que el servidor declare bien el charset."""
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        return r.content.decode("latin-1")


# ---------------------------------------------------------------------------
# MI MERCADO: todo el análisis se limita al giro que elija el usuario
# ---------------------------------------------------------------------------
PLANTILLAS_MERCADO = {
    "Salones de fiestas y eventos": {
        "palabras": ["salón de fiestas", "salón de eventos", "jardín de eventos", "boda", "xv años",
                     "fiesta infantil", "banquetes", "graduación", "posada", "decoración de eventos",
                     "renta de mobiliario", "bautizo"],
        "excluir": ["empleo", "vacantes", "videojuego"], "pinterest": "event_planning"},
    "Oficinas y espacios de trabajo": {
        "palabras": ["renta de oficinas", "oficina virtual", "coworking", "sala de juntas",
                     "oficinas amuebladas", "domicilio fiscal", "espacio de trabajo", "oficina en renta",
                     "home office"],
        "excluir": ["empleo", "vacantes", "microsoft office"], "pinterest": "design"},
    "Cafeterías": {
        "palabras": ["cafetería", "café", "café de especialidad", "matcha", "frappé", "latte", "chai",
                     "postres", "brunch", "pan dulce"],
        "excluir": ["empleo", "vacantes"], "pinterest": "food_and_drinks"},
    "Restaurantes": {
        "palabras": ["restaurante", "comida", "tacos", "menú", "comida a domicilio", "brunch", "mariscos",
                     "pizza", "hamburguesas", "sushi"],
        "excluir": ["empleo", "vacantes", "receta"], "pinterest": "food_and_drinks"},
    "Tiendas de ropa": {
        "palabras": ["ropa", "outfit", "vestidos", "tenis", "moda", "ropa de mujer", "ropa de hombre",
                     "chamarras", "jeans"],
        "excluir": ["empleo", "vacantes"], "pinterest": "womens_fashion"},
    "Gimnasios y fitness": {
        "palabras": ["gimnasio", "gym", "entrenamiento", "pilates", "yoga", "crossfit", "proteína",
                     "rutina de ejercicio"],
        "excluir": ["empleo", "vacantes"], "pinterest": "sport"},
}

_VACIAS = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "para", "con", "a", "al", "un", "una",
           "por", "o", "u", "mi", "tu", "su", "que", "se", "lo"}


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin signos: «Salón de Fiestas!» -> «salon de fiestas»."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return "".join(c if c.isalnum() else " " for c in t)


def _raiz(tok: str) -> str:
    """Quita el plural para que «salones» = «salón» y «fiestas» = «fiesta»."""
    if len(tok) > 4 and tok.endswith("es") and tok[-3] in "lnrdzj":
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok


def _tokens(texto: str) -> frozenset:
    return frozenset(_raiz(t) for t in normalizar(texto).split() if t not in _VACIAS)


class Mercado:
    """Un mercado o giro: su nombre, las palabras que lo definen y las que hay que ignorar."""

    def __init__(self, nombre: str, palabras=(), excluir=(), pinterest: str = ""):
        self.nombre = (nombre or "").strip()
        self.palabras = [p.strip() for p in palabras if p and p.strip()] or ([self.nombre] if self.nombre else [])
        self.excluir = [p.strip() for p in excluir if p and p.strip()]
        self.pinterest = pinterest or ""
        self._claves = [k for k in (_tokens(p) for p in self.palabras + [self.nombre]) if k]
        self._excl = [k for k in (_tokens(p) for p in self.excluir) if k]

    @classmethod
    def desde_dict(cls, nombre: str, d: dict) -> "Mercado":
        return cls(nombre, d.get("palabras", []), d.get("excluir", []), d.get("pinterest", ""))

    def a_dict(self) -> dict:
        return {"palabras": self.palabras, "excluir": self.excluir, "pinterest": self.pinterest}

    @property
    def principal(self) -> str:
        return self.palabras[0] if self.palabras else self.nombre

    def excluido(self, texto: str) -> bool:
        toks = _tokens(texto)
        return any(e <= toks for e in self._excl)

    def coincide(self, texto: str) -> bool:
        """¿El texto habla de este mercado? (todas las palabras de alguna clave aparecen en él)."""
        toks = _tokens(texto)
        if any(e <= toks for e in self._excl):
            return False
        return any(c <= toks for c in self._claves)

    def ajustar_termino(self, termino: str) -> str:
        """«decoración» en Salones -> «decoración salón de fiestas»; si ya es del mercado, se deja igual."""
        termino = termino.strip()
        return termino if self.coincide(termino) else f"{termino} {self.principal}".strip()

    def _or(self, n: int = 8, sep: str = " OR ") -> str:
        return sep.join(f'"{p}"' if " " in p else p for p in self.palabras[:n])

    def consulta_noticias(self, tema: str = "") -> str:
        tema = tema.strip()
        q = tema if tema and self.coincide(tema) else f"{tema} ({self._or()})".strip()
        for e in self.excluir[:5]:
            q += f' -"{e}"' if " " in e else f" -{e}"
        return q

    def consulta_youtube(self, tema: str = "") -> str:
        tema = tema.strip()
        if tema:
            return self.ajustar_termino(tema)
        return self._or(6, "|")


def mercado_activo(cfg: dict) -> "Mercado | None":
    nombre = cfg.get("mercado_activo") or ""
    datos = (cfg.get("mercados") or {}).get(nombre)
    return Mercado.desde_dict(nombre, datos) if datos else None


# ---------------------------------------------------------------------------
# 1) BÚSQUEDAS: Google Trends
# ---------------------------------------------------------------------------
PERIODOS_TRENDS = {
    "Última hora": "now 1-H",
    "Últimas 4 horas": "now 4-H",
    "Último día": "now 1-d",
    "Últimos 7 días": "now 7-d",
    "Últimos 30 días": "today 1-m",
    "Últimos 90 días": "today 3-m",
    "Últimos 12 meses": "today 12-m",
    "Últimos 5 años": "today 5-y",
}


def _json_sin_prefijo(texto: str) -> dict:
    """Google Trends antepone basura anti-XSSI (")]}'") a su JSON."""
    i = texto.find("{")
    if i < 0:
        raise ErrorFuente("Google Trends devolvió una respuesta inesperada.")
    return json.loads(texto[i:])


class GoogleTrends:
    """Cliente sencillo de Google Trends (mismos endpoints que usa la web)."""

    BASE = "https://trends.google.com/trends/api"

    def __init__(self, pais: str = "MX", idioma: str = "es-419", tz_min: int = 360):
        self.pais = (pais or "").upper()
        self.idioma = idioma
        self.tz = tz_min
        self.s = _sesion()
        self._cookies_ok = False
        self._lock = threading.Lock()

    def _cookies(self):
        if not self._cookies_ok:
            try:
                self.s.get(f"https://trends.google.com/trends/?geo={self.pais}", timeout=20)
            except requests.RequestException:
                pass
            self._cookies_ok = True

    def _get(self, ruta: str, params: dict) -> dict:
        with self._lock:
            self._cookies()
            espera = 4
            for _ in range(4):
                try:
                    r = self.s.get(f"{self.BASE}/{ruta}", params=params, timeout=30)
                except requests.RequestException as e:
                    raise ErrorFuente(f"No se pudo conectar con Google Trends: {e}")
                if r.status_code == 429:
                    # Google limita las consultas seguidas: esperamos y reintentamos.
                    self._cookies_ok = False
                    time.sleep(espera)
                    espera *= 2
                    self._cookies()
                    continue
                if r.status_code != 200:
                    raise ErrorFuente(f"Google Trends respondió con código {r.status_code}.")
                return _json_sin_prefijo(_texto_respuesta(r))
            raise ErrorFuente("Google Trends está limitando las consultas (demasiadas seguidas). "
                              "Espera unos minutos y vuelve a intentar.")

    def _explorar(self, terminos: list[str], tiempo: str) -> list[dict]:
        req = {
            "comparisonItem": [{"keyword": t, "geo": self.pais, "time": tiempo} for t in terminos],
            "category": 0,
            "property": "",
        }
        datos = self._get("explore", {"hl": self.idioma, "tz": self.tz,
                                      "req": json.dumps(req, separators=(",", ":"))})
        return datos.get("widgets", [])

    def interes_en_el_tiempo(self, terminos: list[str], tiempo: str = "today 3-m"):
        """Regresa (fechas, {termino: [valores 0-100]})."""
        terminos = [t.strip() for t in terminos if t.strip()][:5]
        if not terminos:
            raise ErrorFuente("Escribe al menos un término.")
        widgets = self._explorar(terminos, tiempo)
        w = next((w for w in widgets if w.get("id", "").startswith("TIMESERIES")), None)
        if not w:
            raise ErrorFuente("Google Trends no devolvió datos de interés para esos términos.")
        datos = self._get("widgetdata/multiline", {
            "hl": self.idioma, "tz": self.tz,
            "req": json.dumps(w["request"], separators=(",", ":")),
            "token": w["token"],
        })
        return parsear_serie_trends(datos, terminos)

    def relacionadas(self, termino: str, tiempo: str = "today 3-m") -> dict:
        """Búsquedas relacionadas: {'top': [(consulta, valor)], 'subiendo': [(consulta, crecimiento)]}."""
        widgets = self._explorar([termino.strip()], tiempo)
        w = next((w for w in widgets if w.get("id", "").startswith("RELATED_QUERIES")), None)
        if not w:
            return {"top": [], "subiendo": []}
        datos = self._get("widgetdata/relatedsearches", {
            "hl": self.idioma, "tz": self.tz,
            "req": json.dumps(w["request"], separators=(",", ":")),
            "token": w["token"],
        })
        return parsear_relacionadas(datos)


def parsear_serie_trends(datos: dict, terminos: list[str]):
    linea = datos.get("default", {}).get("timelineData", [])
    fechas, series = [], {t: [] for t in terminos}
    for punto in linea:
        try:
            fechas.append(dt.datetime.fromtimestamp(int(punto["time"])))
        except (KeyError, ValueError):
            continue
        valores = punto.get("value", [])
        for i, t in enumerate(terminos):
            series[t].append(int(valores[i]) if i < len(valores) else 0)
    if not fechas:
        raise ErrorFuente("No hay suficiente volumen de búsqueda para esos términos en ese periodo.")
    return fechas, series


def parsear_relacionadas(datos: dict) -> dict:
    listas = datos.get("default", {}).get("rankedList", [])
    salida = {"top": [], "subiendo": []}
    for i, clave in enumerate(("top", "subiendo")):
        if i < len(listas):
            for kw in listas[i].get("rankedKeyword", []):
                salida[clave].append((kw.get("query", ""), kw.get("formattedValue", str(kw.get("value", "")))))
    return salida


# ---------------------------------------------------------------------------
# 1b) Tendencias del día (Google "Trending now") — RSS público
# ---------------------------------------------------------------------------
def tendencias_del_dia(pais: str = "MX") -> list[dict]:
    url = f"https://trends.google.com/trending/rss?geo={_gl(pais)}"
    try:
        r = _sesion().get(url, timeout=25)
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con Google Trends: {e}")
    if r.status_code != 200:
        raise ErrorFuente(f"Google Trends respondió con código {r.status_code}.")
    return parsear_rss_tendencias(r.content)


def _hijo(elem, nombre):
    """Busca un hijo por nombre ignorando el namespace."""
    for h in elem:
        if h.tag == nombre or h.tag.endswith("}" + nombre):
            return h
    return None


def _hijos(elem, nombre):
    return [h for h in elem if h.tag == nombre or h.tag.endswith("}" + nombre)]


def _txt(elem, nombre, defecto=""):
    h = _hijo(elem, nombre)
    return (h.text or "").strip() if h is not None and h.text else defecto


def _fecha_rss(texto: str):
    try:
        f = email.utils.parsedate_to_datetime(texto)
        return f.astimezone().replace(tzinfo=None) if f.tzinfo else f
    except (TypeError, ValueError):
        return None


def parsear_rss_tendencias(contenido: bytes) -> list[dict]:
    raiz = ET.fromstring(contenido)
    canal = _hijo(raiz, "channel")
    if canal is None:
        return []
    salida = []
    for item in _hijos(canal, "item"):
        noticias = _hijos(item, "news_item")
        primera = noticias[0] if noticias else None
        trafico = _txt(item, "approx_traffic")
        salida.append({
            "tema": _txt(item, "title"),
            "busquedas": trafico,
            "busquedas_num": _numero_trafico(trafico),
            "fecha": _fecha_rss(_txt(item, "pubDate")),
            "noticia": _txt(primera, "news_item_title") if primera is not None else "",
            "medio": _txt(primera, "news_item_source") if primera is not None else "",
            "url": _txt(primera, "news_item_url") if primera is not None else "",
        })
    salida.sort(key=lambda x: x["busquedas_num"], reverse=True)
    return salida


def _numero_trafico(t: str) -> int:
    """'20,000+' / '2 mil+' / '50K+' -> número aproximado."""
    t = (t or "").lower().replace("+", "").replace(" ", " ").strip()
    mult = 1
    if "mill" in t:
        mult, t = 1_000_000, t.split("mill")[0]
    elif "mil" in t:
        mult, t = 1000, t.replace("mil", "")
    elif t.endswith("k"):
        mult, t = 1000, t[:-1]
    elif t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    t = t.strip().replace(" ", "")
    if mult == 1:
        t = t.replace(",", "").replace(".", "")      # 20,000 -> 20000
    else:
        t = t.replace(",", ".")                     # 1,5 mil -> 1.5
    try:
        return int(float(t) * mult)
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# 1c) Ideas de palabras clave (autocompletado de Google)
#     Sustituto gratuito de Keyword Planner: lo que la gente escribe de verdad.
# ---------------------------------------------------------------------------
MODIFICADORES = (
    [""] + [f" {c}" for c in "abcdefghijklmnopqrstuvwxyz"]
    + [" para", " precio", " cerca de mi", " barato", " mejor", " como", " 2026"]
)
PREFIJOS = ["como ", "donde ", "que ", "mejor ", "cuanto cuesta "]


MODIFICADORES_LIGEROS = ["", " precio", " cerca de mi", " para", " ideas", " 2026"]


def ideas_palabras(semilla: str, pais: str = "MX", idioma: str = "es-419",
                   profundo: bool = True, al_avanzar=None, modificadores=None) -> list[tuple[str, int]]:
    """Regresa [(sugerencia, veces_que_apareció)], ordenado por relevancia."""
    semilla = semilla.strip()
    if not semilla:
        raise ErrorFuente("Escribe una palabra o frase semilla.")
    if modificadores is not None:
        consultas = [semilla + m for m in modificadores]
    else:
        consultas = [semilla + m for m in (MODIFICADORES if profundo else [""])]
        if profundo:
            consultas += [p + semilla for p in PREFIJOS]
    s = _sesion()
    conteo: dict[str, int] = {}
    orden: dict[str, int] = {}
    errores = 0
    for i, q in enumerate(consultas):
        try:
            r = s.get("https://suggestqueries.google.com/complete/search",
                      params={"client": "firefox", "hl": idioma.split("-")[0], "gl": _gl(pais).lower(), "q": q},
                      timeout=15)
            sugerencias = json.loads(_texto_respuesta(r))[1] if r.status_code == 200 else []
        except (requests.RequestException, ValueError, IndexError):
            sugerencias, errores = [], errores + 1
        for pos, sug in enumerate(sugerencias):
            sug = sug.strip().lower()
            if not sug or sug == semilla.lower():
                continue
            conteo[sug] = conteo.get(sug, 0) + 1
            orden.setdefault(sug, len(orden) * 10 + pos)
        if al_avanzar:
            al_avanzar(i + 1, len(consultas))
        time.sleep(0.12)
    if not conteo and errores == len(consultas):
        raise ErrorFuente("No se pudo consultar el autocompletado de Google. Revisa tu conexión.")
    return sorted(conteo.items(), key=lambda kv: (-kv[1], orden[kv[0]]))


# ---------------------------------------------------------------------------
# 1d) Pinterest Trends (API oficial v5, requiere token)
# ---------------------------------------------------------------------------
TIPOS_PINTEREST = {
    "Creciendo ahora": "growing",
    "Top del mes": "monthly",
    "Top del año": "yearly",
    "De temporada": "seasonal",
}


def pinterest_tendencias(token: str, region: str = "MX", tipo: str = "growing",
                         intereses: str = "", limite: int = 50) -> list[dict]:
    if not token:
        raise ErrorFuente("Falta el token de Pinterest. Agrégalo en la pestaña Configuración.")
    params = {"limit": limite}
    if intereses.strip():
        params["interests"] = ",".join(i.strip() for i in intereses.split(",") if i.strip())
    try:
        r = requests.get(f"https://api.pinterest.com/v5/trends/keywords/{_gl(region)}/top/{tipo}",
                         headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con Pinterest: {e}")
    if r.status_code != 200:
        try:
            msg = r.json().get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise ErrorFuente(f"Pinterest respondió {r.status_code}: {msg}")
    return parsear_pinterest(r.json())


def parsear_pinterest(datos: dict) -> list[dict]:
    salida = []
    for t in datos.get("trends", []):
        serie = t.get("time_series") or {}
        salida.append({
            "palabra": t.get("keyword", ""),
            "semana": t.get("pct_growth_wow"),
            "mes": t.get("pct_growth_mom"),
            "anio": t.get("pct_growth_yoy"),
            "serie": sorted(serie.items()),
        })
    return salida


# ---------------------------------------------------------------------------
# 1e) Lo mismo, pero para todo un mercado
# ---------------------------------------------------------------------------
def _valor_crecimiento(v: str) -> float:
    """'+350 %' -> 350; 'Aumento puntual'/'Breakout' -> muy alto."""
    n = "".join(c for c in v if c.isdigit())
    return float(n) if n else 1e6


def relacionadas_mercado(gt: GoogleTrends, mercado: Mercado, tiempo: str = "today 1-m",
                         max_palabras: int = 5, al_avanzar=None) -> dict:
    """Búsquedas que suben y las más buscadas para las palabras principales del mercado."""
    subiendo, top, vistos_s, vistos_t, errores = [], [], set(), set(), []
    palabras = mercado.palabras[:max_palabras]
    for i, p in enumerate(palabras):
        if al_avanzar:
            al_avanzar(i + 1, len(palabras), p)
        try:
            r = gt.relacionadas(p, tiempo)
        except ErrorFuente as e:
            errores.append(f"{p}: {e}")
            continue
        for q, v in r["subiendo"]:
            if q.lower() not in vistos_s and not mercado.excluido(q):
                vistos_s.add(q.lower())
                subiendo.append((q, v, p))
        for q, v in r["top"]:
            if q.lower() not in vistos_t and not mercado.excluido(q):
                vistos_t.add(q.lower())
                top.append((q, v, p))
        time.sleep(1.0)
    if errores and not subiendo and not top:
        raise ErrorFuente(errores[0])
    subiendo.sort(key=lambda x: -_valor_crecimiento(x[1]))
    top.sort(key=lambda x: -(float(x[1]) if str(x[1]).isdigit() else 0))
    return {"subiendo": subiendo, "top": top, "errores": errores}


def ideas_mercado(mercado: Mercado, pais: str = "MX", idioma: str = "es-419", al_avanzar=None,
                  max_palabras: int = 6) -> list[tuple[str, int, str]]:
    """Ideas de palabras clave de todo el mercado: [(idea, fuerza, palabra de origen)]."""
    palabras = mercado.palabras[:max_palabras]
    total: dict[str, list] = {}
    for i, p in enumerate(palabras):
        if al_avanzar:
            al_avanzar(i + 1, len(palabras), p)
        try:
            ideas = ideas_palabras(p, pais, idioma, modificadores=None if i == 0 else MODIFICADORES_LIGEROS)
        except ErrorFuente:
            continue
        for sug, c in ideas:
            if mercado.excluido(sug):
                continue
            if sug in total:
                total[sug][0] += c
            else:
                total[sug] = [c, p]
    if not total:
        raise ErrorFuente("No se pudieron obtener ideas del autocompletado de Google. Revisa tu conexión.")
    return sorted(((s, c, o) for s, (c, o) in total.items()), key=lambda x: -x[1])


def sugerir_palabras_mercado(nombre: str, pais: str = "MX", idioma: str = "es-419", n: int = 15) -> list[str]:
    """Propone palabras clave para un mercado nuevo, a partir de lo que la gente busca en Google."""
    ideas = ideas_palabras(nombre, pais, idioma, modificadores=MODIFICADORES_LIGEROS + [" en", " de", " a"])
    vistas, salida = {normalizar(nombre).strip()}, []
    for sug, _ in ideas:
        clave = normalizar(sug).strip()
        if clave not in vistas:
            vistas.add(clave)
            salida.append(sug)
        if len(salida) >= n:
            break
    return salida


def filtrar_por_mercado(items: list[dict], mercado: "Mercado | None", campos=("tema", "noticia")) -> list[dict]:
    if not mercado:
        return items
    return [it for it in items if mercado.coincide(" ".join(str(it.get(c, "")) for c in campos))]


# ---------------------------------------------------------------------------
# 2) REDES: YouTube (API oficial, clave gratuita)
# ---------------------------------------------------------------------------
def _error_google_api(r: requests.Response) -> str:
    try:
        return r.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return r.text[:200]


def youtube_tendencia(api_key: str, consulta: str, dias: int = 7, pais: str = "MX",
                      idioma: str = "es", maximo: int = 25, mercado: "Mercado | None" = None) -> list[dict]:
    """Videos más vistos sobre un tema publicados en los últimos N días, con velocidad de vistas."""
    if not api_key:
        raise ErrorFuente("Falta la clave de YouTube Data API. Agrégala en la pestaña Configuración.")
    if not consulta.strip():
        raise ErrorFuente("Escribe un tema o hashtag.")
    desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = "https://www.googleapis.com/youtube/v3"
    params = {"part": "snippet", "q": consulta, "type": "video", "order": "viewCount",
              "publishedAfter": desde, "maxResults": min(maximo, 50),
              "relevanceLanguage": idioma.split("-")[0], "key": api_key}
    if pais:
        params["regionCode"] = _gl(pais)
    try:
        r = requests.get(f"{base}/search", params=params, timeout=30)
        if r.status_code != 200:
            raise ErrorFuente(f"YouTube: {_error_google_api(r)}")
        ids = [it["id"]["videoId"] for it in r.json().get("items", []) if it.get("id", {}).get("videoId")]
        if not ids:
            return []
        r2 = requests.get(f"{base}/videos", params={"part": "snippet,statistics", "id": ",".join(ids),
                                                    "key": api_key}, timeout=30)
        if r2.status_code != 200:
            raise ErrorFuente(f"YouTube: {_error_google_api(r2)}")
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con YouTube: {e}")
    videos = parsear_videos_youtube(r2.json())
    if mercado:
        videos = [v for v in videos if mercado.coincide(v["texto"])]
    return videos


def parsear_videos_youtube(datos: dict, ahora: dt.datetime | None = None) -> list[dict]:
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    salida = []
    for v in datos.get("items", []):
        sn, st = v.get("snippet", {}), v.get("statistics", {})
        try:
            pub = dt.datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        horas = max((ahora - pub).total_seconds() / 3600, 1)
        vistas = int(st.get("viewCount", 0) or 0)
        likes = int(st.get("likeCount", 0) or 0)
        coments = int(st.get("commentCount", 0) or 0)
        salida.append({
            "titulo": sn.get("title", ""),
            "canal": sn.get("channelTitle", ""),
            "publicado": pub.astimezone().replace(tzinfo=None),
            "vistas": vistas,
            "vistas_hora": round(vistas / horas, 1),
            "likes": likes,
            "comentarios": coments,
            "engagement": round((likes + coments) / vistas * 100, 2) if vistas else 0.0,
            "url": f"https://www.youtube.com/watch?v={v.get('id', '')}",
            "texto": " ".join([sn.get("title", ""), sn.get("description", "")[:400]] + sn.get("tags", [])[:15]),
        })
    salida.sort(key=lambda x: x["vistas_hora"], reverse=True)
    return salida


# ---------------------------------------------------------------------------
# 2b) MENCIONES: Google Noticias (RSS público)
# ---------------------------------------------------------------------------
def menciones_noticias(consulta: str, dias: int = 7, pais: str = "MX", idioma: str = "es-419") -> list[dict]:
    if not consulta.strip():
        raise ErrorFuente("Escribe un tema, marca o hashtag.")
    gl = _gl(pais)
    params = {"q": f"{consulta} when:{dias}d", "hl": idioma, "gl": gl, "ceid": f"{gl}:{idioma}"}
    try:
        r = _sesion().get("https://news.google.com/rss/search", params=params, timeout=25)
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con Google Noticias: {e}")
    if r.status_code != 200:
        raise ErrorFuente(f"Google Noticias respondió con código {r.status_code}.")
    return parsear_rss_noticias(r.content)


def parsear_rss_noticias(contenido: bytes) -> list[dict]:
    raiz = ET.fromstring(contenido)
    canal = _hijo(raiz, "channel")
    if canal is None:
        return []
    salida = []
    for item in _hijos(canal, "item"):
        fecha = _fecha_rss(_txt(item, "pubDate"))
        if fecha is None:
            continue
        salida.append({"fecha": fecha, "titulo": _txt(item, "title"),
                       "medio": _txt(item, "source"), "url": _txt(item, "link")})
    salida.sort(key=lambda x: x["fecha"], reverse=True)
    return salida


def conteo_por_dia(items: list[dict], dias: int, hoy: dt.date | None = None):
    """Cuenta menciones por día, rellenando con 0 los días sin noticias."""
    hoy = hoy or dt.date.today()
    fechas = [hoy - dt.timedelta(days=d) for d in range(dias - 1, -1, -1)]
    conteo = {f: 0 for f in fechas}
    for it in items:
        d = it["fecha"].date()
        if d in conteo:
            conteo[d] += 1
    return fechas, [conteo[f] for f in fechas]


# ---------------------------------------------------------------------------
# Análisis: picos, crecimiento, medias móviles y pronóstico
# ---------------------------------------------------------------------------
def detectar_pico(valores: list[float], umbral_z: float = 2.0, ventana: int = 1) -> dict:
    """Compara lo más reciente contra el comportamiento normal (puntuación z)."""
    vals = [float(v) for v in valores if v is not None]
    if len(vals) < ventana + 3:
        return {"z": 0.0, "cambio_pct": 0.0, "es_pico": False, "reciente": 0.0, "normal": 0.0}
    base, reciente = vals[:-ventana], statistics.fmean(vals[-ventana:])
    mu = statistics.fmean(base)
    sd = statistics.pstdev(base)
    if sd == 0:
        z = 0.0 if reciente <= mu else (99.0 if mu == 0 else (reciente - mu) / (abs(mu) * 0.1))
    else:
        z = (reciente - mu) / sd
    cambio = ((reciente - mu) / mu * 100) if mu else (100.0 if reciente > 0 else 0.0)
    return {"z": round(z, 2), "cambio_pct": round(cambio, 1), "es_pico": z >= umbral_z and reciente > mu,
            "reciente": round(reciente, 2), "normal": round(mu, 2)}


def crecimiento(valores: list[float], n: int) -> float | None:
    """% de cambio del promedio de los últimos n puntos contra los n anteriores."""
    if n <= 0 or len(valores) < 2 * n:
        return None
    ant = statistics.fmean(valores[-2 * n:-n])
    rec = statistics.fmean(valores[-n:])
    if ant == 0:
        return None if rec == 0 else 100.0
    return round((rec - ant) / ant * 100, 1)


def media_movil(valores: list[float], n: int) -> list[float | None]:
    salida, suma = [], 0.0
    for i, v in enumerate(valores):
        suma += v
        if i >= n:
            suma -= valores[i - n]
        salida.append(suma / n if i >= n - 1 else None)
    return salida


def sumar_periodo(fecha: dt.date, freq: str, k: int = 1) -> dt.date:
    if freq == "D":
        return fecha + dt.timedelta(days=k)
    if freq == "W":
        return fecha + dt.timedelta(weeks=k)
    mes = fecha.month - 1 + k
    return dt.date(fecha.year + mes // 12, mes % 12 + 1, 1)


def pronostico(fechas: list[dt.date], valores: list[float], periodos: int, freq: str) -> dict:
    """Tendencia lineal + (si hay datos diarios suficientes) efecto del día de la semana."""
    import numpy as np

    n = len(valores)
    if n < 3 or periodos <= 0:
        return {"fechas": [], "valores": [], "pendiente": 0.0, "factores_dia": None}
    x = np.arange(n, dtype=float)
    y = np.asarray(valores, dtype=float)
    m, b = np.polyfit(x, y, 1)
    tendencia = m * x + b

    factores = None
    if freq == "D" and n >= 28:
        sumas, cuentas = [0.0] * 7, [0] * 7
        for f, real, t in zip(fechas, y, tendencia):
            if t > 0:
                sumas[f.weekday()] += real / t
                cuentas[f.weekday()] += 1
        if all(cuentas):
            factores = [s / c for s, c in zip(sumas, cuentas)]
            prom = sum(factores) / 7
            factores = [float(f / prom) for f in factores] if prom > 0 else None

    f_fut, v_fut = [], []
    for k in range(1, periodos + 1):
        f = sumar_periodo(fechas[-1], freq, k)
        v = m * (n - 1 + k) + b
        if factores:
            v *= factores[f.weekday()]
        f_fut.append(f)
        v_fut.append(max(0.0, float(v)))
    return {"fechas": f_fut, "valores": v_fut, "pendiente": float(m), "factores_dia": factores}


# ---------------------------------------------------------------------------
# 3) DATOS DE NEGOCIO: importar CSV / Excel (ventas, Google Analytics, etc.)
# ---------------------------------------------------------------------------
FORMATOS_FECHA = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y", "%Y%m%d",
                  "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                  "%m/%d/%Y", "%Y-%m"]


def leer_tabla(ruta: str) -> tuple[list[str], list[list]]:
    """Lee CSV o Excel y regresa (encabezados, filas)."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        hoja = libro.active
        filas = [list(f) for f in hoja.iter_rows(values_only=True)]
        libro.close()
    else:
        texto = None
        for cod in ("utf-8-sig", "latin-1"):
            try:
                with open(ruta, "r", encoding=cod, newline="") as f:
                    texto = f.read()
                break
            except UnicodeDecodeError:
                continue
        lineas = [l for l in texto.splitlines() if l.strip() and not l.startswith("#")]  # GA4 pone comentarios con #
        try:
            dialecto = csv.Sniffer().sniff("\n".join(lineas[:20]), delimiters=",;\t|")
        except csv.Error:
            dialecto = csv.excel
        filas = list(csv.reader(lineas, dialecto))
    filas = [f for f in filas if f and any(c not in (None, "") for c in f)]
    if not filas:
        raise ErrorFuente("El archivo está vacío.")
    encabezados = [str(c).strip() if c is not None else f"Columna {i + 1}" for i, c in enumerate(filas[0])]
    return encabezados, filas[1:]


def parse_fecha(v) -> dt.date | None:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:   # número de serie de Excel
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    s = str(v).strip()
    for fmt in FORMATOS_FECHA:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "")).date()
    except ValueError:
        return None


def parse_numero(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace("MXN", "").replace(" ", "").replace(" ", "")
    if s.endswith("%"):
        s = s[:-1]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # formato 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                                     # formato 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        s = s.replace(",", "") if len(partes[-1]) == 3 else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def adivinar_columnas(encabezados: list[str]) -> dict:
    """Propone columnas de fecha, valor y categoría según sus nombres."""
    bajos = [h.lower() for h in encabezados]

    def buscar(claves):
        for c in claves:
            for i, h in enumerate(bajos):
                if c in h:
                    return i
        return None

    return {
        "fecha": buscar(["fecha", "date", "día", "dia", "day", "periodo", "mes"]),
        "valor": buscar(["total", "venta", "monto", "importe", "ingreso", "revenue", "sesiones", "sessions",
                         "usuarios", "users", "cantidad", "unidades", "views", "vistas", "valor", "value"]),
        "categoria": buscar(["producto", "categor", "articulo", "artículo", "item", "servicio", "canal",
                             "source", "fuente", "page", "página", "pagina", "sucursal"]),
    }


def inicio_periodo(f: dt.date, freq: str) -> dt.date:
    if freq == "W":
        return f - dt.timedelta(days=f.weekday())
    if freq == "M":
        return f.replace(day=1)
    return f


def agrupar(filas: list[list], i_fecha: int, i_valor: int | None, i_cat: int | None, freq: str = "D",
            excluir_incompleto: bool = True) -> dict:
    """Suma por periodo (y por categoría). Si no hay columna de valor, cuenta filas.
    Con excluir_incompleto, se quita la última semana/mes si los datos no la cubren completa
    (si no, parecería que las ventas se desplomaron)."""
    total: dict[dt.date, float] = {}
    por_cat: dict[str, dict[dt.date, float]] = {}
    descartadas = 0
    ultima_fecha = None
    for fila in filas:
        f = parse_fecha(fila[i_fecha]) if i_fecha < len(fila) else None
        if f is None:
            descartadas += 1
            continue
        if i_valor is None:
            v = 1.0
        else:
            v = parse_numero(fila[i_valor]) if i_valor < len(fila) else None
            if v is None:
                descartadas += 1
                continue
        ultima_fecha = f if ultima_fecha is None or f > ultima_fecha else ultima_fecha
        p = inicio_periodo(f, freq)
        total[p] = total.get(p, 0.0) + v
        if i_cat is not None and i_cat < len(fila):
            cat = str(fila[i_cat]).strip() or "(sin categoría)"
            por_cat.setdefault(cat, {})
            por_cat[cat][p] = por_cat[cat].get(p, 0.0) + v
    if not total:
        raise ErrorFuente("No encontré filas con fecha y valor válidos. Revisa las columnas elegidas.")
    incompleto = None
    if excluir_incompleto and freq in ("W", "M") and len(total) > 1:
        ultimo = max(total)
        fin = sumar_periodo(ultimo, freq) - dt.timedelta(days=1)
        if ultima_fecha < fin:
            incompleto = ultimo
            total.pop(ultimo)
            for d in por_cat.values():
                d.pop(ultimo, None)
    # Rellenar periodos vacíos con 0 para que la serie sea continua
    periodos, p = [], min(total)
    while p <= max(total):
        periodos.append(p)
        p = sumar_periodo(p, freq)
    return {
        "periodos": periodos,
        "valores": [total.get(p, 0.0) for p in periodos],
        "por_categoria": {c: [d.get(p, 0.0) for p in periodos] for c, d in por_cat.items()},
        "descartadas": descartadas,
        "periodo_incompleto_excluido": incompleto,
    }


VENTANA_COMPARACION = {"D": 28, "W": 4, "M": 3}   # 4 semanas vs 4 semanas, etc.


def ventana_efectiva(freq: str, n_periodos: int) -> int:
    """Cuántos periodos recientes comparar contra los anteriores, según los datos disponibles."""
    return max(1, min(VENTANA_COMPARACION.get(freq, 4), n_periodos // 2))


def ranking_categorias(por_cat: dict[str, list[float]], n: int) -> list[dict]:
    """Qué productos/categorías están subiendo o bajando."""
    salida = []
    for cat, vals in por_cat.items():
        rec = sum(vals[-n:]) if n else 0
        ant = sum(vals[-2 * n:-n]) if len(vals) >= 2 * n else 0
        if len(vals) < 2 * n:
            cambio = None
        elif ant:
            cambio = round((rec - ant) / ant * 100, 1)
        else:
            cambio = None if rec == 0 else float("inf")
        salida.append({"categoria": cat, "total": sum(vals), "reciente": rec, "anterior": ant, "cambio": cambio})
    salida.sort(key=lambda d: (-(d["cambio"] if d["cambio"] is not None else -math.inf), -d["total"]))
    return salida


# ---------------------------------------------------------------------------
# 4) ALERTAS: lista de vigilancia + historial en SQLite
# ---------------------------------------------------------------------------
class BaseDatos:
    def __init__(self, ruta: str = DB_PATH):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        self.ruta = ruta
        self._lock = threading.Lock()
        with self._con() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS vigilancia(
                           termino TEXT PRIMARY KEY, creado TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS lecturas(
                           id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, termino TEXT, fuente TEXT,
                           valor REAL, normal REAL, z REAL, cambio REAL, es_pico INTEGER, detalle TEXT)""")

    def _con(self):
        return sqlite3.connect(self.ruta, timeout=10)

    def agregar_termino(self, t: str):
        t = t.strip()
        if t:
            with self._lock, self._con() as c:
                c.execute("INSERT OR IGNORE INTO vigilancia VALUES(?, ?)", (t, dt.datetime.now().isoformat()))

    def quitar_termino(self, t: str):
        with self._lock, self._con() as c:
            c.execute("DELETE FROM vigilancia WHERE termino = ?", (t,))

    def terminos(self) -> list[str]:
        with self._con() as c:
            return [r[0] for r in c.execute("SELECT termino FROM vigilancia ORDER BY termino")]

    def guardar_lectura(self, l: dict):
        with self._lock, self._con() as c:
            c.execute("""INSERT INTO lecturas(fecha, termino, fuente, valor, normal, z, cambio, es_pico, detalle)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (l["fecha"].isoformat(timespec="minutes"), l["termino"], l["fuente"], l["valor"],
                       l["normal"], l["z"], l["cambio"], int(l["es_pico"]), l["detalle"]))

    def historial(self, limite: int = 300) -> list[tuple]:
        with self._con() as c:
            return list(c.execute("""SELECT fecha, termino, fuente, valor, normal, z, cambio, es_pico, detalle
                                     FROM lecturas ORDER BY id DESC LIMIT ?""", (limite,)))


def escanear_termino(termino: str, cfg: dict, gt: GoogleTrends, mercado: "Mercado | None" = None) -> list[dict]:
    """Revisa un término en Google Trends (por hora) y en noticias; dice si hay pico.
    Con un mercado activo, el término se analiza dentro de ese mercado."""
    umbral = float(cfg.get("umbral_z", 2.0))
    ahora = dt.datetime.now()
    lecturas = []
    termino_busqueda = mercado.ajustar_termino(termino) if mercado else termino
    consulta_news = mercado.consulta_noticias(termino) if mercado else termino

    # a) Búsquedas en Google, último mes por día. Se descarta el día de hoy (incompleto)
    #    y se comparan los últimos 2 días contra el resto del mes (por hora hay demasiados ceros de noche).
    try:
        _, series = gt.interes_en_el_tiempo([termino_busqueda], "today 1-m")
        vals = series[termino_busqueda][:-1]
        p = detectar_pico(vals, umbral, ventana=2)
        lecturas.append({"fecha": ahora, "termino": termino, "fuente": "Google búsquedas",
                         "valor": p["reciente"], "normal": p["normal"], "z": p["z"], "cambio": p["cambio_pct"],
                         "es_pico": p["es_pico"],
                         "detalle": f"«{termino_busqueda}» últimos 2 días: {p['reciente']:.0f} vs normal {p['normal']:.0f} (0-100)"})
    except ErrorFuente as e:
        lecturas.append({"fecha": ahora, "termino": termino, "fuente": "Google búsquedas", "valor": 0,
                         "normal": 0, "z": 0, "cambio": 0, "es_pico": False, "detalle": f"Error: {e}"})

    # b) Menciones en noticias, últimos 8 días: hoy contra los 7 anteriores
    try:
        items = menciones_noticias(consulta_news, 8, cfg.get("pais", "MX"), cfg.get("idioma", "es-419"))
        _, cuentas = conteo_por_dia(items, 8)
        p = detectar_pico(cuentas, umbral, ventana=1)
        lecturas.append({"fecha": ahora, "termino": termino, "fuente": "Noticias", "valor": p["reciente"],
                         "normal": p["normal"], "z": p["z"], "cambio": p["cambio_pct"], "es_pico": p["es_pico"],
                         "detalle": f"Notas hoy: {int(p['reciente'])} vs {p['normal']} diarias"})
    except ErrorFuente as e:
        lecturas.append({"fecha": ahora, "termino": termino, "fuente": "Noticias", "valor": 0, "normal": 0,
                         "z": 0, "cambio": 0, "es_pico": False, "detalle": f"Error: {e}"})
    return lecturas


def _tupla_version(v: str) -> tuple:
    return tuple(int(x) for x in "".join(c if c.isdigit() or c == "." else "" for c in v).split(".") if x)


def buscar_actualizacion() -> dict | None:
    """Revisa en GitHub si hay una versión más nueva. Regresa {'version', 'url'} o None."""
    owner_repo = REPO_URL.split("github.com/")[-1]
    try:
        r = requests.get(f"https://api.github.com/repos/{owner_repo}/releases/latest",
                         headers={"Accept": "application/vnd.github+json", "User-Agent": APP_NOMBRE}, timeout=10)
        if r.status_code != 200:
            return None
        datos = r.json()
    except (requests.RequestException, ValueError):
        return None
    nueva = datos.get("tag_name", "")
    if nueva and _tupla_version(nueva) > _tupla_version(APP_VERSION):
        return {"version": nueva.lstrip("v"), "url": datos.get("html_url") or f"{REPO_URL}/releases/latest"}
    return None


def exportar_csv(ruta: str, columnas: list[str], filas: list[list]) -> None:
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:   # utf-8-sig: Excel lo abre con acentos
        w = csv.writer(f)
        w.writerow(columnas)
        w.writerows(filas)
