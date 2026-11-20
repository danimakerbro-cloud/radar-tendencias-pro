# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro - análisis del mercado.

Toma las fuentes de motor.py y las convierte en un reporte claro:
- cada palabra del mercado con su PROPIA curva y su veredicto (sube, baja, estable…)
- las búsquedas nuevas separadas por tipo: oportunidades de venta, ideas, generales
  e informativas (estas últimas se ocultan porque no sirven para vender)
- lo que la gente pregunta, temas de hoy, noticias y videos
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
import time

import motor as m

# ---------------------------------------------------------------------------
# Clasificar búsquedas por intención
# ---------------------------------------------------------------------------
TIPOS = {
    "venta": "Oportunidad de venta",
    "ideas": "Idea que sube",
    "general": "General",
    "info": "Informativa",
    "fuera": "De otro país",
}

# Palabras que delatan a alguien que quiere comprar o contratar
_VENTA = {
    "precio", "precios", "costo", "costos", "cotizacion", "cotizar", "paquete", "paquetes", "renta", "rentar",
    "alquiler", "venta", "vender", "comprar", "compra", "contratar", "servicio", "servicios", "cerca",
    "economico", "economica", "economicos", "economicas", "barato", "barata", "baratos", "baratas", "promocion",
    "promociones", "descuento", "descuentos", "oferta", "ofertas", "salon", "salones", "jardin", "jardines",
    "hacienda", "haciendas", "quinta", "quintas", "terraza", "terrazas", "local", "locales", "lugar", "lugares",
    "catering", "banquete", "banquetes", "taquiza", "dj", "fotografo", "fotografos", "fotografia", "video",
    "mobiliario", "invitacion", "invitaciones", "vestido", "vestidos", "traje", "trajes", "pastel", "pasteles",
    "recuerdo", "recuerdos", "regalo", "regalos", "tienda", "tiendas", "domicilio", "menu", "reservar",
    "reservacion", "horario", "horarios", "expo", "lazo", "anillo", "anillos", "boleto", "boletos", "cdmx",
    "df", "mexico", "monterrey", "guadalajara", "puebla", "queretaro", "toluca", "naucalpan", "ecatepec",
    "tlalnepantla", "coyoacan", "iztapalapa", "polanco", "oficina", "oficinas", "amueblada", "amuebladas",
    "coworking", "mayoreo", "proveedor", "proveedores", "agencia", "planner", "organizador", "organizadora",
    "musica", "grupo", "mariachi", "banda", "show", "pista", "cabina", "audio", "iluminacion", "renta",
}
_VENTA_FRASES = ["cuanto cuesta", "cuanto cobra", "donde comprar", "cerca de mi", "a domicilio", "para rentar",
                 "en renta", "en venta", "mas barato"]

# Palabras de inspiración: ideas para contenido y anuncios
_IDEAS = {
    "idea", "ideas", "tendencia", "tendencias", "tematica", "tematicas", "tema", "colores", "color", "estilo",
    "estilos", "sencillo", "sencillos", "sencilla", "sencillas", "elegante", "elegantes", "moderno", "modernos",
    "moderna", "modernas", "bonito", "bonitos", "bonita", "bonitas", "original", "originales", "inspiracion",
    "decoracion", "decorar", "centros", "fondos", "diseno", "disenos", "outfit", "outfits", "2026", "2027",
    "minimalista", "boho", "rustico", "rustica", "vintage", "aesthetic", "temporada", "nuevo", "nuevos", "nueva",
}

# Frases de quien solo quiere información (no va a comprar)
_INFO_FRASES = [
    "mi corazon es tuyo", "corazon es tuyo",
    "que es", "que son", "que significa", "significado", "como se llama", "como se llaman", "cuantos anos son",
    "que numero es", "que siglo es", "que bodas son", "por anos", "frases", "letra", "cancion", "pelicula",
    "peliculas", "serie", "capitulo", "libro", "resumen", "personajes", "obra de teatro", "biblia", "wikipedia",
    "historia de", "origen de", "donde ver", "ver online", "chistes", "memes", "meme", "imagenes", "vector",
    "png", "dibujo", "dibujos", "para colorear", "wallpaper", "fondo de pantalla", "tarea", "ejemplos de",
    "sinonimo", "traduccion", "en ingles", "mapa", "noticias", "murio", "muere", "hijas del", "hijo de",
    "esposa de", "quien es", "edad de", "sangre", "funeral", "cordero", "cana",
    "aniversario de bodas por", "que se regala", "numero romano", "romano",
]
_INFO_PALABRAS = {"sangrienta", "sangriento", "terror", "net", "sa", "wiki", "pdf", "rae", "lyrics", "trailer", "netflix", "disney", "imdb", "subaru",
                  "xview", "xvi", "xvii", "xviii", "xix", "xx", "letras", "roblox", "minecraft", "fortnite", "sims",
                  "juego", "juegos", "anime", "novela", "telenovela", "capitulos", "temporada2", "actor", "actriz",
                  "cantante", "famosos", "famosa", "famoso", "testigos"}

# «boda de julia roberts», «xv años de rubí», «la boda de rachel»: eventos de famosos o ficción
# «boda de yosi y yaren», «la boda de ana y fernando…»: parejas de famosos, influencers o novelas
_PAREJA = re.compile(r"\b(boda|bodas|xv anos) de [a-z]+ y [a-z]+")
_PERSONA = re.compile(r"^(la |las )?(boda|bodas|xv anos) (de|del) "
                      r"(?!(noche|dia|playa|jardin|campo|plata|oro|bronce|diamante|rubi|ensueno|lujo|princesa|"
                      r"blanco|negro|tarde|invierno|verano|primavera|otono|civil|religiosa|destino|mis|tus|"
                      r"nuestros|cuento|hadas)\b)[a-z]+( [a-z]+)?$")

# Lugares que no son México (para un usuario en MX)
_FUERA = {
    "MX": {"espana", "madrid", "barcelona", "valencia", "sevilla", "malaga", "bilbao", "zaragoza", "alicante",
           "murcia", "argentina", "chile", "colombia", "bogota", "medellin", "barranquilla", "cartagena", "peru",
           "arequipa", "cusco", "uruguay", "montevideo", "venezuela", "caracas", "ecuador", "quito", "guayaquil",
           "bolivia", "cochabamba", "paraguay", "asuncion", "guatemala", "honduras", "tegucigalpa", "nicaragua",
           "managua", "panama", "cuba", "habana", "dominicana", "finca", "fincas", "masia", "masias", "cortijo",
           "euros", "usa", "miami", "texas", "california", "rosario", "avellaneda", "berazategui", "neuquen",
           "mendoza", "quilmes", "lanus", "moron", "tucuman", "caba", "conurbano", "gba", "valparaiso", "comuna"},
}


def clasificar(texto: str, pais: str = "MX") -> str:
    """Devuelve 'venta', 'ideas', 'general', 'info' o 'fuera'."""
    n = " " + " ".join(m.normalizar(texto).split()) + " "
    palabras = set(n.split())
    if palabras & _FUERA.get((pais or "MX").upper(), set()):
        return "fuera"
    if palabras & _INFO_PALABRAS or any(f" {f} " in n for f in _INFO_FRASES) or _PERSONA.match(n.strip()) \
            or _PAREJA.search(n):
        return "info"
    if palabras & _VENTA or any(f" {f} " in n for f in _VENTA_FRASES):
        return "venta"
    if palabras & _IDEAS:
        return "ideas"
    return "general"


