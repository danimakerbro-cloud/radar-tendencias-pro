# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro - análisis.

Toma las fuentes de motor.py y arma lo que muestra la interfaz:
- lo que es viral ahora, por país o en todo el mundo
- tendencias de inteligencia artificial
- copys y guiones para publicidad, armados a partir de una tendencia
- los hashtags que más se repiten, cruzando YouTube, Instagram y lo que pegues de TikTok y Facebook
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
import time

import motor as m

SEMILLAS_IA = ["ChatGPT", "Gemini IA", "Claude AI", "Midjourney", "Sora IA", "Copilot IA",
               "DeepSeek", "Grok IA", "Perplexity AI", "agentes de IA", "video con IA", "imágenes con IA"]
CONSULTA_IA = "inteligencia artificial"


def _avanza(al_avanzar, pct, paso):
    if al_avanzar:
        al_avanzar(int(pct), paso)


def _paises(codigo: str) -> list[str]:
    """MUNDO se convierte en todos los países de la lista; un código suelto, en uno solo."""
    if codigo == m.MUNDO:
        return list(m.PAISES)
    if codigo in m.PAISES:
        return [codigo]
    raise m.ErrorFuente(f"No conozco el país «{codigo}».")


def _coincide(texto: str, filtro: str) -> bool:
    """Filtro opcional: basta con que una palabra del filtro aparezca en el texto."""
    palabras = [m.normalizar(p) for p in (filtro or "").split()]
    palabras = [p for p in palabras if len(p) >= 3]
    if not palabras:
        return True
    t = m.normalizar(texto)
    return any(p in t for p in palabras)


def _ahora() -> str:
    return dt.datetime.now().isoformat(timespec="minutes")


# ---------------------------------------------------------------------------
# 1) VIRALES: lo que la gente busca y mira ahora mismo
# ---------------------------------------------------------------------------
def virales(cfg: dict, pais: str = "MX", filtro: str = "", al_avanzar=None) -> dict:
    paises = _paises(pais)
    errores, avisos, mapa = {}, [], {}
    for i, p in enumerate(paises):
        _avanza(al_avanzar, 5 + 35 * i / len(paises), f"Tendencias de Google en {m.nombre_pais(p)}")
        try:
            lista = m.tendencias_del_dia(p)
        except m.ErrorFuente as e:
            errores[f"Google {p}"] = str(e)
            continue
        for x in lista[:25]:
            t = mapa.setdefault(m.normalizar(x["tema"]), {
                "tema": x["tema"], "paises": [], "busquedas": x["busquedas"], "busquedas_num": 0,
                "noticia": x["noticia"], "medio": x["medio"], "url": x["url"]})
            if p not in t["paises"]:
                t["paises"].append(p)
            t["busquedas_num"] = max(t["busquedas_num"], x["busquedas_num"])
            if not t["noticia"] and x["noticia"]:
                t.update(noticia=x["noticia"], medio=x["medio"], url=x["url"])
    temas = sorted(mapa.values(), key=lambda t: (-len(t["paises"]), -t["busquedas_num"]))
    temas = [t for t in temas if _coincide(f"{t['tema']} {t['noticia']}", filtro)][:40]

    videos, clave = [], cfg.get("youtube_api_key", "")
    if not clave:
        avisos.append("Agrega tu clave gratuita de YouTube en Ajustes para ver los videos virales.")
    else:
        if len(paises) > 4:
            avisos.append("Los videos virales salen de 4 países (México, Estados Unidos, España y Argentina) "
                          "para no gastar toda la cuota gratuita de YouTube.")
        for i, p in enumerate(paises[:4]):
            _avanza(al_avanzar, 40 + 25 * i / 4, f"Videos virales en {m.nombre_pais(p)}")
            try:
                for v in m.youtube_populares(clave, p, 25):
                    v["pais"] = p
                    videos.append(v)
            except m.ErrorFuente as e:
                errores[f"YouTube {p}"] = str(e)
                break
        vistos, unicos = set(), []
        for v in sorted(videos, key=lambda v: -v["vistas_hora"]):
            if v["url"] not in vistos and _coincide(f"{v['titulo']} {v['canal']}", filtro):
                vistos.add(v["url"])
                unicos.append(v)
        videos = unicos[:40]

    pinterest = []
    if cfg.get("pinterest_token"):
        _avanza(al_avanzar, 70, "Ideas que crecen en Pinterest")
        try:
            pinterest = [x for x in m.pinterest_tendencias(cfg["pinterest_token"], paises[0], "growing", limite=25)
                         if _coincide(x["palabra"], filtro)][:20]
        except m.ErrorFuente as e:
            errores["Pinterest"] = str(e)

    _avanza(al_avanzar, 100, "Listo")
    return {"pais": pais, "paises": paises, "temas": temas, "videos": videos, "pinterest": pinterest,
            "errores": errores, "avisos": avisos, "filtro": filtro, "fecha": _ahora()}


