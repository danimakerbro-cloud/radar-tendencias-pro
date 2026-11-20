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
    "que es", "que son", "que significa", "significado", "como se llama", "como se llaman", "cuantos anos son",
    "que numero es", "que siglo es", "que bodas son", "por anos", "frases", "letra", "cancion", "pelicula",
    "peliculas", "serie", "capitulo", "libro", "resumen", "personajes", "obra de teatro", "biblia", "wikipedia",
    "historia de", "origen de", "donde ver", "ver online", "chistes", "memes", "meme", "imagenes", "vector",
    "png", "dibujo", "dibujos", "para colorear", "wallpaper", "fondo de pantalla", "tarea", "ejemplos de",
    "sinonimo", "traduccion", "en ingles", "mapa", "noticias", "murio", "muere", "hijas del", "hijo de",
    "esposa de", "quien es", "edad de", "sangre", "funeral", "cordero", "cana",
    "aniversario de bodas por", "que se regala", "numero romano", "romano",
]
_INFO_PALABRAS = {"net", "sa", "wiki", "pdf", "rae", "lyrics", "trailer", "netflix", "disney", "imdb", "subaru",
                  "xview", "xvi", "xvii", "xviii", "xix", "xx"}

# Lugares que no son México (para un usuario en MX)
_FUERA = {
    "MX": {"espana", "madrid", "barcelona", "valencia", "sevilla", "malaga", "bilbao", "argentina", "buenos",
           "chile", "santiago", "colombia", "bogota", "medellin", "peru", "lima", "uruguay", "montevideo",
           "venezuela", "caracas", "ecuador", "quito", "guayaquil", "bolivia", "paraguay", "finca", "fincas",
           "masia", "masias", "cortijo", "euros", "usa", "miami", "texas", "california", "rd", "dominicana",
           "guatemala", "honduras", "salvador", "nicaragua", "costa", "panama", "cuba", "puerto"},
}


def clasificar(texto: str, pais: str = "MX") -> str:
    """Devuelve 'venta', 'ideas', 'general', 'info' o 'fuera'."""
    n = " " + " ".join(m.normalizar(texto).split()) + " "
    palabras = set(n.split())
    if palabras & _FUERA.get((pais or "MX").upper(), set()):
        return "fuera"
    if palabras & _INFO_PALABRAS or any(f" {f} " in n for f in _INFO_FRASES):
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
        clave = m.normalizar(it["busqueda"]).strip()
        if not clave or clave in vistos:
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
    n = len(vals)
    k_rec = max(2, round(n * 0.16))           # ~2 semanas de 90 días
    k_ant = max(3, round(n * 0.32))           # ~4 semanas antes
    rec = statistics.fmean(vals[-k_rec:])
    ant = statistics.fmean(vals[-(k_rec + k_ant):-k_rec]) if n > k_rec + 2 else statistics.fmean(vals[:-k_rec])
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
        marcada = tipo in ("venta", "ideas") and relacionado and len(clave.split()) <= 6
        if tipo in ("info", "fuera") or not relacionado:
            tipo = "info" if tipo != "fuera" else "fuera"
        salida.append({"texto": sug, "tipo": tipo, "marcada": marcada})
    orden = {"general": 0, "venta": 1, "ideas": 2, "info": 3, "fuera": 4}
    salida = salida[:2] + sorted(salida[2:], key=lambda x: (orden[x["tipo"]], not x["marcada"]))
    return {"nombre": nombre, "nombre_sugerido": nombre_sugerido, "palabras": salida[:45]}