def separar_por_tipo(items: list[dict], pais: str = "MX") -> dict:
    """Agrupa [{'busqueda': ...}] por tipo, sin repetir."""
    grupos = {k: [] for k in TIPOS}
    vistos = set()
    for it in items:
        clave = (m.normalizar(it["busqueda"]).strip(), it.get("fuente", ""))
        if not clave[0] or clave in vistos:
            continue
        vistos.add(clave)
        it["tipo"] = clasificar(it["busqueda"], pais)
        grupos[it["tipo"]].append(it)
    return grupos


# ---------------------------------------------------------------------------
# Veredicto de una curva
# ---------------------------------------------------------------------------
VEREDICTOS = ["Explotando", "Sube fuerte", "Sube", "Estable", "Baja", "Baja fuerte", "Muy pocas búsquedas"]


def veredicto(serie: list[float], umbral_z: float = 2.0) -> dict:
    """Compara lo reciente con lo anterior en la propia curva de la palabra."""
    vals = [float(v) for v in serie if v is not None]
    if len(vals) > 8:
        vals = vals[:-1]                      # el último punto casi siempre está incompleto
    if len(vals) < 6 or max(vals) < 3 or statistics.fmean(vals) < 1:
        return {"veredicto": "Muy pocas búsquedas", "cambio": None, "pico": False}
    # Curvas casi todo en cero (Google solo registra búsquedas sueltas): un día con algo las haría «explotar»
    if sum(1 for v in vals if v == 0) / len(vals) > 0.3:
        return {"veredicto": "Muy pocas búsquedas", "cambio": None, "pico": False}
    n = len(vals)
    k_rec = max(2, round(n * 0.16))           # ~2 semanas de 90 días
    k_ant = max(3, round(n * 0.32))           # ~4 semanas antes
    rec = statistics.fmean(vals[-k_rec:])
    ant = statistics.fmean(vals[-(k_rec + k_ant):-k_rec]) if n > k_rec + 2 else statistics.fmean(vals[:-k_rec])
    if ant < 2 and rec < 5:
        return {"veredicto": "Muy pocas búsquedas", "cambio": None, "pico": False}
    cambio = ((rec - ant) / ant * 100) if ant > 0 else (100.0 if rec > 0 else 0.0)
    p = m.detectar_pico(vals, umbral_z, ventana=max(1, round(n * 0.05)))
    if p["es_pico"] and cambio >= 30:
        v = "Explotando"
    elif cambio >= 25:
        v = "Sube fuerte"
    elif cambio >= 8:
        v = "Sube"
    elif cambio <= -25:
        v = "Baja fuerte"
    elif cambio <= -8:
        v = "Baja"
    else:
        v = "Estable"
    return {"veredicto": v, "cambio": round(cambio, 1), "pico": bool(p["es_pico"])}


def valor_crecimiento(v) -> float:
    """'+350%' -> 350; 'Aumento puntual' / 'Breakout' / 'Aumento' -> muy alto."""
    n = "".join(c for c in str(v) if c.isdigit())
    return float(n) if n else 5000.0


def texto_crecimiento(v) -> str:
    s = str(v).strip()
    return s if any(c.isdigit() for c in s) else "Explotando"


# ---------------------------------------------------------------------------
# Sugerir palabras para un mercado nuevo
# ---------------------------------------------------------------------------
MODS_SUGERIR = ["", " precio", " precios", " paquetes", " cerca de mi", " ideas", " para", " en cdmx",
                " economicos", " 2026"]


def sugerir_palabras(nombre: str, pais: str = "MX", idioma: str = "es-419") -> dict:
    """Propone palabras para el mercado, separadas por tipo y con las útiles ya marcadas."""
    nombre = " ".join(nombre.split())
    if not nombre:
        raise m.ErrorFuente("Escribe el nombre de tu mercado.")
    ideas = m.ideas_palabras(nombre, pais, idioma, modificadores=MODS_SUGERIR)
    corto = len(m.normalizar(nombre).replace(" ", "")) <= 3
    nombre_sugerido = None
    if corto:
        # «xv» es ambiguo (xview, xvi, subaru xv…): proponemos la forma completa más buscada
        pref = m.normalizar(nombre).strip() + " "
        candidatos = [s for s, _ in ideas if m.normalizar(s).startswith(pref) and clasificar(s, pais) != "info"]
        if candidatos:
            nombre_sugerido = " ".join(candidatos[0].split()[:2])
    base = m.normalizar(nombre_sugerido or nombre).split()
    salida, vistos = [], {m.normalizar(nombre).strip()}
    salida.append({"texto": nombre, "tipo": "general", "marcada": not corto})
    if nombre_sugerido and m.normalizar(nombre_sugerido).strip() not in vistos:
        vistos.add(m.normalizar(nombre_sugerido).strip())
        salida.append({"texto": nombre_sugerido, "tipo": "general", "marcada": True})
    for sug, _ in ideas:
        clave = m.normalizar(sug).strip()
        if clave in vistos:
            continue
        vistos.add(clave)
        tipo = clasificar(sug, pais)
        # Si el nombre era corto, solo cuentan las que contienen la forma completa
        relacionado = all(t in clave.split() for t in base) if corto else True
        # Se marcan frases cortas: las muy largas casi no tienen búsquedas medibles
        marcada = tipo in ("venta", "ideas") and relacionado and len(clave.split()) <= len(base) + 2
        if tipo in ("info", "fuera") or not relacionado:
            tipo = "info" if tipo != "fuera" else "fuera"
        salida.append({"texto": sug, "tipo": tipo, "marcada": marcada})
    orden = {"general": 0, "venta": 1, "ideas": 2, "info": 3, "fuera": 4}
    salida = salida[:2] + sorted(salida[2:], key=lambda x: (orden[x["tipo"]], not x["marcada"],
                                                            len(x["texto"].split())))
    # Máximo 8 marcadas (las que se analizan); el resto queda para que tú decidas
    n = 0
    for x in salida:
        if x["marcada"]:
            n += 1
            x["marcada"] = n <= 8
    return {"nombre": nombre, "nombre_sugerido": nombre_sugerido, "palabras": salida[:45]}


