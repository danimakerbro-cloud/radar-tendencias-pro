# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro - fuentes de datos.

Aquí viven solo las consultas a internet: Google Trends (tendencias del día e
interés en el tiempo), Google Noticias, YouTube, Instagram, Pinterest y la
revisión de actualizaciones. La interfaz (app.py) y el servidor (servidor.py)
solo llaman a estas funciones; el análisis está en analisis.py.
"""
from __future__ import annotations

import csv
import datetime as dt
import email.utils
import json
import os
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
APP_VERSION = "2.0.0"   # GitHub Actions lo reemplaza con la versión de la etiqueta (v1.2.3)
REPO_URL = "https://github.com/danimakerbro-cloud/radar-tendencias-pro"
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RadarTendenciasPro")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

CONFIG_DEFECTO = {
    "pais": "MX",                # país que se muestra al abrir el programa
    "idioma": "es-419",          # idioma de Google (es-419 = español de Latinoamérica)
    "zona_horaria_min": 360,     # minutos de diferencia con UTC (CDMX = 360)
    "youtube_api_key": "",       # clave gratuita de YouTube Data API v3
    "pinterest_token": "",       # token gratuito de Pinterest (lectura)
    "instagram_token": "",       # token de la cuenta profesional de Instagram
    "instagram_usuario": "",     # número de esa cuenta
    "pegados": {},               # lo que pegaste de TikTok y Facebook: {red: resumen}
}

# Países que se pueden consultar. MUNDO = todos los de esta lista juntos.
PAISES = {
    "MX": "México", "US": "Estados Unidos", "ES": "España", "AR": "Argentina", "CO": "Colombia",
    "CL": "Chile", "PE": "Perú", "EC": "Ecuador", "GT": "Guatemala", "BR": "Brasil",
    "GB": "Reino Unido", "FR": "Francia", "DE": "Alemania", "IT": "Italia",
    "IN": "India", "JP": "Japón", "KR": "Corea del Sur",
}
MUNDO = "MUNDO"


def nombre_pais(codigo: str) -> str:
    return PAISES.get(codigo, codigo)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def cargar_config() -> dict:
    """Solo se leen las claves que el programa usa hoy; las de versiones anteriores se descartan."""
    cfg = json.loads(json.dumps(CONFIG_DEFECTO))   # copia profunda: no tocar los valores por defecto
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            datos = json.load(f)
        cfg.update({k: v for k, v in datos.items() if k in CONFIG_DEFECTO})
    except (OSError, ValueError):
        pass
    return cfg


def _gl(pais: str) -> str:
    return (pais or "US").upper()

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

class ErrorFuente(Exception):
    """Error entendible para mostrar al usuario."""

def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "es-MX,es;q=0.9,en;q=0.6"})
    return s

def _texto_respuesta(r: requests.Response) -> str:
    """Decodifica sin depender de que el servidor declare bien el charset."""
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        return r.content.decode("latin-1")

def guardar_config(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

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

    def _explorar(self, terminos: list[str], tiempo: str, propiedad: str = "") -> list[dict]:
        """propiedad: "" (búsqueda web), "youtube", "images", "froogle" (Google Shopping) o "news"."""
        req = {
            "comparisonItem": [{"keyword": t, "geo": self.pais, "time": tiempo} for t in terminos],
            "category": 0,
            "property": propiedad,
        }
        datos = self._get("explore", {"hl": self.idioma, "tz": self.tz,
                                      "req": json.dumps(req, separators=(",", ":"))})
        return datos.get("widgets", [])

    def interes_en_el_tiempo(self, terminos: list[str], tiempo: str = "today 3-m", propiedad: str = ""):
        """Regresa (fechas, {termino: [valores 0-100]})."""
        terminos = [t.strip() for t in terminos if t.strip()][:5]
        if not terminos:
            raise ErrorFuente("Escribe al menos un término.")
        widgets = self._explorar(terminos, tiempo, propiedad)
        w = next((w for w in widgets if w.get("id", "").startswith("TIMESERIES")), None)
        if not w:
            raise ErrorFuente("Google Trends no devolvió datos de interés para esos términos.")
        datos = self._get("widgetdata/multiline", {
            "hl": self.idioma, "tz": self.tz,
            "req": json.dumps(w["request"], separators=(",", ":")),
            "token": w["token"],
        })
        return parsear_serie_trends(datos, terminos)

    def relacionadas(self, termino: str, tiempo: str = "today 3-m", propiedad: str = "") -> dict:
        """Búsquedas relacionadas: {'top': [(consulta, valor)], 'subiendo': [(consulta, crecimiento)]}."""
        widgets = self._explorar([termino.strip()], tiempo, propiedad)
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

def hashtag_de(texto: str) -> str:
    """«XV años» -> «xvaños» (los hashtags no llevan espacios ni signos)."""
    return "".join(c for c in (texto or "").lower() if c.isalnum())

def instagram_hashtag(token: str, ig_usuario: str, palabra: str, limite: int = 12, recientes: bool = False) -> dict:
    """Publicaciones con más interacción de un hashtag, con la API oficial de Instagram.
    Necesita una cuenta profesional de Instagram ligada a una página de Facebook y un token de acceso.
    Meta permite consultar hasta 30 hashtags distintos por semana."""
    if not token or not ig_usuario:
        raise ErrorFuente("Falta conectar Instagram en Ajustes (token y número de cuenta).")
    base = "https://graph.facebook.com"
    etiqueta = hashtag_de(palabra)
    try:
        r = requests.get(f"{base}/ig_hashtag_search", params={"user_id": ig_usuario, "q": etiqueta,
                                                               "access_token": token}, timeout=25)
        datos = r.json()
        if "error" in datos:
            raise ErrorFuente(f"Instagram: {datos['error'].get('message', 'error')}")
        if not datos.get("data"):
            return {"hashtag": etiqueta, "publicaciones": []}
        hid = datos["data"][0]["id"]
        r = requests.get(f"{base}/{hid}/{'recent_media' if recientes else 'top_media'}", params={
            "user_id": ig_usuario, "access_token": token, "limit": limite,
            "fields": "caption,like_count,comments_count,permalink,media_type,media_product_type,timestamp"},
            timeout=25)
        datos = r.json()
        if "error" in datos:
            raise ErrorFuente(f"Instagram: {datos['error'].get('message', 'error')}")
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con Instagram: {e}") from None
    pubs = []
    for p in datos.get("data", []):
        formato = {"REELS": "Reel", "STORY": "Historia"}.get(p.get("media_product_type") or "") or \
            {"IMAGE": "Foto", "VIDEO": "Video", "CAROUSEL_ALBUM": "Carrusel"}.get(p.get("media_type") or "", "Publicación")
        pubs.append({"texto": (p.get("caption") or "")[:160], "texto_completo": (p.get("caption") or "")[:1500],
                     "likes": p.get("like_count"), "comentarios": p.get("comments_count"), "url": p.get("permalink"),
                     "tipo": p.get("media_type"), "formato": formato, "fecha": p.get("timestamp")})
    pubs.sort(key=lambda x: -((x["likes"] or 0) + 3 * (x["comentarios"] or 0)))
    return {"hashtag": etiqueta, "publicaciones": pubs}

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
# 2) REDES: YouTube (API oficial, clave gratuita)
# ---------------------------------------------------------------------------
def _error_google_api(r: requests.Response) -> str:
    try:
        return r.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return r.text[:200]

def youtube_tendencia(api_key: str, consulta: str, dias: int = 7, pais: str = "MX",
                      idioma: str = "es", maximo: int = 25,
                      duracion: str = "") -> list[dict]:
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
    if duracion:
        params["videoDuration"] = duracion
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
    return parsear_videos_youtube(r2.json())

def youtube_populares(api_key: str, pais: str = "MX", maximo: int = 50) -> list[dict]:
    """Videos en tendencia de YouTube en el país, ahora mismo (lista oficial «Más populares»)."""
    if not api_key:
        raise ErrorFuente("Falta la clave de YouTube Data API. Agrégala en Ajustes.")
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "snippet,statistics", "chart": "mostPopular", "regionCode": _gl(pais),
                                 "maxResults": min(maximo, 50), "key": api_key}, timeout=30)
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con YouTube: {e}") from None
    if r.status_code != 200:
        raise ErrorFuente(f"YouTube: {_error_google_api(r)}")
    return parsear_videos_youtube(r.json())

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