# ---------------------------------------------------------------------------
# Interés de cada palabra, cada una con su propia escala
# ---------------------------------------------------------------------------
def interes_por_palabra(gt: m.GoogleTrends, palabras: list[str], tiempo: str = "today 3-m",
                        al_avanzar=None, umbral_z: float = 2.0) -> tuple[list[dict], str]:
    """Consulta cada palabra por separado (para que una grande no aplaste a las chicas).
    Si Google limita las consultas, cae a consultas de 5 en 5."""
    resultados, aviso = [], ""
    pendientes = list(palabras)
    for i, p in enumerate(palabras):
        if al_avanzar:
            al_avanzar(i, len(palabras), p)
        try:
            fechas, series = gt.interes_en_el_tiempo([p], tiempo)
        except m.ErrorFuente as e:
            if "limitando" in str(e) or "429" in str(e):
                aviso = "Google limitó las consultas; algunas palabras se midieron juntas."
                break
            resultados.append({"palabra": p, "error": str(e), "serie": [], "fechas": [],
                               **veredicto([])})
            pendientes.remove(p)
            continue
        serie = series[p]
        resultados.append({"palabra": p, "serie": serie, "fechas": [f.date().isoformat() for f in fechas],
                           **veredicto(serie, umbral_z)})
        pendientes.remove(p)
        time.sleep(0.8)
    # Lo que faltó por el límite de Google: en grupos de 5 (cambia la escala, no la dirección)
    for j in range(0, len(pendientes), 5):
        grupo = pendientes[j:j + 5]
        try:
            time.sleep(4)
            fechas, series = gt.interes_en_el_tiempo(grupo, tiempo)
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
# Análisis completo del mercado
# ---------------------------------------------------------------------------
def analizar_mercado(cfg: dict, mercado: m.Mercado, gt: m.GoogleTrends, al_avanzar=None,
                     max_palabras: int = 8) -> dict:
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
            lambda i, n, p: avanza(3 + 40 * i / max(n, 1), f"Midiendo «{p}» en Google ({i + 1} de {n})"),
            umbral)
        if aviso:
            rep["avisos"].append(aviso)
        avanza(44, "Comparando qué tan buscada es cada palabra")
        pop = popularidad_relativa(gt, [c["palabra"] for c in cada if c["serie"]])
        for c in cada:
            c["popularidad"] = pop.get(c["palabra"])
        rep["palabras"] = cada
    except m.ErrorFuente as e:
        rep["palabras"], rep["errores"]["palabras"] = [], str(e)

    # 2) Búsquedas que despegan y las más buscadas, separadas por tipo (45-70%)
    despegan, populares, fallas = [], [], 0
    principales = palabras[:4]
    for i, p in enumerate(principales):
        avanza(46 + 24 * i / max(len(principales), 1),
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
                                 "origen": p})
        for q, v in r["top"]:
            if not mercado.excluido(q):
                populares.append({"busqueda": q, "interes": int(v) if str(v).isdigit() else 0, "origen": p})
        time.sleep(0.8)
    if fallas < len(principales):
        rep["errores"].pop("despegan", None)
    despegan.sort(key=lambda x: -x["valor"])
    populares.sort(key=lambda x: -x["interes"])
    rep["despegan"] = separar_por_tipo(despegan, pais)
    rep["populares"] = separar_por_tipo(populares, pais)

    # 3) Lo que la gente pregunta (70-80%)
    avanza(71, "Revisando qué pregunta la gente en Google")
    try:
        rep["preguntas"] = preguntas_gente(palabras, mercado, pais, idioma)
    except m.ErrorFuente as e:
        rep["preguntas"], rep["errores"]["preguntas"] = [], str(e)

    # 4) Temas de hoy (80-85%)
    avanza(81, "Revisando lo más buscado hoy")
    try:
        hoy = m.tendencias_del_dia(pais)
        rep["hoy_total"] = len(hoy)
        rep["hoy"] = [{k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in t.items()}
                      for t in m.filtrar_por_mercado(hoy, mercado)]
    except m.ErrorFuente as e:
        rep["hoy"], rep["hoy_total"], rep["errores"]["hoy"] = [], 0, str(e)

    # 5) Noticias (85-92%)
    avanza(86, "Contando noticias de tu mercado")
    try:
        notas = m.menciones_noticias(mercado.consulta_noticias(), 14, pais, idioma)
        fechas, cuentas = m.conteo_por_dia(notas, 14)
        p = m.detectar_pico(cuentas, umbral, 1)
        rep["noticias"] = {"total": len(notas), "por_dia": [[f.isoformat(), c] for f, c in zip(fechas, cuentas)],
                           "pico": bool(p["es_pico"]), "normal": p["normal"],
                           "items": [{"fecha": n["fecha"].isoformat(timespec="minutes"), "titulo": n["titulo"],
                                      "medio": n["medio"], "url": n["url"]} for n in notas[:8]]}
    except m.ErrorFuente as e:
        rep["noticias"], rep["errores"]["noticias"] = None, str(e)

    # 6) Videos (92-99%)
    if cfg.get("youtube_api_key"):
        avanza(93, "Buscando los videos que más rápido crecen")
        try:
            vids = m.youtube_tendencia(cfg["youtube_api_key"], mercado.consulta_youtube(), 7, pais,
                                       idioma.split("-")[0], 50, mercado)
            rep["videos"] = [{k: (v.isoformat(timespec="minutes") if isinstance(v, dt.datetime) else v)
                              for k, v in x.items() if k != "texto"} for x in vids[:10]]
        except m.ErrorFuente as e:
            rep["videos"], rep["errores"]["videos"] = [], str(e)
    else:
        rep["videos"] = None

    # Resumen en palabras
    pal = rep.get("palabras", [])
    rep["resumen"] = {
        "suben": sum(1 for p in pal if p["veredicto"] in ("Explotando", "Sube fuerte", "Sube")),
        "bajan": sum(1 for p in pal if p["veredicto"] in ("Baja", "Baja fuerte")),
        "estables": sum(1 for p in pal if p["veredicto"] == "Estable"),
        "explotando": [p["palabra"] for p in pal if p["veredicto"] == "Explotando"],
        "oportunidades": len(rep["despegan"]["venta"]),
        "ideas": len(rep["despegan"]["ideas"]),
    }
    avanza(100, "Listo")
    return rep