# ---------------------------------------------------------------------------
# Interés de cada palabra, cada una con su propia escala
# ---------------------------------------------------------------------------
def interes_por_palabra(gt: m.GoogleTrends, palabras: list[str], tiempo: str = "today 3-m",
                        al_avanzar=None, umbral_z: float = 2.0, propiedad: str = "") -> tuple[list[dict], str]:
    """Consulta cada palabra por separado (para que una grande no aplaste a las chicas).
    Si Google limita las consultas, cae a consultas de 5 en 5."""
    resultados, aviso = [], ""
    pendientes = list(palabras)
    for i, p in enumerate(palabras):
        if al_avanzar:
            al_avanzar(i, len(palabras), p)
        try:
            fechas, series = gt.interes_en_el_tiempo([p], tiempo, propiedad)
        except m.ErrorFuente as e:
            if "limitando" in str(e) or "429" in str(e):
                aviso = "Google limitó las consultas; algunas palabras se midieron juntas."
                break
            resultados.append({"palabra": p, "error": str(e), "serie": [], "fechas": [],
                               **veredicto([])})
            pendientes.remove(p)
            continue
        serie = series[p]
        fila = {"palabra": p, "serie": serie, "fechas": [f.date().isoformat() for f in fechas],
                "periodo": "3 meses", **veredicto(serie, umbral_z)}
        # Mercados chicos: por día casi todo sale en cero, pero por semana sí se ve la tendencia
        if fila["veredicto"] == "Muy pocas búsquedas" and tiempo == "today 3-m" and max(serie or [0]) > 0:
            try:
                time.sleep(0.8)
                f2, s2 = gt.interes_en_el_tiempo([p], "today 12-m", propiedad)
                v2 = veredicto(s2[p], umbral_z)
                if v2["veredicto"] != "Muy pocas búsquedas":
                    fila.update({"serie": s2[p], "fechas": [f.date().isoformat() for f in f2],
                                 "periodo": "12 meses, por semana", **v2})
            except m.ErrorFuente:
                pass
        resultados.append(fila)
        pendientes.remove(p)
        time.sleep(0.8)
    # Lo que faltó por el límite de Google: en grupos de 5 (cambia la escala, no la dirección)
    for j in range(0, len(pendientes), 5):
        grupo = pendientes[j:j + 5]
        try:
            time.sleep(4)
            fechas, series = gt.interes_en_el_tiempo(grupo, tiempo, propiedad)
            for p in grupo:
                resultados.append({"palabra": p, "serie": series[p], "fechas": [f.date().isoformat() for f in fechas],
                                   **veredicto(series[p], umbral_z)})
        except m.ErrorFuente as e:
            for p in grupo:
                resultados.append({"palabra": p, "error": str(e), "serie": [], "fechas": [], **veredicto([])})
    orden = {v: i for i, v in enumerate(VEREDICTOS)}
    resultados.sort(key=lambda r: (orden.get(r["veredicto"], 9), -(r["cambio"] or 0)))
    return resultados, aviso


def popularidad_relativa(gt: m.GoogleTrends, palabras: list[str], tiempo: str = "today 3-m") -> dict:
    """Qué tan buscada es cada palabra comparada con la más buscada (100)."""
    grupo = palabras[:5]
    if len(grupo) < 2:
        return {}
    try:
        _, series = gt.interes_en_el_tiempo(grupo, tiempo)
    except m.ErrorFuente:
        return {}
    prom = {p: statistics.fmean(v) if v else 0 for p, v in series.items()}
    tope = max(prom.values()) or 1
    return {p: round(v / tope * 100) for p, v in prom.items()}


# ---------------------------------------------------------------------------
# Lo que la gente pregunta (ideal para anuncios y publicaciones)
# ---------------------------------------------------------------------------
PREFIJOS_PREGUNTA = ["como ", "que ", "cuanto cuesta ", "donde ", "cual es el mejor ", "cuando "]


def preguntas_gente(palabras: list[str], mercado: m.Mercado, pais: str = "MX", idioma: str = "es-419",
                    maximo: int = 20) -> list[dict]:
    salida, vistos = [], set()
    for p in palabras[:2]:
        for pref in PREFIJOS_PREGUNTA:
            try:
                ideas = m.ideas_palabras(pref + p, pais, idioma, modificadores=[""])
            except m.ErrorFuente:
                continue
            for s, _ in ideas:
                clave = m.normalizar(s).strip()
                if clave in vistos or mercado.excluido(s):
                    continue
                vistos.add(clave)
                tipo = clasificar(s, pais)
                if tipo in ("fuera",):
                    continue
                if tipo == "info" and not any(clave.startswith(x) for x in ("cuanto cuesta", "donde", "cual es")):
                    continue
                salida.append({"pregunta": s, "tipo": tipo})
    salida.sort(key=lambda x: {"venta": 0, "ideas": 1, "general": 2, "info": 3}.get(x["tipo"], 4))
    return salida[:maximo]


# ---------------------------------------------------------------------------
# Investigación en redes: cada dato dice de qué red salió
# ---------------------------------------------------------------------------
REDES = {
    "google": "Google", "youtube": "YouTube", "imagenes": "Google Imágenes", "shopping": "Google Shopping",
    "pinterest": "Pinterest", "instagram": "Instagram", "tiktok": "TikTok", "facebook": "Facebook",
}
# Google Trends mide la búsqueda dentro de cada producto de Google
_PROPIEDADES = [("youtube", "youtube"), ("imagenes", "images"), ("shopping", "froogle")]