# ---------------------------------------------------------------------------
# 2) POR LUGAR: comparar países (o el mundo) y ver qué se repite entre ellos
# ---------------------------------------------------------------------------
def por_lugar(seleccion: list[str], al_avanzar=None) -> dict:
    paises = []
    for codigo in seleccion:
        for p in _paises(codigo):
            if p not in paises:
                paises.append(p)
    if not paises:
        raise m.ErrorFuente("Elige al menos un país.")
    por_pais, errores, aparece = {}, {}, {}
    for i, p in enumerate(paises):
        _avanza(al_avanzar, 5 + 90 * i / len(paises), f"Tendencias de {m.nombre_pais(p)}")
        try:
            lista = m.tendencias_del_dia(p)
        except m.ErrorFuente as e:
            errores[p] = str(e)
            continue
        por_pais[p] = {"nombre": m.nombre_pais(p),
                       "temas": [{"tema": x["tema"], "busquedas": x["busquedas"], "noticia": x["noticia"],
                                  "url": x["url"]} for x in lista[:10]]}
        for x in lista[:20]:
            fila = aparece.setdefault(m.normalizar(x["tema"]), {"tema": x["tema"], "paises": []})
            if p not in fila["paises"]:
                fila["paises"].append(p)
    repetidos = sorted((f for f in aparece.values() if len(f["paises"]) >= 2),
                       key=lambda f: -len(f["paises"]))[:30]
    _avanza(al_avanzar, 100, "Listo")
    return {"paises": paises, "por_pais": por_pais, "repetidos": repetidos, "errores": errores, "fecha": _ahora()}


# ---------------------------------------------------------------------------
# 3) TENDENCIAS DE IA
# ---------------------------------------------------------------------------
def tendencias_ia(cfg: dict, pais: str = "MX", al_avanzar=None) -> dict:
    if pais not in m.PAISES:
        raise m.ErrorFuente(f"No conozco el país «{pais}».")
    errores = {}
    gt = m.GoogleTrends(pais, cfg.get("idioma", "es-419"), int(cfg.get("zona_horaria_min", 360)))

    def paso_gt(i, n, p):
        _avanza(al_avanzar, 5 + 55 * i / n, f"Midiendo «{p}» en Google")
    try:
        terminos, aviso = interes_por_palabra(gt, SEMILLAS_IA, "today 3-m", paso_gt)
        terminos = [{"palabra": t["palabra"], "veredicto": t["veredicto"], "cambio": t.get("cambio"),
                     "error": t.get("error")} for t in terminos]
        if aviso:
            errores["Google"] = aviso
    except m.ErrorFuente as e:
        terminos, errores["Google"] = [], str(e)

    subiendo = []
    _avanza(al_avanzar, 62, "Búsquedas de IA que están subiendo")
    try:
        rel = gt.relacionadas(CONSULTA_IA, "today 1-m")
        subiendo = [{"busqueda": q, "crecimiento": v} for q, v in rel["subiendo"][:15]]
    except m.ErrorFuente as e:
        errores["Google relacionadas"] = str(e)

    videos = []
    if cfg.get("youtube_api_key"):
        _avanza(al_avanzar, 72, "Videos de IA más vistos")
        try:
            videos = m.youtube_tendencia(cfg["youtube_api_key"], CONSULTA_IA, 7, pais, "es", 20)[:15]
        except m.ErrorFuente as e:
            errores["YouTube"] = str(e)

    _avanza(al_avanzar, 86, "Noticias de IA de hoy")
    noticias = []
    try:
        noticias = m.menciones_noticias(CONSULTA_IA, 3, pais, cfg.get("idioma", "es-419"))[:12]
        noticias = [{"titulo": n["titulo"], "medio": n["medio"], "url": n["url"], "fecha": n["fecha"]} for n in noticias]
    except m.ErrorFuente as e:
        errores["Noticias"] = str(e)

    _avanza(al_avanzar, 100, "Listo")
    return {"pais": pais, "terminos": terminos, "subiendo": subiendo, "videos": videos,
            "noticias": noticias, "errores": errores, "fecha": _ahora()}