def enlaces_redes(palabra: str, pais: str = "MX") -> dict:
    """Páginas oficiales y públicas de cada red para ver el tema con tus propios ojos."""
    q = m.quote_url(palabra)
    tag = m.quote_url(m.hashtag_de(palabra))
    pais = (pais or "MX").upper()
    return {
        "tiktok": [
            {"texto": f"Hashtags en tendencia en TikTok ({pais})",
             "url": f"https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/es?countryCode={pais}&period=7"},
            {"texto": f"Buscar «{palabra}» en TikTok", "url": f"https://www.tiktok.com/search?q={q}"},
            {"texto": f"Ver #{m.hashtag_de(palabra)} en TikTok", "url": f"https://www.tiktok.com/tag/{tag}"},
            {"texto": "Anuncios que mejor funcionan en TikTok", "url": f"https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/es?region={pais}&period=30"},
        ],
        "facebook": [
            {"texto": f"Anuncios activos sobre «{palabra}» (Biblioteca de anuncios)",
             "url": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={pais}&q={q}&search_type=keyword_unordered"},
            {"texto": f"Buscar «{palabra}» en Facebook", "url": f"https://www.facebook.com/search/top?q={q}"},
        ],
        "instagram": [
            {"texto": f"Ver #{m.hashtag_de(palabra)} en Instagram", "url": f"https://www.instagram.com/explore/tags/{tag}/"},
        ],
        "pinterest": [
            {"texto": "Pinterest Trends (lo que empieza a crecer)", "url": "https://trends.pinterest.com/"},
            {"texto": f"Buscar «{palabra}» en Pinterest", "url": f"https://www.pinterest.com/search/pins/?q={q}"},
        ],
        "youtube": [
            {"texto": f"Videos más nuevos de «{palabra}»", "url": f"https://www.youtube.com/results?search_query={q}&sp=CAI%253D"},
        ],
        "x": [
            {"texto": f"Lo más reciente de «{palabra}» en X (Twitter)", "url": f"https://x.com/search?q={q}&f=live"},
        ],
    }


def investigar_redes(cfg: dict, mercado: m.Mercado, gt: m.GoogleTrends, al_avanzar=None,
                     desde: int = 0, hasta: int = 100, google_suben: list | None = None,
                     palabras: list[str] | None = None) -> dict:
    """Busca el mercado en cada red que permite consultar datos y arma un resumen por red.
    palabras: las del mercado ordenadas de más a menos buscadas (si se conocen)."""
    pais = cfg.get("pais") or "MX"
    idioma = cfg.get("idioma", "es-419")
    umbral = float(cfg.get("umbral_z", 2.0))
    pal = (palabras or mercado.palabras)[:5]
    principal = pal[0] if pal else mercado.nombre
    redes: dict = {}

    def avanza(frac, texto):
        if al_avanzar:
            al_avanzar(int(desde + (hasta - desde) * frac), texto)

    def limpio(q):
        return not mercado.excluido(q) and clasificar(q, pais) not in ("info", "fuera")

    # Interés en YouTube, Google Imágenes y Google Shopping (Google Trends oficial, por producto)
    for i, (clave, prop) in enumerate(_PROPIEDADES):
        avanza(0.05 + 0.15 * i, f"Midiendo tu mercado en {REDES[clave]}")
        red = {"nombre": REDES[clave], "estado": "ok", "suben": []}
        # Cada palabra por separado, para que una muy buscada no aplaste a las demás
        cada, aviso = interes_por_palabra(gt, pal[:3], "today 3-m", None, umbral, prop)
        red["palabras"] = cada
        if aviso:
            red["aviso"] = aviso
        if cada and all(c.get("error") for c in cada):
            red.update(estado="error", error=cada[0]["error"])
        # Lo que está subiendo dentro de esa red
        for p in (pal[:2] if clave == "youtube" else pal[:1]):
            try:
                r = gt.relacionadas(p, "today 1-m", prop)
            except m.ErrorFuente:
                continue
            for q, v in r["subiendo"]:
                if limpio(q):
                    red["suben"].append({"busqueda": q, "crecimiento": texto_crecimiento(v),
                                         "valor": valor_crecimiento(v), "origen": p, "fuente": REDES[clave],
                                         "tipo": clasificar(q, pais)})
            time.sleep(0.8)
        red["suben"] = _sin_repetir(sorted(red["suben"], key=lambda x: -x["valor"]))
        redes[clave] = red

    # Lo que la gente escribe en el buscador de YouTube
    avanza(0.5, "Revisando qué busca la gente en YouTube")
    vistos, sug = set(), []
    for p in pal[:3]:
        for s in m.sugerencias_youtube(p, pais, idioma):
            k = m.normalizar(s).strip()
            if k not in vistos and k != m.normalizar(p).strip() and limpio(s):
                vistos.add(k)
                sug.append({"texto": s, "fuente": "YouTube", "tipo": clasificar(s, pais)})
    redes["youtube"]["sugerencias"] = sug[:20]

    # Pinterest (API oficial, con token)
    avanza(0.6, "Revisando Pinterest")
    if cfg.get("pinterest_token"):
        try:
            pins = m.pinterest_tendencias(cfg["pinterest_token"], pais, "growing", mercado.pinterest)
            propias = [p for p in pins if mercado.coincide(p["palabra"])]
            lista = propias if (propias or not mercado.pinterest) else pins
            redes["pinterest"] = {"nombre": "Pinterest", "estado": "ok",
                                  "suben": [{"busqueda": p["palabra"], "crecimiento": f"+{p['semana']}%" if p["semana"] else "",
                                             "valor": p["semana"] or 0, "fuente": "Pinterest",
                                             "tipo": clasificar(p["palabra"], pais)} for p in lista[:20]]}
        except m.ErrorFuente as e:
            redes["pinterest"] = {"nombre": "Pinterest", "estado": "error", "error": str(e)}
    else:
        redes["pinterest"] = {"nombre": "Pinterest", "estado": "sin_clave"}

    # Instagram (API oficial de Meta, con cuenta profesional conectada)
    avanza(0.75, "Revisando Instagram")
    if cfg.get("instagram_token") and cfg.get("instagram_usuario"):
        pubs, etiquetas, error = [], [], ""
        for p in pal[:2]:
            try:
                r = m.instagram_hashtag(cfg["instagram_token"], cfg["instagram_usuario"], p)
                etiquetas.append(r["hashtag"])
                for x in r["publicaciones"]:
                    pubs.append({**x, "hashtag": r["hashtag"], "fuente": "Instagram"})
            except m.ErrorFuente as e:
                error = str(e)
        pubs = list({p["url"]: p for p in pubs}.values())
        pubs.sort(key=lambda x: -((x["likes"] or 0) + 3 * (x["comentarios"] or 0)))
        redes["instagram"] = {"nombre": "Instagram", "estado": "ok" if pubs or not error else "error",
                              "error": error, "hashtags": etiquetas, "publicaciones": pubs[:12]}
    else:
        redes["instagram"] = {"nombre": "Instagram", "estado": "sin_clave"}

    # TikTok y Facebook no ofrecen datos públicos de tendencias: se dejan sus páginas oficiales a un clic
    redes["tiktok"] = {"nombre": "TikTok", "estado": "enlace"}
    redes["facebook"] = {"nombre": "Facebook", "estado": "enlace"}

    # ¿Qué aparece subiendo en más de una red? (la señal más fuerte)
    avanza(0.95, "Cruzando lo que sube en todas las redes")
    por_tema: dict[str, dict] = {}
    fuentes = [("Google", google_suben or [])] + [(r["nombre"], r.get("suben", [])) for r in redes.values()]
    for nombre, items in fuentes:
        for it in items:
            clave = " ".join(sorted(_tokens_simples(it["busqueda"]) - _tokens_simples(" ".join(pal))))
            if not clave:
                continue
            t = por_tema.setdefault(clave, {"busqueda": it["busqueda"], "fuentes": [], "tipo": it.get("tipo")})
            if nombre not in t["fuentes"]:
                t["fuentes"].append(nombre)
    coinciden = sorted((t for t in por_tema.values() if len(t["fuentes"]) >= 2), key=lambda t: -len(t["fuentes"]))

    return {"principal": principal, "redes": redes, "coinciden": coinciden[:15],
            "enlaces": enlaces_redes(mercado.nombre, pais)}


def _sin_repetir(items: list[dict]) -> list[dict]:
    vistos, salida = set(), []
    for it in items:
        k = m.normalizar(it["busqueda"]).strip()
        if k not in vistos:
            vistos.add(k)
            salida.append(it)
    return salida


def _tokens_simples(texto: str) -> set:
    return {t for t in m.normalizar(texto).split() if len(t) > 2 and t not in m._VACIAS}


# ---------------------------------------------------------------------------
# Ideas creativas: lo creativo que sube la gente (reels, videos, imágenes, hashtags)
# ---------------------------------------------------------------------------
# Cómo busca la gente ideas para su contenido o su evento
_CREATIVO_SUFIJOS = [" ideas", " decoracion", " tendencias", " tematica", " fotos", " videos", " reels", " baile",
                     " entrada", " sorpresa", " colores", " originales", " 2026", " 2027", " diy", " aesthetic"]
_CREATIVO_PREFIJOS = ["ideas para ", "ideas de ", "decoracion de ", "fotos de ", "videos de ", "tendencias en "]
_YT_SUFIJOS = [" ideas", " baile", " decoracion", " tiktok", " tendencias", " entrada", " sorpresa", " shorts"]

# Palabras que no dicen nada del tema creativo
_SIN_HASHTAG = re.compile(r"#[^\s#]+")   # los hashtags van en su propia lista; en temas solo palabras reales
_RUIDO_TEMAS = {
    "mxn", "pesos", "tipo", "publicidad", "anuncio", "anuncios",
    "ideas", "idea", "para", "como", "que", "con", "mas", "video", "videos", "foto", "fotos", "2025", "2026", "2027",
    "tiktok", "reels", "reel", "shorts", "short", "viral", "virales", "fyp", "parati", "foryou", "trend", "trending",
    "tendencias", "tendencia", "nuevo", "nueva", "nuevos", "mejor", "mejores", "los", "las", "una", "uno", "mis", "tus",
    "sus", "este", "esta", "hoy", "dia", "todo", "todos", "aqui", "asi", "muy", "bien", "solo", "ser", "hacer",
    "xyzbca", "fypシ", "paratii", "explore", "explorar", "instagram", "youtube", "pinterest", "facebook", "google",
    "cerca", "precio", "precios", "mexico", "cdmx", "aesthetic", "originales", "original", "parte", "part",
    # textos de las páginas de TikTok y Facebook (botones, avisos)
    "publicidad", "patrocinado", "sponsored", "anuncio", "anuncios", "activo", "identificador", "biblioteca",
    "circulacion", "plataformas", "detalles", "enviar", "mensaje", "cotizar", "whatsapp", "informacion", "registrarte",
    "seguir", "siguiendo", "compartir", "comentarios", "comentar", "gusta", "responder", "iniciar", "sesion", "ver",
    "mostrar", "traducir", "subtitulos", "cargar", "perfil", "empresa", "programa", "terminos", "politicas",
    "privacidad", "condiciones", "cookies", "resultados", "filtros", "ordenar", "busqueda", "buscar", "inicio",
    "versiones", "anunciante", "desde", "hace", "semanas", "semana", "dias", "horas",
}


def _texto_tokens(texto: str, quitar: set, formas: dict | None = None) -> list[str]:
    """Palabras útiles del texto. Se junta el plural con el singular («vaqueros» = «vaquero»);
    en «formas» se anota cómo la escribe la gente, para mostrarla igual."""
    salida = []
    for t in m.normalizar(texto).split():
        if len(t) <= 2 or t in m._VACIAS or t in _RUIDO_TEMAS or t.isdigit():
            continue
        r = m._raiz(t)
        if r in quitar:
            continue
        if formas is not None:
            formas.setdefault(r, {}).setdefault(t, 0)
            formas[r][t] += 1
        salida.append(r)
    return salida


def temas_creativos(items: list[tuple[str, str]], palabras_mercado: list[str], minimo: int = 2) -> list[dict]:
    """Temas (palabras y pares de palabras) que más se repiten en lo creativo de todas las redes.
    items: [(texto, red)]. Se quitan las palabras del propio mercado."""
    quitar = {m._raiz(t) for p in palabras_mercado for t in m.normalizar(p).split()}
    quitar |= {m._raiz(m.normalizar(m.hashtag_de(p)).strip()) for p in palabras_mercado}
    # Lo que aparece en casi todo es otra forma de nombrar al mercado (ej. «quinceañera»), no una idea
    if len(items) >= 10:
        frecuencia: dict[str, int] = {}
        for texto, _ in items:
            for t in set(_texto_tokens(_SIN_HASHTAG.sub(" ", texto), quitar)):
                frecuencia[t] = frecuencia.get(t, 0) + 1
        quitar |= {t for t, n in frecuencia.items() if n > len(items) * 0.4}
    cuenta: dict[str, dict] = {}
    formas: dict[str, dict] = {}
    # Un hashtag cuenta como tema solo si es una palabra que la gente también escribe suelta (#vals sí, #vestidoxv no)
    vocab = set()
    for texto, _ in items:
        vocab.update(_texto_tokens(_SIN_HASHTAG.sub(" ", texto), quitar))
    for texto, red in items:
        toks = _texto_tokens(_SIN_HASHTAG.sub(" ", texto), quitar, formas)
        extra = [t for t in _texto_tokens(" ".join(_SIN_HASHTAG.findall(texto)).replace("#", " "), quitar) if t in vocab]
        vistos = set()
        for i, t in enumerate(toks + extra):
            for clave in (t, f"{t} {toks[i + 1]}" if i + 1 < len(toks) else None):
                if not clave or clave in vistos:
                    continue
                vistos.add(clave)
                c = cuenta.setdefault(clave, {"tema": clave, "veces": 0, "fuentes": []})
                c["veces"] += 1
                if red not in c["fuentes"]:
                    c["fuentes"].append(red)
    temas = [c for c in cuenta.values() if c["veces"] >= minimo]
    # Si un par de palabras aparece casi tanto como su palabra suelta, se queda el par (es más específico)
    pares = {c["tema"]: c for c in temas if " " in c["tema"]}
    for par, c in pares.items():
        for t in par.split():
            suelta = next((x for x in temas if x["tema"] == t), None)
            if suelta and c["veces"] >= suelta["veces"] * 0.6:
                suelta["oculto"] = True
    temas = [c for c in temas if not c.get("oculto")]
    for c in temas:
        c["tema"] = " ".join(max(formas.get(r, {r: 1}).items(), key=lambda kv: kv[1])[0] for r in c["tema"].split())
    temas.sort(key=lambda c: -(c["veces"] * (1 + 0.6 * (len(c["fuentes"]) - 1))))
    return temas[:24]


_HASHTAG = re.compile(r"#([^\s#.,;:!?¡¿()\[\]{}\"'“”]+)")


def hashtags_de_textos(items: list[tuple[str, str]], minimo: int = 1) -> list[dict]:
    cuenta: dict[str, dict] = {}
    for texto, red in items:
        for h in {x.lower() for x in _HASHTAG.findall(texto or "")}:
            if len(h) < 3 or m.normalizar(h).strip() in _RUIDO_TEMAS or h in ("fyp", "fypシ", "parati", "viral"):
                continue
            c = cuenta.setdefault(h, {"hashtag": h, "veces": 0, "fuentes": []})
            c["veces"] += 1
            if red not in c["fuentes"]:
                c["fuentes"].append(red)
    salida = [c for c in cuenta.values() if c["veces"] >= minimo]
    salida.sort(key=lambda c: (-c["veces"], -len(c["fuentes"])))
    return salida[:40]


def analizar_pegado(red: str, texto: str, mercado: m.Mercado) -> dict:
    """Lo que copiaste de una página de TikTok o Facebook: hashtags, anunciantes, precios, ofertas y temas."""
    texto = (texto or "")[:400000]
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    nombre_red = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram"}.get(red, red.title())
    anunciantes: dict[str, int] = {}
    for i, l in enumerate(lineas):
        if l in ("Publicidad", "Patrocinado", "Sponsored") and i > 0 and len(lineas[i - 1]) < 80:
            anunciantes[lineas[i - 1]] = anunciantes.get(lineas[i - 1], 0) + 1
    precios = []
    for p in re.findall(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:MXN|mxn|pesos))?", texto):
        p = " ".join(p.split())
        if p not in precios:
            precios.append(p)
    claves = re.compile(r"(descuento|% ?off|\d+ ?%|promo|gratis|2x1|meses sin intereses|msi|aparta|incluye|paquete|"
                        r"oferta|regalo|cortes[ií]a|solo este mes|cupo|reserva)", re.I)
    ofertas = []
    for l in lineas:
        if claves.search(l) and 12 <= len(l) <= 220 and l not in ofertas:
            ofertas.append(l)
    no_tema = set(anunciantes) | {"Publicidad", "Patrocinado", "Sponsored"}
    items = [(l, nombre_red) for l in lineas if len(l) > 3 and l not in no_tema]
    return {
        "red": nombre_red, "fecha": dt.datetime.now().isoformat(timespec="minutes"), "lineas": len(lineas),
        "hashtags": hashtags_de_textos(items)[:25],
        "anunciantes": sorted(({"nombre": k, "anuncios": v} for k, v in anunciantes.items()),
                              key=lambda x: -x["anuncios"])[:20],
        "precios": precios[:15], "ofertas": ofertas[:15],
        "temas": temas_creativos(items, mercado.palabras + [mercado.nombre], 2)[:15],
    }


def ideas_creativas(cfg: dict, mercado: m.Mercado, gt: m.GoogleTrends, al_avanzar=None,
                    palabras: list[str] | None = None, previo: dict | None = None,
                    desde: int = 0, hasta: int = 100) -> dict:
    """Lo creativo que sube la gente sobre el mercado: búsquedas de ideas (Google y YouTube),
    lo visual que sube (Google Imágenes), Shorts que pegan, Instagram por formato, Pinterest
    y lo que pegaste de TikTok/Facebook. Arriba, los temas y hashtags que se repiten entre redes."""
    pais = cfg.get("pais") or "MX"
    idioma = cfg.get("idioma", "es-419")
    pal = (palabras or mercado.palabras)[:3]
    principal = mercado.nombre if len(mercado.nombre.split()) <= 3 else (pal[0] if pal else mercado.nombre)
    previo = previo or {}
    sal = {"fecha": dt.datetime.now().isoformat(timespec="minutes"), "errores": {}}
    todo: list[tuple[str, str]] = []          # (texto, red) para temas y hashtags

    def avanza(frac, texto):
        if al_avanzar:
            al_avanzar(int(desde + (hasta - desde) * frac), texto)

    def sirve(q):
        return not mercado.excluido(q) and clasificar(q, pais) not in ("info", "fuera")

    # 1) Lo que busca la gente para inspirarse (Google)
    avanza(0.05, "Buscando las ideas que más busca la gente en Google")
    vistos, busq = set(), []
    consultas = [principal + s for s in _CREATIVO_SUFIJOS] + [p + principal for p in _CREATIVO_PREFIJOS]
    for i, q in enumerate(consultas):
        try:
            res = m.ideas_palabras(q, pais, idioma, modificadores=[""])
        except m.ErrorFuente:
            continue
        for s, _ in res[:6]:
            k = m.normalizar(s).strip()
            if k not in vistos and sirve(s):
                vistos.add(k)
                busq.append({"texto": s, "fuente": "Google"})
                todo.append((s, "Google"))
        if i % 5 == 4:
            avanza(0.05 + 0.25 * i / len(consultas), "Buscando las ideas que más busca la gente en Google")
    # 2) Lo que busca la gente en YouTube (videos, bailes, tutoriales)
    avanza(0.32, "Buscando qué videos buscan en YouTube")
    for s in _YT_SUFIJOS:
        for x in m.sugerencias_youtube(principal + s, pais, idioma)[:6]:
            k = m.normalizar(x).strip()
            if k not in vistos and sirve(x):
                vistos.add(k)
                busq.append({"texto": x, "fuente": "YouTube"})
                todo.append((x, "YouTube"))
    sal["busquedas"] = busq[:60]

    # 3) Lo visual que sube (Google Imágenes): se toma del análisis de redes si ya existe
    avanza(0.45, "Revisando lo visual que sube en Google Imágenes")
    img = (((previo.get("redes") or {}).get("redes") or {}).get("imagenes") or {}).get("suben")
    if img is None:
        img = []
        try:
            r = gt.relacionadas(principal, "today 1-m", "images")
            img = [{"busqueda": q, "crecimiento": texto_crecimiento(v), "valor": valor_crecimiento(v),
                    "fuente": "Google Imágenes"} for q, v in r["subiendo"] if sirve(q)]
        except m.ErrorFuente as e:
            sal["errores"]["imagenes"] = str(e)
    sal["imagenes"] = img[:15]
    todo += [(x["busqueda"], "Google Imágenes") for x in img]

    # 4) Videos cortos que pegan (YouTube Shorts, API oficial con clave)
    key = cfg.get("youtube_api_key")
    if key:
        avanza(0.55, "Buscando los Shorts que más pegan")
        try:
            vids = m.youtube_tendencia(key, mercado.consulta_youtube(), 14, pais, idioma.split("-")[0], 50, mercado,
                                       duracion="short")
            sal["shorts"] = [dict(_limpiar_fechas(v), fuente="YouTube") for v in vids[:15]]
            todo += [(v.get("texto", ""), "YouTube") for v in vids]
        except m.ErrorFuente as e:
            sal["shorts"], sal["errores"]["shorts"] = [], str(e)
    else:
        sal["shorts"] = None

    # 5) Instagram por formato (reels, fotos, carruseles), API oficial
    if cfg.get("instagram_token") and cfg.get("instagram_usuario"):
        avanza(0.7, "Revisando qué publican en Instagram")
        pubs = []
        for p in pal[:2]:
            try:
                r = m.instagram_hashtag(cfg["instagram_token"], cfg["instagram_usuario"], p, 25)
                pubs += [dict(x, hashtag=r["hashtag"], fuente="Instagram") for x in r["publicaciones"]]
            except m.ErrorFuente as e:
                sal["errores"]["instagram"] = str(e)
        pubs = list({x["url"]: x for x in pubs}.values())
        formatos: dict[str, dict] = {}
        for x in pubs:
            f = formatos.setdefault(x["formato"], {"formato": x["formato"], "publicaciones": 0, "interaccion": 0})
            f["publicaciones"] += 1
            f["interaccion"] += (x["likes"] or 0) + 3 * (x["comentarios"] or 0)
        for f in formatos.values():
            f["promedio"] = round(f["interaccion"] / f["publicaciones"]) if f["publicaciones"] else 0
        pubs.sort(key=lambda x: -((x["likes"] or 0) + 3 * (x["comentarios"] or 0)))
        sal["instagram"] = {"publicaciones": [{k: v for k, v in x.items() if k != "texto_completo"} for x in pubs[:12]],
                            "formatos": sorted(formatos.values(), key=lambda f: -f["promedio"])}
        todo += [(x.get("texto_completo") or x["texto"], "Instagram") for x in pubs]
    else:
        sal["instagram"] = None

    # 6) Pinterest (del análisis de redes) y lo que pegaste de TikTok/Facebook
    pins = (((previo.get("redes") or {}).get("redes") or {}).get("pinterest") or {}).get("suben") or []
    sal["pinterest"] = pins[:12]
    todo += [(x["busqueda"], "Pinterest") for x in pins]

    avanza(0.92, "Cruzando los temas creativos de todas las redes")
    sal["base"] = [list(x) for x in todo[:1500]]    # lo que salió de internet, para volver a cruzar al pegar
    cruzar_ideas(sal, previo.get("pegados"), mercado)
    avanza(1, "Listo")
    return sal