# ---------------------------------------------------------------------------
# 4) COPYS E IDEAS PARA PUBLICIDAD (plantillas que llenan la tendencia)
# ---------------------------------------------------------------------------
FORMATOS = {
    "Anuncio de Facebook": "Escríbenos por mensaje y te damos todos los detalles.",
    "Publicación de Instagram": "Guarda esta publicación y compártela con quien le pueda servir.",
    "Reel o TikTok": "Sígueme para no perderte la parte 2.",
}
TONOS = {
    "Cercano": "Esta semana {tema} es de lo más buscado. Te contamos qué está pasando y cómo sumarte antes de que pase de moda.",
    "Profesional": "{tema} está ganando atención. Es el momento de mostrar tu propuesta con claridad a quien ya la está buscando.",
    "Urgente": "{tema} está en su punto más alto y no va a durar para siempre. No te quedes fuera de la conversación.",
}
GANCHOS = [
    "¿Ya viste lo que está pasando con {tema}?",
    "Todo el mundo habla de {tema}. Aquí va lo importante.",
    "Lo que nadie te cuenta sobre {tema}.",
    "Si te interesa {tema}, esto te va a servir.",
    "{tema}: la tendencia que no puedes ignorar esta semana.",
]


def generar_copys(tema: str, formato: str, tono: str, hashtags: list[str] | None = None) -> dict:
    """Arma textos listos para editar. No redacta con IA: llena plantillas con la tendencia elegida."""
    tema = (tema or "").strip()
    if not tema:
        raise m.ErrorFuente("Elige o escribe una tendencia.")
    if formato not in FORMATOS:
        raise m.ErrorFuente("Elige el formato del copy.")
    cuerpo = TONOS.get(tono, TONOS["Cercano"]).replace("{tema}", tema)
    cta = FORMATOS[formato]
    variantes = [{"gancho": g.replace("{tema}", tema), "texto": f"{g.replace('{tema}', tema)} {cuerpo} {cta}"}
                 for g in GANCHOS[:3]]
    etiquetas = [f"#{h.lstrip('#')}" for h in (hashtags or [])][:8]
    # «vals de xv años» -> #ValsDeXvAños (cada palabra con mayúscula, para que se lea bien)
    etiqueta_tema = "#" + "".join(w.capitalize() for w in re.findall(r"\w+", tema))[:40]
    if etiqueta_tema.lower() not in [e.lower() for e in etiquetas] and len(m.hashtag_de(tema)) >= 3:
        etiquetas.insert(0, etiqueta_tema)
    guion = []
    if formato == "Reel o TikTok":
        guion = [f"0 a 3 s: {GANCHOS[0].replace('{tema}', tema)}",
                 f"3 a 10 s: muestra {tema} en acción o da el dato que más sorprende.",
                 f"10 a 15 s: {cta}",
                 "Graba en vertical, pon texto en pantalla y usa un audio que ya esté en tendencia."]
    return {"tema": tema, "formato": formato, "tono": tono, "variantes": variantes, "guion": guion,
            "hashtags": " ".join(etiquetas)}