def cruzar_ideas(ideas: dict, pegados: dict | None, mercado: m.Mercado) -> dict:
    """Junta lo de internet con lo que pegaste de TikTok/Facebook y saca temas y hashtags que se repiten."""
    todo = [tuple(x) for x in ideas.get("base") or []]
    for pg in (pegados or {}).values():
        for t in pg.get("temas", []):
            todo += [(t["tema"], pg["red"])] * min(t["veces"], 5)
        for h in pg.get("hashtags", []):
            todo += [("#" + h["hashtag"], pg["red"])] * min(h["veces"], 5)
    ideas["temas"] = temas_creativos(todo, mercado.palabras + [mercado.nombre])
    ideas["hashtags"] = hashtags_de_textos(todo)
    ideas["redes"] = sorted({red for _, red in todo})
    return ideas


# ---------------------------------------------------------------------------
# En vivo: lo más viral ahora (últimas horas)
# ---------------------------------------------------------------------------
def _limpiar_fechas(d: dict) -> dict:
    return {k: (v.isoformat(timespec="minutes") if isinstance(v, dt.datetime) else v) for k, v in d.items() if k != "texto"}


def en_vivo(cfg: dict, mercado: m.Mercado, gt: m.GoogleTrends, al_avanzar=None,
            palabras: list[str] | None = None) -> dict:
    """Lo que se está moviendo ahora: Google por hora, lo más buscado hoy, videos virales,
    Instagram reciente y noticias de las últimas 24 horas. Cada dato lleva su red."""
    pais = cfg.get("pais") or "MX"
    idioma = cfg.get("idioma", "es-419")
    umbral = float(cfg.get("umbral_z", 2.0))
    pal = (palabras or mercado.palabras)[:4]
    salida = {"mercado": mercado.nombre, "fecha": dt.datetime.now().isoformat(timespec="minutes"), "errores": {}}

    def avanza(pct, texto):
        if al_avanzar:
            al_avanzar(int(pct), texto)

    # 1) Google hora por hora, últimas 24 horas (cada palabra por separado)
    horas = []
    for i, p in enumerate(pal):
        avanza(5 + 45 * i / max(len(pal), 1), f"Midiendo «{p}» en Google, hora por hora")
        try:
            fechas, series = gt.interes_en_el_tiempo([p], "now 1-d")
            serie = series[p]
            base = serie[:-2]                                   # los últimos minutos aún están incompletos
            ceros = sum(1 for x in base if not x) / max(len(base), 1)
            if ceros > 0.4:
                # Casi no se busca por hora: un porcentaje aquí engañaría
                horas.append({"palabra": p, "horas": [f.isoformat(timespec="minutes") for f in fechas],
                              "serie": serie, "pico": False, "cambio": None, "poco": True, "fuente": "Google"})
            else:
                pk = m.detectar_pico(base, umbral, ventana=max(3, round(len(base) / 12)))   # ~2 horas
                horas.append({"palabra": p, "horas": [f.isoformat(timespec="minutes") for f in fechas],
                              "serie": serie, "pico": bool(pk["es_pico"]), "cambio": pk["cambio_pct"],
                              "fuente": "Google"})
        except m.ErrorFuente as e:
            horas.append({"palabra": p, "error": str(e), "serie": [], "horas": [], "pico": False, "cambio": None,
                          "fuente": "Google"})
        time.sleep(0.8)
    horas.sort(key=lambda h: (not h["pico"], -(h["cambio"] or -999)))
    salida["google_horas"] = horas

    # 2) Lo más buscado hoy en el país (Google Tendencias): de tu mercado y general
    avanza(55, "Revisando lo más buscado hoy en Google")
    try:
        hoy = [dict(_limpiar_fechas(t), fuente="Google Tendencias") for t in m.tendencias_del_dia(pais)]
        salida["hoy_mercado"] = [t for t in hoy if mercado.coincide(f"{t['tema']} {t['noticia']}")]
        salida["hoy_general"] = hoy[:15]
    except m.ErrorFuente as e:
        salida["hoy_mercado"], salida["hoy_general"], salida["errores"]["hoy"] = [], [], str(e)

    # 3) Videos que se están volviendo virales (YouTube, con clave)
    key = cfg.get("youtube_api_key")
    if key:
        avanza(65, "Buscando videos que se están volviendo virales")
        try:
            vids = m.youtube_tendencia(key, mercado.consulta_youtube(), 2, pais, idioma.split("-")[0], 50, mercado)
            salida["videos_mercado"] = [dict(_limpiar_fechas(v), fuente="YouTube") for v in vids[:12]]
        except m.ErrorFuente as e:
            salida["videos_mercado"], salida["errores"]["videos_mercado"] = [], str(e)
        try:
            pop = m.youtube_populares(key, pais)
            salida["videos_general"] = [dict(_limpiar_fechas(v), fuente="YouTube") for v in pop[:15]]
            salida["videos_general_mercado"] = [dict(_limpiar_fechas(v), fuente="YouTube") for v in pop
                                                if mercado.coincide(v.get("texto", ""))]
        except m.ErrorFuente as e:
            salida["videos_general"], salida["errores"]["videos_general"] = [], str(e)
    else:
        salida["videos_mercado"] = salida["videos_general"] = None

    # 4) Instagram: lo más reciente de los hashtags de tu mercado (API oficial)
    if cfg.get("instagram_token") and cfg.get("instagram_usuario"):
        avanza(78, "Revisando lo más reciente en Instagram")
        pubs = []
        for p in pal[:2]:
            try:
                r = m.instagram_hashtag(cfg["instagram_token"], cfg["instagram_usuario"], p, 15, recientes=True)
                pubs += [dict(x, hashtag=r["hashtag"], fuente="Instagram") for x in r["publicaciones"]]
            except m.ErrorFuente as e:
                salida["errores"]["instagram"] = str(e)
        salida["instagram"] = sorted({x["url"]: x for x in pubs}.values(),
                                     key=lambda x: -((x["likes"] or 0) + 3 * (x["comentarios"] or 0)))[:12]
    else:
        salida["instagram"] = None

    # 5) Noticias de las últimas 24 horas
    avanza(88, "Buscando noticias de las últimas 24 horas")
    try:
        notas = m.menciones_noticias(mercado.consulta_noticias(), 1, pais, idioma)
        salida["noticias"] = [{"fecha": n["fecha"].isoformat(timespec="minutes"), "titulo": n["titulo"],
                               "medio": n["medio"], "url": n["url"], "fuente": "Google Noticias"} for n in notas[:12]]
    except m.ErrorFuente as e:
        salida["noticias"], salida["errores"]["noticias"] = [], str(e)

    salida["enlaces"] = enlaces_redes(mercado.nombre, pais)
    salida["picos"] = [h["palabra"] for h in horas if h["pico"]]
    avanza(100, "Listo")
    return salida