# ---------------------------------------------------------------------------
# 5) HASHTAGS: los que más se repiten, cruzando las redes disponibles
# ---------------------------------------------------------------------------
def hashtags_tendencia(cfg: dict, pais: str = "MX", temas: list[str] | None = None, al_avanzar=None) -> dict:
    items, errores = [], {}
    pegados = cfg.get("pegados") or {}
    _avanza(al_avanzar, 5, "Hashtags de lo que pegaste")
    for pg in pegados.values():
        for h in pg.get("hashtags", []):
            items += [("#" + h["hashtag"], pg["red"])] * min(h["veces"], 5)

    clave = cfg.get("youtube_api_key", "")
    if clave:
        _avanza(al_avanzar, 30, "Hashtags de YouTube (videos más vistos)")
        try:
            items += [(v["texto"], "YouTube") for v in m.youtube_populares(clave, pais, 50)]
        except m.ErrorFuente as e:
            errores["YouTube"] = str(e)

    token, usuario = cfg.get("instagram_token", ""), cfg.get("instagram_usuario", "")
    if token and usuario and temas:
        for i, t in enumerate(temas[:3]):
            _avanza(al_avanzar, 60 + 25 * i / 3, f"Hashtags de Instagram: #{m.hashtag_de(t)}")
            try:
                for p in m.instagram_hashtag(token, usuario, t, 12)["publicaciones"]:
                    items.append((p.get("texto_completo") or p.get("texto") or "", "Instagram"))
            except m.ErrorFuente as e:
                errores["Instagram"] = str(e)
                break

    por_red = {}
    for red in sorted({r for _, r in items}):
        por_red[red] = hashtags_de_textos([x for x in items if x[1] == red])[:15]
    _avanza(al_avanzar, 100, "Listo")
    return {"mejores": hashtags_de_textos(items)[:25], "por_red": por_red,
            "redes": sorted({r for _, r in items}), "errores": errores, "fecha": _ahora()}


# ---------------------------------------------------------------------------
# Medición por palabra, temas y hashtags (de versiones anteriores)
# ---------------------------------------------------------------------------
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

def _texto_tokens(texto: str, quitar: set, formas: dict | None = None) -> list[str]:
    """Palabras útiles del texto. Se junta el plural con el singular («vaqueros» = «vaquero»);
    en «formas» se anota cómo la escribe la gente, para mostrarla igual."""
    salida = []
    for w in re.findall(r"\w+", texto):
        for t in m.normalizar(w).split():
            if len(t) <= 2 or t in m._VACIAS or t in _RUIDO_TEMAS or t.isdigit():
                continue
            r = m._raiz(t)
            if r in quitar:
                continue
            if formas is not None:   # se guarda como la escribió la gente («años», no «anos»)
                formas.setdefault(r, {}).setdefault(w.lower(), 0)
                formas[r][w.lower()] += 1
            salida.append(r)
    return salida

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

def temas_creativos(items: list[tuple[str, str]], quitar_palabras: list[str], minimo: int = 2) -> list[dict]:
    """Temas (palabras y pares de palabras) que más se repiten en lo creativo de todas las redes.
    items: [(texto, red)]. Se quitan las palabras de la búsqueda."""
    quitar = {m._raiz(t) for p in quitar_palabras for t in m.normalizar(p).split()}
    quitar |= {m._raiz(m.normalizar(m.hashtag_de(p)).strip()) for p in quitar_palabras}
    # Lo que aparece en casi todo es otra forma de nombrar lo buscado (ej. «quinceañera»), no una idea
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

# Palabras que no dicen nada del tema creativo
_SIN_HASHTAG = re.compile(r"#[^\s#]+")   # los hashtags van en su propia lista; en temas solo palabras reales

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

def analizar_pegado(red: str, texto: str) -> dict:
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
        "temas": temas_creativos(items, [], 2)[:15],
    }