# ---------------------------------------------------------------------------
# Análisis completo del mercado
# ---------------------------------------------------------------------------
def analizar_mercado(cfg: dict, mercado: m.Mercado, gt: m.GoogleTrends, al_avanzar=None,
                     max_palabras: int = 6) -> dict:
    """Corre todas las fuentes y arma el reporte. al_avanzar(porcentaje, texto)."""
    pais = cfg.get("pais") or "MX"
    idioma = cfg.get("idioma", "es-419")
    umbral = float(cfg.get("umbral_z", 2.0))
    palabras = mercado.palabras[:max_palabras]
    rep = {"mercado": mercado.nombre, "fecha": dt.datetime.now().isoformat(timespec="minutes"), "pais": pais,
           "errores": {}, "avisos": []}

    def avanza(pct, texto):
        if al_avanzar:
            al_avanzar(int(pct), texto)

    # 1) Cada palabra con su propia curva (0-45%)
    try:
        cada, aviso = interes_por_palabra(
            gt, palabras, "today 3-m",
            lambda i, n, p: avanza(3 + 30 * i / max(n, 1), f"Midiendo «{p}» en Google ({i + 1} de {n})"),
            umbral)
        if aviso:
            rep["avisos"].append(aviso)
        avanza(34, "Comparando qué tan buscada es cada palabra")
        pop = popularidad_relativa(gt, [c["palabra"] for c in cada if c["serie"]])
        for c in cada:
            c["popularidad"] = pop.get(c["palabra"])
        rep["palabras"] = cada
    except m.ErrorFuente as e:
        rep["palabras"], rep["errores"]["palabras"] = [], str(e)

    # 2) Búsquedas que despegan y las más buscadas, separadas por tipo (45-70%)
    despegan, populares, fallas = [], [], 0
    principales = palabras[:3]
    for i, p in enumerate(principales):
        avanza(36 + 16 * i / max(len(principales), 1),
               f"Buscando lo que sube alrededor de «{p}» ({i + 1} de {len(principales)})")
        try:
            r = gt.relacionadas(p, "today 1-m")
        except m.ErrorFuente as e:
            fallas += 1
            rep["errores"]["despegan"] = str(e)
            continue
        for q, v in r["subiendo"]:
            if not mercado.excluido(q):
                despegan.append({"busqueda": q, "crecimiento": texto_crecimiento(v), "valor": valor_crecimiento(v),
                                 "origen": p, "fuente": "Google"})
        for q, v in r["top"]:
            if not mercado.excluido(q):
                populares.append({"busqueda": q, "interes": int(v) if str(v).isdigit() else 0, "origen": p,
                                  "fuente": "Google"})
        time.sleep(0.8)
    if fallas < len(principales):
        rep["errores"].pop("despegan", None)
    google_suben = [dict(x, tipo=clasificar(x["busqueda"], pais)) for x in despegan]

    # 3) Investigación en redes (53-80%)
    por_pop = sorted(rep.get("palabras") or [], key=lambda c: -(c.get("popularidad") or 0))
    orden = [c["palabra"] for c in por_pop if c.get("serie")] or palabras
    try:
        rep["redes"] = investigar_redes(cfg, mercado, gt, al_avanzar, 53, 80, google_suben, orden)
        for clave in ("youtube", "imagenes", "shopping", "pinterest"):
            despegan += [dict(x) for x in rep["redes"]["redes"].get(clave, {}).get("suben", [])]
    except m.ErrorFuente as e:
        rep["redes"], rep["errores"]["redes"] = None, str(e)

    despegan.sort(key=lambda x: -x["valor"])
    populares.sort(key=lambda x: -x["interes"])
    rep["despegan"] = separar_por_tipo(despegan, pais)
    rep["populares"] = separar_por_tipo(populares, pais)

    # 3b) Ideas creativas (80-86%)
    try:
        rep["ideas"] = ideas_creativas(cfg, mercado, gt, al_avanzar, orden,
                                       {"redes": rep.get("redes")}, 80, 86)
    except m.ErrorFuente as e:
        rep["ideas"], rep["errores"]["ideas"] = None, str(e)

    # 4) Lo que la gente pregunta (86-88%)
    avanza(86, "Revisando qué pregunta la gente en Google")
    try:
        rep["preguntas"] = [dict(p, fuente="Google") for p in preguntas_gente(palabras, mercado, pais, idioma)]
    except m.ErrorFuente as e:
        rep["preguntas"], rep["errores"]["preguntas"] = [], str(e)

    # 4) Temas de hoy (80-85%)
    avanza(88, "Revisando lo más buscado hoy")
    try:
        hoy = m.tendencias_del_dia(pais)
        rep["hoy_total"] = len(hoy)
        rep["hoy"] = [{**{k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in t.items()},
                       "fuente": "Google Tendencias"} for t in m.filtrar_por_mercado(hoy, mercado)]
    except m.ErrorFuente as e:
        rep["hoy"], rep["hoy_total"], rep["errores"]["hoy"] = [], 0, str(e)

    # 5) Noticias (85-92%)
    avanza(90, "Contando noticias de tu mercado")
    try:
        notas = m.menciones_noticias(mercado.consulta_noticias(), 14, pais, idioma)
        fechas, cuentas = m.conteo_por_dia(notas, 14)
        p = m.detectar_pico(cuentas, umbral, 1)
        rep["noticias"] = {"total": len(notas), "por_dia": [[f.isoformat(), c] for f, c in zip(fechas, cuentas)],
                           "pico": bool(p["es_pico"]), "normal": p["normal"],
                           "items": [{"fecha": n["fecha"].isoformat(timespec="minutes"), "titulo": n["titulo"],
                                      "medio": n["medio"], "url": n["url"], "fuente": "Google Noticias"}
                                     for n in notas[:8]]}
    except m.ErrorFuente as e:
        rep["noticias"], rep["errores"]["noticias"] = None, str(e)

    # 6) Videos (92-99%)
    if cfg.get("youtube_api_key"):
        avanza(95, "Buscando los videos que más rápido crecen")
        try:
            vids = m.youtube_tendencia(cfg["youtube_api_key"], mercado.consulta_youtube(), 7, pais,
                                       idioma.split("-")[0], 50, mercado)
            rep["videos"] = [{**{k: (v.isoformat(timespec="minutes") if isinstance(v, dt.datetime) else v)
                                 for k, v in x.items() if k != "texto"}, "fuente": "YouTube"} for x in vids[:10]]
        except m.ErrorFuente as e:
            rep["videos"], rep["errores"]["videos"] = [], str(e)
    else:
        rep["videos"] = None

    # Resumen en palabras
    pal = rep.get("palabras", [])
    redes_ok = [r["nombre"] for r in ((rep.get("redes") or {}).get("redes") or {}).values() if r.get("estado") == "ok"]
    rep["resumen"] = {
        "redes": ["Google"] + redes_ok,
        "coinciden": len((rep.get("redes") or {}).get("coinciden") or []),
        "temas_creativos": len((rep.get("ideas") or {}).get("temas") or []),
        "suben": sum(1 for p in pal if p["veredicto"] in ("Explotando", "Sube fuerte", "Sube")),
        "bajan": sum(1 for p in pal if p["veredicto"] in ("Baja", "Baja fuerte")),
        "estables": sum(1 for p in pal if p["veredicto"] == "Estable"),
        "explotando": [p["palabra"] for p in pal if p["veredicto"] == "Explotando"],
        "oportunidades": len(rep["despegan"]["venta"]),
        "ideas": len(rep["despegan"]["ideas"]),
    }
    avanza(100, "Listo")
    return rep
