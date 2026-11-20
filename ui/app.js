/* Radar de Tendencias Pro: interfaz */
"use strict";

// ------------------------------------------------------------ utilidades
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const nf = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
const fnum = (v) => (v == null || isNaN(v) ? "—" : nf.format(v));
const fpct = (v) => (v == null ? "—" : v === "nuevo" ? "Nuevo" : (v > 0 ? "+" : "") + Math.round(v) + "%");
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function fechaBonita(iso) {
  if (!iso) return "";
  const f = new Date(iso);
  const hoy = new Date();
  const hora = f.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  if (f.toDateString() === hoy.toDateString()) return `hoy a las ${hora}`;
  const ayer = new Date(hoy); ayer.setDate(hoy.getDate() - 1);
  if (f.toDateString() === ayer.toDateString()) return `ayer a las ${hora}`;
  return `${f.getDate()} de ${MESES[f.getMonth()]} a las ${hora}`;
}
const fechaCorta = (iso) => { const f = new Date(iso.length <= 10 ? iso + "T12:00" : iso); return `${f.getDate()} ${MESES[f.getMonth()]}`; };

function errorAmable(msg) {
  const t = String(msg || "");
  if (/limitando|429/.test(t)) return "Google pidió una pausa porque hubo muchas consultas seguidas. Espera unos 5 minutos y vuelve a intentar.";
  if (/conectar|Connection|timed out|Max retries/i.test(t)) return "No hubo respuesta de internet. Revisa tu conexión y vuelve a intentar.";
  return t;
}

// ------------------------------------------------------------ comunicación con el programa
async function api(nombre, datos = {}) {
  const r = await fetch("/api/" + nombre, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || "Algo salió mal");
  return j;
}

async function esperar(id, alAvanzar) {
  for (;;) {
    await dormir(700);
    const t = await api("trabajo", { id });
    if (alAvanzar) alAvanzar(t);
    if (t.estado === "listo") return t.resultado;
    if (t.estado === "error") throw new Error(t.error);
  }
}

function barra(pct) {
  const b = $("#barraCarga");
  if (pct == null) { b.hidden = true; return; }
  b.hidden = false;
  $("span", b).style.width = Math.max(3, pct) + "%";
}

function aviso(msg, tipo = "", titulo = "") {
  const t = document.createElement("div");
  t.className = "toast " + tipo;
  t.innerHTML = (titulo ? `<b>${esc(titulo)}</b>` : "") + esc(msg);
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), tipo === "pico" ? 15000 : 6000);
}

async function copiar(texto) {
  try { await navigator.clipboard.writeText(texto); aviso("Copiado: " + texto); } catch { aviso("No se pudo copiar"); }
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-url]");
  if (a) { e.preventDefault(); api("abrir", { url: a.dataset.url }); }
});

// ------------------------------------------------------------ estado general
const E = { estado: null, vista: "inicio", analisis: null, analizando: null, editor: null, comparar: null, redes: null, ventas: null };

async function cargarEstado() {
  E.estado = await api("estado");
  const sel = $("#selMercado");
  sel.innerHTML = E.estado.mercados.length
    ? E.estado.mercados.map((m) => `<option ${m.nombre === E.estado.activo ? "selected" : ""}>${esc(m.nombre)}</option>`).join("")
    : `<option value="">Todavía no tienes mercado</option>`;
  $("#versionTxt").textContent = `Versión ${E.estado.version}`;
}

$("#selMercado").addEventListener("change", async (e) => {
  if (!e.target.value) return ir("mercado");
  await api("mercado/activar", { nombre: e.target.value });
  E.analisis = null; E.comparar = null; E.redes = null; E.vivo = null;
  await cargarEstado();
  render();
});
$("#btnAnalizarSup").addEventListener("click", () => analizar());
$$("#menu button").forEach((b) => b.addEventListener("click", () => ir(b.dataset.vista)));

function ir(vista) {
  E.vista = vista;
  $$("#menu button").forEach((b) => b.classList.toggle("activo", b.dataset.vista === vista));
  render();
  $("main").scrollTo?.(0, 0); window.scrollTo(0, 0);
}

function render() {
  const c = $("#contenido");
  const vistas = { inicio: vistaInicio, envivo: vistaEnVivo, mercado: vistaMercado, redsociales: vistaRedesSociales, comparar: vistaComparar, redes: vistaRedes, ventas: vistaVentas, alertas: vistaAlertas, ajustes: vistaAjustes };
  (vistas[E.vista] || vistaInicio)(c);
}

// ------------------------------------------------------------ gráficas (SVG propias)
const NS = "http://www.w3.org/2000/svg";
const COLORES = ["#2563EB", "#DC2626", "#16A34A", "#D97706", "#7C3AED"];

function sparkline(valores, color = "#2563EB", w = 170, h = 38) {
  const v = (valores || []).filter((x) => x != null);
  if (v.length < 2) return `<svg width="${w}" height="${h}"></svg>`;
  const max = Math.max(...v, 1), min = Math.min(...v);
  const pts = v.map((y, i) => [(i / (v.length - 1)) * (w - 6) + 3, h - 4 - ((y - min) / (max - min || 1)) * (h - 8)]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const u = pts[pts.length - 1];
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${u[0]}" cy="${u[1]}" r="3" fill="${color}"/></svg>`;
}

function graficaLinea(cont, { etiquetas, series, alto = 260, fmtY = fnum, formatoX = fechaCorta, barras = false }) {
  cont.classList.add("grafica");
  const W = Math.max(cont.clientWidth || 700, 320), H = alto, I = 46, D = 14, A = 14, B = 30;
  const todos = series.flatMap((s) => s.valores.filter((v) => v != null));
  const max = Math.max(...todos, 1) * 1.08;
  const n = etiquetas.length;
  const x = (i) => I + (n <= 1 ? 0 : (i / (n - 1)) * (W - I - D));
  const y = (v) => A + (1 - v / max) * (H - A - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  for (let k = 0; k <= 4; k++) {
    const v = (max / 4) * k, yy = y(v);
    s += `<line x1="${I}" x2="${W - D}" y1="${yy}" y2="${yy}" stroke="#EEF1F6"/><text x="${I - 8}" y="${yy + 4}" text-anchor="end" font-size="11" fill="#8A97AE">${esc(fmtY(v))}</text>`;
  }
  const paso = Math.max(1, Math.ceil(n / 7));
  for (let i = 0; i < n; i += paso) s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="#8A97AE">${esc(formatoX(etiquetas[i]))}</text>`;
  if (barras) {
    const bw = Math.max(4, ((W - I - D) / n) * 0.62);
    series[0].valores.forEach((v, i) => {
      const col = (series[0].colores && series[0].colores[i]) || series[0].color;
      s += `<rect x="${x(i) - bw / 2}" y="${y(v || 0)}" width="${bw}" height="${H - B - y(v || 0)}" rx="3" fill="${col}"/>`;
    });
  } else {
    series.forEach((se) => {
      let d = "", abierto = false;
      se.valores.forEach((v, i) => { if (v == null) { abierto = false; return; } d += (abierto ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; abierto = true; });
      if (se.area && d) { let u = se.valores.length - 1; while (u > 0 && se.valores[u] == null) u--; s += `<path d="${d} L${x(u)} ${H - B} L${x(se.valores.findIndex((v) => v != null))} ${H - B} Z" fill="${se.color}" opacity=".09"/>`; }
      s += `<path d="${d}" fill="none" stroke="${se.color}" stroke-width="${se.grosor || 2.4}" ${se.punteada ? 'stroke-dasharray="5 5"' : ""} stroke-linejoin="round" stroke-linecap="round"/>`;
    });
  }
  s += `<line class="guia" x1="0" x2="0" y1="${A}" y2="${H - B}" stroke="#0F1E3D" stroke-width="1" opacity="0"/><rect class="captura" x="${I}" y="0" width="${W - I - D}" height="${H}" fill="transparent"/></svg><div class="tip" hidden></div>`;
  cont.innerHTML = s;
  const svg = $("svg", cont), tip = $(".tip", cont), guia = $(".guia", cont);
  $(".captura", cont).addEventListener("mousemove", (ev) => {
    const r = svg.getBoundingClientRect(), esc_ = W / r.width;
    const px = (ev.clientX - r.left) * esc_;
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - I) / (W - I - D)) * (n - 1))));
    guia.setAttribute("x1", x(i)); guia.setAttribute("x2", x(i)); guia.setAttribute("opacity", ".25");
    const filas = series.filter((se) => se.valores[i] != null).map((se) => `<span style="color:${se.color === "#0F1E3D" ? "#fff" : se.color}">●</span> ${esc(se.nombre)}: <b>${esc(fmtY(se.valores[i]))}</b>`);
    if (!filas.length) { tip.hidden = true; return; }
    tip.innerHTML = `${esc(formatoX(etiquetas[i]))}<br>${filas.join("<br>")}`;
    tip.hidden = false; tip.style.left = x(i) / esc_ + "px"; tip.style.top = A / esc_ + "px";
  });
  $(".captura", cont).addEventListener("mouseleave", () => { tip.hidden = true; guia.setAttribute("opacity", "0"); });
}

// ------------------------------------------------------------ piezas reutilizables
const VER = {
  "Explotando": ["explotando", "🔥 Explotando"], "Sube fuerte": ["sube", "↑ Sube fuerte"], "Sube": ["sube", "↗ Sube"],
  "Estable": ["estable", "→ Estable"], "Baja": ["baja", "↘ Baja"], "Baja fuerte": ["baja", "↓ Baja fuerte"],
  "Muy pocas búsquedas": ["estable", "Muy pocas búsquedas"],
};
const chipVer = (v) => { const [c, t] = VER[v] || ["estable", v]; return `<span class="chip ${c}">${esc(t)}</span>`; };
const TIPOS = { venta: "💰 Oportunidades de venta", ideas: "💡 Ideas que suben", general: "Generales", ocultas: "Ocultas" };
const AYUDA_TIPOS = {
  venta: "Gente buscando precios, paquetes, lugares o productos: listos para comprar.",
  ideas: "Temas de inspiración que están creciendo: buenos para publicaciones y anuncios.",
  general: "Búsquedas relacionadas sin una intención clara de compra.",
  ocultas: "Búsquedas informativas o de otros países (por ejemplo «qué significa», «España»). No suelen servir para vender.",
};

function cargando(c, texto) { c.innerHTML = `<div class="tarjeta vacio"><p>${esc(texto)}</p></div>`; }

function progresoHTML(titulo, t, pasos) {
  const pct = t ? t.pct : 0;
  const lis = pasos.map((p, i) => {
    const desde = i ? pasos[i - 1].hasta : 0;
    const est = pct >= p.hasta ? "hecho" : pct >= desde ? "ahora" : "";
    return `<li class="${est}"><span class="marca">${est === "hecho" ? "✓" : ""}</span>${esc(p.txt)}</li>`;
  }).join("");
  return `<div class="tarjeta progreso"><h1>${esc(titulo)}</h1><p class="sub">${esc(t ? t.paso : "Empezando…")}</p>
    <div class="riel-grande"><span style="width:${Math.max(3, pct)}%"></span></div>
    <div class="pct"><span>${t && t.segundos > 1 ? `Llevamos ${t.segundos} segundos` : "Esto tarda de 1 a 3 minutos"}</span><b>${pct}%</b></div>
    <ul class="pasos">${lis}</ul>
    <p class="chico" style="margin-top:18px">Puedes revisar otras secciones mientras tanto; te aviso cuando termine.</p></div>`;
}

// ------------------------------------------------------------ análisis del mercado
const PASOS_ANALISIS = [
  { hasta: 34, txt: "Medir cada palabra en Google, una por una" },
  { hasta: 53, txt: "Encontrar las búsquedas que están despegando en Google" },
  { hasta: 80, txt: "Investigar en redes: YouTube, Imágenes, Shopping, Pinterest, Instagram" },
  { hasta: 86, txt: "Ver qué pregunta la gente" },
  { hasta: 89, txt: "Revisar lo más buscado hoy" },
  { hasta: 94, txt: "Contar las noticias de tu mercado" },
  { hasta: 100, txt: "Buscar videos que están pegando" },
];

// De qué red salió cada dato
const FUENTES = {
  "Google": "google", "Google Tendencias": "google", "YouTube": "youtube", "Google Imágenes": "imagenes",
  "Google Shopping": "shopping", "Pinterest": "pinterest", "Instagram": "instagram", "TikTok": "tiktok",
  "Facebook": "facebook", "X": "x", "Google Noticias": "noticias",
};
const fuente = (f) => (f ? `<span class="fuente f-${FUENTES[f] || "google"}" title="Este dato salió de ${esc(f)}">${esc(f)}</span>` : "");

async function analizar() {
  if (!E.estado.activo) { aviso("Primero crea tu mercado."); return ir("mercado"); }
  if (E.analizando) return ir("inicio");
  const boton = $("#btnAnalizarSup");
  try {
    const { trabajo } = await api("analizar");
    E.analizando = { id: trabajo, pct: 0, paso: "Empezando…" };
    boton.disabled = true;
    ir("inicio");
    const rep = await esperar(trabajo, (t) => {
      E.analizando = t; barra(t.pct); boton.textContent = `Analizando… ${t.pct}%`;
      if (E.vista === "inicio" && $("#contenido .progreso")) $("#contenido").innerHTML = progresoHTML(`Analizando «${E.estado.activo}»`, t, PASOS_ANALISIS);
    });
    E.analisis = rep;
    aviso("Ya puedes ver qué está subiendo en tu mercado.", "", "Análisis listo");
  } catch (err) {
    aviso(errorAmable(err.message), "error", "No se pudo terminar el análisis");
  } finally {
    E.analizando = null; barra(null); boton.disabled = false; boton.textContent = "Analizar mi mercado";
    if (E.vista === "inicio") render();
  }
}

// ------------------------------------------------------------ INICIO
async function vistaInicio(c) {
  if (!E.estado.activo) {
    c.innerHTML = `<div class="tarjeta vacio"><h1>Bienvenido a tu radar de tendencias</h1>
      <p>Dime en qué mercado estás (por ejemplo «salones de fiestas», «oficinas en renta» o «cafetería») y te digo qué está subiendo, qué está bajando y qué busca la gente para comprar.</p>
      <button class="btn primario grande" id="bCrear">Crear mi mercado</button></div>`;
    $("#bCrear").onclick = () => { E.editor = nuevoEditor(); ir("mercado"); };
    return;
  }
  if (E.analizando) { c.innerHTML = progresoHTML(`Analizando «${E.estado.activo}»`, E.analizando, PASOS_ANALISIS); return; }
  if (!E.analisis) {
    cargando(c, "Cargando tu último análisis…");
    E.analisis = (await api("analisis/ultimo")).analisis;
    if (E.vista !== "inicio") return;
  }
  const mer = E.estado.mercados.find((m) => m.nombre === E.estado.activo);
  if (!E.analisis) {
    c.innerHTML = `<div class="tarjeta vacio"><h1>Todo listo para analizar «${esc(E.estado.activo)}»</h1>
      <p>Voy a revisar ${Math.min(8, mer.palabras.length)} palabras de tu mercado en Google, las búsquedas que están despegando, lo que pregunta la gente, los temas de hoy y las noticias. Tarda de 1 a 3 minutos.</p>
      <button class="btn primario grande" id="bAn">Analizar mi mercado</button></div>`;
    $("#bAn").onclick = analizar;
    return;
  }
  reporte(c, E.analisis);
}

function reporte(c, r) {
  const R = r.resumen || {};
  const errs = r.errores || {};
  const errorDe = (k) => (errs[k] ? `<div class="error-sec">${esc(errorAmable(errs[k]))}</div>` : "");
  c.innerHTML = `
    <div class="encabezado"><div><h1>${esc(r.mercado)}</h1><p class="sub" style="margin:0">Analizado ${esc(fechaBonita(r.fecha))}</p>
      <div class="fuentes-revisadas"><span class="chico">Revisé:</span>${(R.redes || ["Google"]).map(fuente).join("")}${fuente("Google Noticias")}</div></div>
      <button class="btn" id="bOtraVez">Analizar de nuevo</button></div>
    ${(r.avisos || []).map((a) => `<p class="nota">${esc(a)}</p>`).join("")}
    ${R.explotando && R.explotando.length ? `<div class="sugerencia"><span>🔥 <b>Explotando ahora:</b> ${R.explotando.map(esc).join(", ")}</span></div>` : ""}
    <div class="resumen">
      <div class="cifra verde"><b>${R.suben ?? 0}</b><span>palabras van subiendo</span></div>
      <div class="cifra rojo"><b>${R.bajan ?? 0}</b><span>palabras van bajando</span></div>
      <div class="cifra ambar"><b>${R.oportunidades ?? 0}</b><span>oportunidades de venta nuevas</span></div>
      <div class="cifra"><b>${R.ideas ?? 0}</b><span>ideas que están creciendo</span></div>
    </div>
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Cómo va cada palabra</h2><p>Cada palabra con su propia curva de los últimos 3 meses, comparada consigo misma.</p></div></div>
      ${errorDe("palabras")}<div class="palabras" id="lPal"></div></section>
    ${r.redes && r.redes.coinciden && r.redes.coinciden.length ? `<section class="tarjeta"><div class="tarjeta-cab"><div><h2>🔥 Sube en varias redes a la vez</h2><p>La señal más fuerte: el mismo tema creciendo en más de una red.</p></div><button class="btn" id="bVerRedes">Ver todas las redes</button></div>
      <ul class="lista">${r.redes.coinciden.map((c) => `<li><div class="txt"><b>${esc(c.busqueda)}</b></div>${c.fuentes.map(fuente).join(" ")}</li>`).join("")}</ul></section>` : ""}
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2 id="tBus">Búsquedas que están despegando</h2><p id="pBus">Lo que más creció en el último mes en Google y en las redes, separado por tipo. Cada una dice de dónde salió.</p></div>
      <div class="segmentado" id="segBus"><button class="activo" data-v="despegan">Despegando</button><button data-v="populares">Más buscadas</button></div></div>
      ${errorDe("despegan")}<div class="pestanas" id="pestBus"></div><p class="chico" id="ayudaBus"></p><ul class="lista" id="lBus"></ul></section>
    <div class="dos-col">
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Lo que la gente pregunta</h2><p>Úsalas como títulos de anuncios, publicaciones o respuestas de WhatsApp.</p></div></div>
        ${errorDe("preguntas")}<ul class="lista" id="lPreg"></ul></section>
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Hoy en México</h2><p>De lo más buscado hoy, solo lo que toca tu mercado.</p></div></div>
        ${errorDe("hoy")}<ul class="lista" id="lHoy"></ul></section>
    </div>
    <div class="dos-col">
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>En las noticias</h2><p id="pNot">Notas por día sobre tu mercado (últimas 2 semanas).</p></div></div>
        ${errorDe("noticias")}<div id="gNot"></div><ul class="lista" id="lNot"></ul></section>
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Videos que están pegando</h2><p>Los videos de tu mercado que más rápido ganan vistas esta semana.</p></div></div>
        ${errorDe("videos")}<div id="lVid"></div></section>
    </div>
`;
  $("#bOtraVez").onclick = analizar;
  if ($("#bVerRedes")) $("#bVerRedes").onclick = () => ir("redsociales");

  // Cada palabra
  const lp = $("#lPal");
  const pal = r.palabras || [];
  lp.innerHTML = pal.length ? pal.map((p) => `<div class="palabra">
      <span class="nom">${esc(p.palabra)}</span>
      <span>${sparkline(p.serie, p.veredicto && /Baja/.test(p.veredicto) ? "#B91C1C" : p.veredicto === "Explotando" ? "#D97706" : "#2563EB")}</span>
      <span>${chipVer(p.veredicto)}</span>
      <span class="cambio ${p.cambio > 0 ? "pos" : p.cambio < 0 ? "neg" : ""}">${fpct(p.cambio)}</span>
      <span class="pop" title="Qué tan buscada es comparada con tu palabra más buscada">${p.popularidad != null ? `<span class="riel"><i style="width:${Math.max(3, p.popularidad)}%"></i></span>${p.popularidad}` : ""}</span>
      <span class="acc"><button class="btn fantasma" data-comp="${esc(p.palabra)}">Ver curva</button></span></div>`).join("")
    : `<p class="nota">No hay datos de las palabras todavía.</p>`;
  $$("[data-comp]", lp).forEach((b) => (b.onclick = () => { E.comparar = { terminos: [b.dataset.comp], periodo: "Últimos 12 meses", juntas: false }; ir("comparar"); compararAhora(); }));

  // Búsquedas por tipo
  let modo = "despegan", tipo = null, limite = 10;
  const pintarBus = () => {
    const g = r[modo] || {};
    const grupos = { venta: g.venta || [], ideas: g.ideas || [], general: g.general || [], ocultas: [...(g.info || []), ...(g.fuera || [])] };
    if (!tipo) tipo = ["venta", "ideas", "general", "ocultas"].find((k) => grupos[k].length) || "venta";
    $("#tBus").textContent = modo === "despegan" ? "Búsquedas que están despegando" : "Lo más buscado en tu mercado";
    $("#pBus").textContent = modo === "despegan" ? "Lo que más creció en el último mes en Google y en las redes, separado por tipo. Cada una dice de dónde salió." : "Las búsquedas con más volumen en Google alrededor de tus palabras, separadas por tipo.";
    $("#pestBus").innerHTML = Object.entries(TIPOS).map(([k, t]) => `<button data-t="${k}" class="${k === tipo ? "activo" : ""}">${t}<span class="cuenta">${grupos[k].length}</span></button>`).join("");
    $$("#pestBus button").forEach((b) => (b.onclick = () => { tipo = b.dataset.t; limite = 10; pintarBus(); }));
    $("#ayudaBus").textContent = AYUDA_TIPOS[tipo];
    const items = grupos[tipo];
    $("#lBus").innerHTML = items.length ? items.slice(0, limite).map((it) => `<li>
        <div class="txt"><b>${esc(it.busqueda)}</b><small>${fuente(it.fuente)} ${it.origen ? `relacionada con «${esc(it.origen)}»` : ""}</small></div>
        ${modo === "despegan" ? `<span class="chip ${it.crecimiento === "Explotando" ? "explotando" : "sube"}">${it.crecimiento === "Explotando" ? "🔥 Explotando" : esc(it.crecimiento)}</span>` : `<span class="chip">${it.interes}/100</span>`}
        <span class="acc"><button class="btn fantasma" data-cop="${esc(it.busqueda)}" title="Copiar">Copiar</button>
        <button class="btn fantasma" data-cmp="${esc(it.busqueda)}">Ver curva</button>
        ${tipo !== "ocultas" ? `<button class="btn fantasma" data-ex="${esc(it.busqueda)}" title="Ya no mostrar esta búsqueda">✕ No es de mi mercado</button>` : ""}</span></li>`).join("")
      : `<li><div class="txt chico">No hubo búsquedas de este tipo en este análisis.</div></li>`;
    if (items.length > limite) $("#lBus").insertAdjacentHTML("beforeend", `<li><button class="btn" id="bMas">Ver ${Math.min(10, items.length - limite)} más (quedan ${items.length - limite})</button></li>`);
    if ($("#bMas")) $("#bMas").onclick = () => { limite += 10; pintarBus(); };
    $$("[data-cop]", $("#lBus")).forEach((b) => (b.onclick = () => copiar(b.dataset.cop)));
    $$("[data-cmp]", $("#lBus")).forEach((b) => (b.onclick = () => { E.comparar = { terminos: [b.dataset.cmp], periodo: "Últimos 90 días", juntas: false, ajustar: false }; ir("comparar"); compararAhora(); }));
    $$("[data-ex]", $("#lBus")).forEach((b) => (b.onclick = async () => {
      await api("mercado/excluir", { texto: b.dataset.ex });
      for (const gr of ["despegan", "populares"]) for (const k in r[gr]) r[gr][k] = r[gr][k].filter((x) => x.busqueda !== b.dataset.ex);
      aviso(`Listo: ya no te mostraré «${b.dataset.ex}».`);
      pintarBus();
    }));
  };
  $$("#segBus button").forEach((b) => (b.onclick = () => { modo = b.dataset.v; tipo = null; limite = 10; $$("#segBus button").forEach((x) => x.classList.toggle("activo", x === b)); pintarBus(); }));
  pintarBus();

  // Preguntas
  const pr = r.preguntas || [];
  $("#lPreg").innerHTML = pr.length ? pr.slice(0, 10).map((p) => `<li><div class="txt">${esc(p.pregunta)}<small>${fuente(p.fuente || "Google")}</small></div>${p.tipo === "venta" ? '<span class="chip venta">💰</span>' : ""}<span class="acc"><button class="btn fantasma" data-cop="${esc(p.pregunta)}">Copiar</button></span></li>`).join("")
    : `<li><div class="txt chico">Sin preguntas por ahora.</div></li>`;
  $$("[data-cop]", $("#lPreg")).forEach((b) => (b.onclick = () => copiar(b.dataset.cop)));

  // Hoy
  const hoy = r.hoy || [];
  $("#lHoy").innerHTML = hoy.length ? hoy.map((t) => `<li><div class="txt"><b>${esc(t.tema)}</b><small>${fuente(t.fuente || "Google Tendencias")} ${esc(t.noticia)}</small></div><span class="chip">${esc(t.busquedas)}</span>${t.url ? `<a href="#" data-url="${esc(t.url)}" class="btn fantasma">Abrir</a>` : ""}</li>`).join("")
    : `<li><div class="txt chico">Hoy ninguno de los ${r.hoy_total || 0} temas más buscados en México toca tu mercado. Es normal: estos temas suelen ser deportes, espectáculos y noticias.</div></li>`;

  // Noticias
  const no = r.noticias;
  if (no) {
    $("#pNot").textContent = `${no.total} notas en 2 semanas${no.pico ? " · hoy hay más de lo normal" : ""}.`;
    const cols = no.por_dia.map((d, i) => (i === no.por_dia.length - 1 && no.pico ? "#D97706" : "#93B4F5"));
    graficaLinea($("#gNot"), { etiquetas: no.por_dia.map((d) => d[0]), series: [{ nombre: "Notas", valores: no.por_dia.map((d) => d[1]), color: "#93B4F5", colores: cols }], alto: 150, barras: true });
    $("#lNot").innerHTML = no.items.slice(0, 5).map((n) => `<li><div class="txt"><a href="#" data-url="${esc(n.url)}">${esc(n.titulo)}</a><small>${fuente("Google Noticias")} ${esc(n.medio)} · ${esc(fechaBonita(n.fecha))}</small></div></li>`).join("");
  }

  // Videos
  const vid = r.videos;
  $("#lVid").innerHTML = vid == null ? `<p class="nota">Para ver videos, agrega tu clave gratuita de YouTube en Ajustes (toma 5 minutos).</p><button class="btn" id="bClave">Ir a Ajustes</button>`
    : vid.length ? `<ul class="lista">${vid.slice(0, 6).map((v) => `<li><div class="txt"><a href="#" data-url="${esc(v.url)}">${esc(v.titulo)}</a><small>${fuente("YouTube")} ${esc(v.canal)} · ${fnum(v.vistas)} vistas</small></div><span class="chip sube">${fnum(v.vistas_hora)} vistas/hora</span></li>`).join("")}</ul>`
    : `<p class="nota">Esta semana no hubo videos nuevos de tu mercado.</p>`;
  if ($("#bClave")) $("#bClave").onclick = () => ir("ajustes");
}

// ------------------------------------------------------------ MI MERCADO
const EJEMPLOS = ["Salones de fiestas", "Bodas", "XV años", "Oficinas en renta", "Cafetería", "Restaurante", "Gimnasio", "Tienda de ropa"];
const nuevoEditor = () => ({ nombre: "", anterior: null, palabras: [], excluir: [], pinterest: "", nombre_sugerido: null, buscado: false });

function vistaMercado(c) {
  const mercados = E.estado.mercados;
  if (!E.editor && !mercados.length) E.editor = nuevoEditor();
  c.innerHTML = `<h1>Mi mercado</h1><p class="sub">Dile al programa en qué giro estás. Solo se analizarán las tendencias de ese mercado; cada mercado guarda sus propias palabras.</p>
    ${mercados.length ? `<div class="mercados">${mercados.map((m) => `<div class="mercado-card ${m.nombre === E.estado.activo ? "activo" : ""}">
        <b>${esc(m.nombre)}</b><small>${m.palabras.length} palabras${m.nombre === E.estado.activo ? " · en uso" : ""}</small>
        <div class="acc">${m.nombre !== E.estado.activo ? `<button class="btn" data-usar="${esc(m.nombre)}">Usar</button>` : ""}
        <button class="btn fantasma" data-edit="${esc(m.nombre)}">Editar</button><button class="btn fantasma peligro" data-borrar="${esc(m.nombre)}">Borrar</button></div></div>`).join("")}
      <button class="mercado-card" id="bNuevo" style="cursor:pointer;border-style:dashed;text-align:left"><b>＋ Nuevo mercado</b><small>Empieza desde cero</small></button></div>` : ""}
    <div id="editor"></div>`;
  $$("[data-usar]", c).forEach((b) => (b.onclick = async () => { await api("mercado/activar", { nombre: b.dataset.usar }); E.analisis = null; await cargarEstado(); render(); }));
  $$("[data-edit]", c).forEach((b) => (b.onclick = () => {
    const m = mercados.find((x) => x.nombre === b.dataset.edit);
    E.editor = { nombre: m.nombre, anterior: m.nombre, palabras: m.palabras.map((p) => ({ texto: p, tipo: "general", marcada: true })), excluir: [...(m.excluir || [])], pinterest: m.pinterest || "", buscado: true };
    render(); $("#editor").scrollIntoView({ behavior: "smooth" });
  }));
  $$("[data-borrar]", c).forEach((b) => (b.onclick = async () => {
    if (b.dataset.conf !== "1") { b.dataset.conf = "1"; b.textContent = "¿Seguro? Toca otra vez"; return; }
    await api("mercado/borrar", { nombre: b.dataset.borrar }); E.analisis = null; E.editor = null; await cargarEstado(); render();
  }));
  if ($("#bNuevo")) $("#bNuevo").onclick = () => { E.editor = nuevoEditor(); render(); $("#mNombre").focus(); };
  if (E.editor) pintarEditor($("#editor"));
}

function pintarEditor(c) {
  const ed = E.editor;
  const grupos = { general: [], venta: [], ideas: [], dudosas: [] };
  ed.palabras.forEach((p, i) => (grupos[p.tipo === "info" || p.tipo === "fuera" ? "dudosas" : p.tipo] || grupos.general).push([p, i]));
  const marcas = (lista) => `<div class="marcas">${lista.map(([p, i]) => `<label><input type="checkbox" data-i="${i}" ${p.marcada ? "checked" : ""}>${esc(p.texto)}</label>`).join("")}</div>`;
  const marcadas = ed.palabras.filter((p) => p.marcada).length;
  c.innerHTML = `<section class="tarjeta">
    <div class="paso-tit"><span class="paso-num">1</span><h2>${ed.anterior ? "Editar «" + esc(ed.anterior) + "»" : "¿Cuál es tu mercado?"}</h2></div>
    <div class="fila"><label class="campo" style="flex:1;max-width:460px"><span>Nombre del mercado</span>
      <input type="text" id="mNombre" value="${esc(ed.nombre)}" placeholder="Por ejemplo: salones de fiestas"></label>
      <button class="btn ${ed.buscado ? "" : "primario"}" id="bBuscar">${ed.buscado ? "Buscar más palabras" : "Buscar palabras"}</button></div>
    ${ed.buscado ? "" : `<div class="ejemplos"><span class="chico">Ejemplos:</span>${EJEMPLOS.map((x) => `<button data-ej="${esc(x)}">${esc(x)}</button>`).join("")}</div>
      <p class="chico" style="margin-top:14px">¿Prefieres una lista ya hecha? ${Object.keys(E.estado.plantillas).map((p) => `<button class="btn fantasma" data-pl="${esc(p)}">${esc(p)}</button>`).join(" ")}</p>`}
    ${ed.nombre_sugerido ? `<div class="sugerencia" style="margin-top:14px"><span>«${esc(ed.nombre)}» es muy corto y Google lo confunde con otras cosas. ¿Usamos <b>«${esc(ed.nombre_sugerido)}»</b>?</span><button class="btn" id="bSug">Usar «${esc(ed.nombre_sugerido)}»</button></div>` : ""}
    </section>
    ${ed.buscado ? `<section class="tarjeta">
      <div class="paso-tit"><span class="paso-num">2</span><h2>Marca las palabras que sí son de tu mercado</h2></div>
      <p class="chico">Ya marqué las que sirven para vender. Quita las que no apliquen. Llevas <b id="nMarcadas">${marcadas}</b> marcadas (se analizan las primeras 8).</p>
      ${grupos.general.length ? `<div class="grupo-pal"><h3>Tu mercado</h3>${marcas(grupos.general)}</div>` : ""}
      ${grupos.venta.length ? `<div class="grupo-pal"><h3><span class="chip venta">💰</span> Para vender (precios, paquetes, lugares)</h3>${marcas(grupos.venta)}</div>` : ""}
      ${grupos.ideas.length ? `<div class="grupo-pal"><h3><span class="chip ideas">💡</span> Ideas e inspiración</h3>${marcas(grupos.ideas)}</div>` : ""}
      ${grupos.dudosas.length ? `<details class="ocultas"><summary>Probablemente no son de tu mercado (${grupos.dudosas.length})</summary><div class="grupo-pal">${marcas(grupos.dudosas)}</div></details>` : ""}
      <div class="fila" style="margin-top:18px"><label class="campo" style="flex:1;max-width:460px"><span>Agregar otra palabra</span><input type="text" id="mOtra" placeholder="Por ejemplo: salón para xv años en Iztapalapa"></label><button class="btn" id="bOtra">Agregar</button></div>
    </section>
    <section class="tarjeta">
      <div class="paso-tit"><span class="paso-num">3</span><h2>Palabras a ignorar <span class="chico">(opcional)</span></h2></div>
      <p class="chico">Si algo aparece y no tiene nada que ver con tu negocio, escríbelo aquí. Ejemplo: empleo, vacantes, gratis.</p>
      <div class="etiquetas" id="mExcl">${ed.excluir.map((x, i) => `<span class="etiqueta">${esc(x)}<button data-qx="${i}" aria-label="Quitar">×</button></span>`).join("")}</div>
      <div class="fila" style="margin-top:10px"><input type="text" id="mExNueva" placeholder="Escribe y presiona Enter" style="max-width:320px"></div>
      <details style="margin-top:16px"><summary class="chico" style="cursor:pointer">Más opciones</summary>
        <label class="campo" style="max-width:320px;margin-top:10px"><span>Categoría en Pinterest</span><select id="mPin">${PIN_CATS.map(([v, t]) => `<option value="${v}" ${v === ed.pinterest ? "selected" : ""}>${t}</option>`).join("")}</select></label></details>
    </section>
    <div class="fila"><button class="btn primario grande" id="bGuardar">Guardar y analizar</button><button class="btn" id="bCancelar">Cancelar</button></div>` : ""}`;

  const nombreInput = $("#mNombre", c);
  nombreInput.oninput = () => (ed.nombre = nombreInput.value);
  nombreInput.onkeydown = (e) => { if (e.key === "Enter") buscarPalabras(); };
  $("#bBuscar", c).onclick = buscarPalabras;
  $$("[data-ej]", c).forEach((b) => (b.onclick = () => { ed.nombre = b.dataset.ej; buscarPalabras(); }));
  $$("[data-pl]", c).forEach((b) => (b.onclick = () => {
    const p = E.estado.plantillas[b.dataset.pl];
    Object.assign(ed, { nombre: ed.nombre || b.dataset.pl, palabras: p.palabras.map((t) => ({ texto: t, tipo: "general", marcada: true })), excluir: [...p.excluir], pinterest: p.pinterest, buscado: true });
    pintarEditor(c);
  }));
  if ($("#bSug", c)) $("#bSug", c).onclick = () => { ed.nombre = ed.nombre_sugerido; ed.nombre_sugerido = null; ed.palabras = []; buscarPalabras(); };
  if (!ed.buscado) return;
  $$("input[type=checkbox][data-i]", c).forEach((cb) => (cb.onchange = () => { ed.palabras[+cb.dataset.i].marcada = cb.checked; $("#nMarcadas").textContent = ed.palabras.filter((p) => p.marcada).length; }));
  const otra = () => { const v = $("#mOtra", c).value.trim(); if (!v) return; ed.palabras.unshift({ texto: v, tipo: "general", marcada: true }); pintarEditor(c); };
  $("#bOtra", c).onclick = otra; $("#mOtra", c).onkeydown = (e) => { if (e.key === "Enter") otra(); };
  $$("[data-qx]", c).forEach((b) => (b.onclick = () => { ed.excluir.splice(+b.dataset.qx, 1); pintarEditor(c); }));
  $("#mExNueva", c).onkeydown = (e) => { if (e.key === "Enter" && e.target.value.trim()) { ed.excluir.push(e.target.value.trim()); pintarEditor(c); $("#mExNueva").focus(); } };
  $("#mPin", c).onchange = (e) => (ed.pinterest = e.target.value);
  $("#bCancelar", c).onclick = () => { E.editor = E.estado.mercados.length ? null : nuevoEditor(); render(); };
  $("#bGuardar", c).onclick = async () => {
    const palabras = ed.palabras.filter((p) => p.marcada).map((p) => p.texto);
    if (!ed.nombre.trim()) return aviso("Ponle nombre a tu mercado.", "error");
    if (!palabras.length) return aviso("Marca al menos una palabra.", "error");
    try {
      await api("mercado/guardar", { nombre: ed.nombre.trim(), nombre_anterior: ed.anterior, palabras, excluir: ed.excluir, pinterest: ed.pinterest });
      E.editor = null; E.analisis = null;
      await cargarEstado();
      analizar();
    } catch (err) { aviso(err.message, "error"); }
  };
}

async function buscarPalabras() {
  const ed = E.editor;
  if (!ed.nombre.trim()) return aviso("Escribe el nombre de tu mercado.", "error");
  const boton = $("#bBuscar");
  boton.disabled = true; boton.textContent = "Buscando en Google…"; barra(20);
  try {
    const { trabajo } = await api("mercado/sugerir", { nombre: ed.nombre.trim() });
    const r = await esperar(trabajo, (t) => barra(t.pct));
    const previas = new Set(ed.palabras.map((p) => p.texto.toLowerCase()));
    const nuevas = r.palabras.filter((p) => !previas.has(p.texto.toLowerCase()));
    ed.palabras = ed.buscado ? [...ed.palabras, ...nuevas.map((p) => ({ ...p }))] : r.palabras;
    ed.nombre_sugerido = r.nombre_sugerido; ed.buscado = true;
  } catch (err) {
    aviso(errorAmable(err.message), "error", "No se pudieron buscar palabras");
  } finally { barra(null); }
  if (E.vista === "mercado") pintarEditor($("#editor"));
}

const PIN_CATS = [["", "Todas"], ["event_planning", "Planeación de eventos"], ["wedding", "Bodas"], ["food_and_drinks", "Comida y bebida"],
  ["home_decor", "Decoración del hogar"], ["womens_fashion", "Moda mujer"], ["mens_fashion", "Moda hombre"], ["beauty", "Belleza"],
  ["design", "Diseño"], ["sport", "Deporte"], ["travel", "Viajes"], ["diy_and_crafts", "Manualidades"], ["entertainment", "Entretenimiento"]];

// ------------------------------------------------------------ EN VIVO
const VIVO = { trabajo: null, error: null, auto: (() => { try { return localStorage.getItem("vivoAuto") !== "0"; } catch { return true; } })(), reloj: null };
const PASOS_VIVO = [{ hasta: 50, txt: "Google, hora por hora" }, { hasta: 60, txt: "Lo más buscado hoy" }, { hasta: 78, txt: "Videos que se vuelven virales" }, { hasta: 88, txt: "Instagram reciente" }, { hasta: 100, txt: "Noticias de las últimas 24 horas" }];
const horaCorta = (iso) => new Date(iso).toLocaleTimeString("es-MX", { hour: "numeric", minute: "2-digit" });
const haceCuanto = (iso) => { const min = Math.round((Date.now() - new Date(iso)) / 60000); return min < 1 ? "hace un momento" : min < 60 ? `hace ${min} min` : fechaBonita(iso); };

async function actualizarVivo(silencioso = false) {
  if (VIVO.trabajo || !E.estado.activo) return;
  try {
    const { trabajo } = await api("en_vivo");
    VIVO.trabajo = { pct: 1, paso: "Empezando…" }; VIVO.error = null;
    if (E.vista === "envivo") render();
    E.vivo = await esperar(trabajo, (t) => { VIVO.trabajo = t; if (!silencioso) barra(t.pct); if (E.vista === "envivo" && $("#contenido .progreso")) $("#contenido .progreso").outerHTML = progresoHTML("Buscando lo más viral ahora", t, PASOS_VIVO); });
    if (E.vivo.picos && E.vivo.picos.length) aviso(`Se está disparando ahora: ${E.vivo.picos.join(", ")}`, "pico", "🔥 En vivo");
  } catch (err) { VIVO.error = errorAmable(err.message); if (!silencioso) aviso(VIVO.error, "error", "No se pudo actualizar En vivo"); }
  finally { VIVO.trabajo = null; barra(null); if (E.vista === "envivo") render(); }
}

function programarVivo() {
  clearInterval(VIVO.reloj);
  if (VIVO.auto) VIVO.reloj = setInterval(() => actualizarVivo(true), 15 * 60 * 1000);
}

async function vistaEnVivo(c) {
  if (!E.estado.activo) { c.innerHTML = `<div class="tarjeta vacio"><h1>Primero crea tu mercado</h1><p>Así te muestro lo más viral de tu giro en este momento.</p><button class="btn primario grande" id="bCr">Crear mi mercado</button></div>`; $("#bCr").onclick = () => ir("mercado"); return; }
  if (VIVO.trabajo && !E.vivo) { c.innerHTML = progresoHTML("Buscando lo más viral ahora", VIVO.trabajo, PASOS_VIVO); return; }
  if (!E.vivo || E.vivo.mercado !== E.estado.activo) {
    E.vivo = (await api("en_vivo/ultimo")).vivo;
    if (!E.vivo && VIVO.error) {
      c.innerHTML = `<div class="tarjeta vacio"><h1>No se pudo traer lo más viral</h1><p>${esc(VIVO.error)}</p><button class="btn primario grande" id="bRe">Intentar otra vez</button></div>`;
      $("#bRe").onclick = () => actualizarVivo(); return;
    }
    if (!E.vivo) { c.innerHTML = progresoHTML("Buscando lo más viral ahora", VIVO.trabajo, PASOS_VIVO); if (!VIVO.trabajo) actualizarVivo(); return; }
  }
  const v = E.vivo, er = v.errores || {};
  const errorDe = (k) => (er[k] ? `<div class="error-sec">${esc(errorAmable(er[k]))}</div>` : "");
  const listaTemas = (lista, vacio) => (lista && lista.length ? `<ul class="lista">${lista.map((t) => `<li><div class="txt"><b>${esc(t.tema)}</b><small>${fuente(t.fuente)} ${esc(t.noticia || "")}</small></div><span class="chip">${esc(t.busquedas)} búsquedas</span>${t.url ? `<a href="#" class="btn fantasma" data-url="${esc(t.url)}">Abrir</a>` : ""}</li>`).join("")}</ul>` : `<p class="nota">${vacio}</p>`);
  const listaVideos = (lista, vacio) => (lista && lista.length ? `<ul class="lista">${lista.map((x, i) => `<li><div class="txt"><a href="#" data-url="${esc(x.url)}">${esc(x.titulo)}</a><small>${fuente("YouTube")} ${esc(x.canal)} · ${fnum(x.vistas)} vistas · publicado ${esc(fechaBonita(x.publicado))}</small></div><span class="chip ${i < 3 ? "explotando" : "sube"}">${i < 3 ? "🔥 " : ""}${fnum(x.vistas_hora)} vistas/hora</span></li>`).join("")}</ul>` : `<p class="nota">${vacio}</p>`);
  c.innerHTML = `<div class="encabezado"><div><h1 class="en-vivo-tit"><span class="vivo-punto"></span>Lo más viral ahora</h1>
      <p class="sub" style="margin:0">«${esc(v.mercado)}» · actualizado ${esc(haceCuanto(v.fecha))}${VIVO.trabajo ? ` · actualizando… ${VIVO.trabajo.pct}%` : ""}</p></div>
      <div class="fila" style="align-items:center"><label class="switch"><input type="checkbox" id="vAuto" ${VIVO.auto ? "checked" : ""}>Actualizar solo cada 15 min</label>
      <button class="btn primario" id="vYa" ${VIVO.trabajo ? "disabled" : ""}>Actualizar ahora</button></div></div>
    ${v.picos && v.picos.length ? `<div class="sugerencia"><span>🔥 <b>Se está disparando ahora en Google:</b> ${v.picos.map(esc).join(", ")}</span></div>` : ""}
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Tu mercado en las últimas 24 horas ${fuente("Google")}</h2><p>Búsquedas hora por hora. Si las últimas horas están muy arriba de lo normal del día, se marca 🔥.</p></div></div>
      ${v.google_horas.map((h) => `<div class="vivo-fila"><b>${esc(h.palabra)}</b>${h.error ? `<span class="chico">${esc(errorAmable(h.error))}</span><span></span><span></span>` : `${sparkline(h.serie, h.pico ? "#D97706" : "#2563EB", 240, 36)}<span>${h.pico ? '<span class="chip explotando">🔥 Disparándose</span>' : (h.cambio > 15 ? '<span class="chip sube">↗ Subiendo</span>' : h.cambio < -15 ? '<span class="chip baja">↘ Más bajo</span>' : '<span class="chip estable">→ Normal</span>')}</span><span class="cambio ${h.cambio > 0 ? "pos" : h.cambio < 0 ? "neg" : ""}" style="text-align:right" title="Últimas 3 horas contra el resto del día">${fpct(h.cambio)}</span>`}</div>`).join("")}
    </section>
    <div class="dos-col">
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Lo más buscado hoy ${fuente("Google Tendencias")}</h2><p>Los temas que explotaron en Google hoy en México.</p></div>
        <div class="segmentado" id="segHoy"><button class="activo" data-h="m">De tu mercado (${(v.hoy_mercado || []).length})</button><button data-h="g">Todo México</button></div></div>
        ${errorDe("hoy")}<div id="lHoyV"></div></section>
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Noticias de las últimas 24 horas ${fuente("Google Noticias")}</h2><p>Lo que se está publicando ahora sobre tu mercado.</p></div></div>
        ${errorDe("noticias")}${(v.noticias || []).length ? `<ul class="lista">${v.noticias.map((n) => `<li><div class="txt"><a href="#" data-url="${esc(n.url)}">${esc(n.titulo)}</a><small>${fuente("Google Noticias")} ${esc(n.medio)} · ${esc(horaCorta(n.fecha))}</small></div></li>`).join("")}</ul>` : `<p class="nota">No hubo noticias de tu mercado en las últimas 24 horas.</p>`}</section>
    </div>
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Videos que se están volviendo virales ${fuente("YouTube")}</h2><p>Ordenados por vistas por hora desde que se publicaron.</p></div>
      ${v.videos_mercado == null ? "" : `<div class="segmentado" id="segVid"><button class="activo" data-v="m">De tu mercado (últimas 48 h)</button><button data-v="g">Tendencias de YouTube México</button></div>`}</div>
      ${v.videos_mercado == null ? `<p class="nota">Agrega tu clave gratuita de YouTube en Ajustes para ver aquí los videos que se están volviendo virales.</p><button class="btn" id="bClaveV">Ir a Ajustes</button>` : errorDe("videos_mercado") + errorDe("videos_general") + `<div id="lVidV"></div>`}</section>
    <div class="dos-col">
      <section class="red-card c-instagram"><h2>${fuente("Instagram")} Instagram ahora</h2><p class="que">Lo más reciente de los hashtags de tu mercado (últimas 24 horas).</p>
        ${v.instagram == null ? `<p class="nota">Conecta tu cuenta profesional de Instagram en Ajustes para ver esto aquí.</p>` : errorDe("instagram") + (v.instagram.length ? `<ul class="lista">${v.instagram.map((p) => `<li><div class="txt"><a href="#" data-url="${esc(p.url)}">${esc(p.texto || "(sin texto)")}</a><small>${fuente("Instagram")} #${esc(p.hashtag)}</small></div><span class="chip">♥ ${fnum(p.likes)}</span></li>`).join("")}</ul>` : `<p class="nota">Sin publicaciones recientes.</p>`)}
        ${(v.enlaces.instagram || []).map((l) => `<div class="enlaces-red"><a href="#" data-url="${esc(l.url)}">${esc(l.texto)}</a></div>`).join("")}</section>
      <section class="red-card c-tiktok"><h2>${fuente("TikTok")} ${fuente("Facebook")} ${fuente("X")} Ver en vivo</h2><p class="que">Estas redes no comparten sus datos de tendencias con programas externos. Ábrelas aquí, ya con la búsqueda de tu mercado:</p>
        <div class="enlaces-red">${[...(v.enlaces.tiktok || []), ...(v.enlaces.facebook || []), ...(v.enlaces.x || [])].map((l) => `<a href="#" data-url="${esc(l.url)}">${esc(l.texto)}</a>`).join("")}</div></section>
    </div>`;
  let hoyModo = "m", vidModo = "m";
  const pintarHoy = () => ($("#lHoyV").innerHTML = hoyModo === "m" ? listaTemas(v.hoy_mercado, `Ahorita ninguno de los temas más buscados de México toca tu mercado. Cambia a «Todo México» para ver lo más viral en general.`) : listaTemas(v.hoy_general, "Sin datos."));
  pintarHoy();
  $$("#segHoy button").forEach((b) => (b.onclick = () => { hoyModo = b.dataset.h; $$("#segHoy button").forEach((x) => x.classList.toggle("activo", x === b)); pintarHoy(); }));
  if ($("#lVidV")) {
    const pintarVid = () => ($("#lVidV").innerHTML = vidModo === "m" ? listaVideos(v.videos_mercado, "No hubo videos nuevos de tu mercado en las últimas 48 horas.") : listaVideos(v.videos_general, "Sin datos."));
    pintarVid();
    $$("#segVid button").forEach((b) => (b.onclick = () => { vidModo = b.dataset.v; $$("#segVid button").forEach((x) => x.classList.toggle("activo", x === b)); pintarVid(); }));
  }
  if ($("#bClaveV")) $("#bClaveV").onclick = () => ir("ajustes");
  $("#vYa").onclick = () => actualizarVivo();
  $("#vAuto").onchange = (e) => { VIVO.auto = e.target.checked; try { localStorage.setItem("vivoAuto", VIVO.auto ? "1" : "0"); } catch { /* sin almacenamiento */ } programarVivo(); aviso(VIVO.auto ? "En vivo se actualizará solo cada 15 minutos." : "Actualización automática apagada."); };
}

// ------------------------------------------------------------ REDES SOCIALES
const TEXTO_RED = {
  google: "Lo que la gente busca en Google: tu base para saber qué tiene demanda.",
  youtube: "Lo que la gente busca en YouTube: qué temas quieren ver en video (útil también para TikTok y Reels).",
  imagenes: "Lo que la gente busca en Google Imágenes: lo visual que buscan, buena pista para Instagram y Pinterest.",
  shopping: "Lo que la gente busca en Google Shopping: señal de que quieren comprar.",
  pinterest: "Ideas que empiezan a crecer en Pinterest, antes de volverse masivas.",
  instagram: "Las publicaciones con más interacción de los hashtags de tu mercado.",
  tiktok: "TikTok no comparte sus datos de tendencias con programas externos. Ábrelos aquí, en sus páginas oficiales:",
  facebook: "Facebook no comparte datos de tendencias. Lo más útil es ver los anuncios que está pagando tu competencia:",
  x: "Lo que se está publicando ahora mismo:",
};

let investigandoRedes = null;
async function investigarRedes() {
  if (investigandoRedes) return;
  try {
    const { trabajo } = await api("redes/investigar");
    investigandoRedes = { pct: 1, paso: "Empezando…" };
    if (E.vista === "redsociales") render();
    E.analisis = await esperar(trabajo, (t) => { investigandoRedes = t; barra(t.pct); if (E.vista === "redsociales" && $("#contenido .progreso")) $("#contenido .progreso").outerHTML = progresoHTML("Investigando en redes", t, PASOS_REDES); });
    aviso("Ya puedes ver qué sube en cada red.", "", "Investigación lista");
  } catch (err) { aviso(errorAmable(err.message), "error", "No se pudo investigar en redes"); }
  finally { investigandoRedes = null; barra(null); if (E.vista === "redsociales") render(); }
}
const PASOS_REDES = [{ hasta: 20, txt: "YouTube" }, { hasta: 35, txt: "Google Imágenes" }, { hasta: 50, txt: "Google Shopping" }, { hasta: 60, txt: "Lo que se busca en YouTube" }, { hasta: 75, txt: "Pinterest" }, { hasta: 95, txt: "Instagram" }, { hasta: 100, txt: "Cruzar lo que sube en todas" }];

async function vistaRedesSociales(c) {
  if (!E.estado.activo) { c.innerHTML = `<div class="tarjeta vacio"><h1>Primero crea tu mercado</h1><p>Así investigo en las redes solo lo que es de tu giro.</p><button class="btn primario grande" id="bCr">Crear mi mercado</button></div>`; $("#bCr").onclick = () => ir("mercado"); return; }
  if (investigandoRedes) { c.innerHTML = progresoHTML("Investigando en redes", investigandoRedes, PASOS_REDES); return; }
  if (!E.analisis) { cargando(c, "Cargando…"); E.analisis = (await api("analisis/ultimo")).analisis; if (E.vista !== "redsociales") return; }
  const r = E.analisis && E.analisis.redes;
  if (!r) {
    c.innerHTML = `<div class="tarjeta vacio"><h1>Investigar «${esc(E.estado.activo)}» en redes</h1><p>Reviso tu mercado en YouTube, Google Imágenes, Google Shopping, Pinterest e Instagram, y te dejo a un clic TikTok, Facebook y X. Cada dato dice de qué red salió. Tarda alrededor de un minuto.</p><button class="btn primario grande" id="bInv">Investigar en redes</button></div>`;
    $("#bInv").onclick = investigarRedes; return;
  }
  const redes = r.redes || {}, en = r.enlaces || {};
  const filas = (pal) => (pal || []).map((p) => `<div class="fila-red"><span>${esc(p.palabra)}</span>${sparkline(p.serie, "#5B6B88", 110, 26)}${chipVer(p.veredicto)}<span class="cambio ${p.cambio > 0 ? "pos" : p.cambio < 0 ? "neg" : ""}" style="text-align:right">${fpct(p.cambio)}</span></div>`).join("");
  const suben = (lista, f) => (lista && lista.length ? `<h3>Lo que más sube aquí</h3><ul class="lista">${lista.slice(0, 8).map((x) => `<li><div class="txt"><b>${esc(x.busqueda)}</b><small>${fuente(f)}${x.tipo === "venta" ? ' <span class="chip venta">💰 venta</span>' : x.tipo === "ideas" ? ' <span class="chip ideas">💡 idea</span>' : ""}</small></div>${x.crecimiento ? `<span class="chip ${x.crecimiento === "Explotando" ? "explotando" : "sube"}">${x.crecimiento === "Explotando" ? "🔥 Explotando" : esc(x.crecimiento)}</span>` : ""}<span class="acc"><button class="btn fantasma" data-cop="${esc(x.busqueda)}">Copiar</button></span></li>`).join("")}</ul>` : "");
  const links = (k) => (en[k] && en[k].length ? `<div class="enlaces-red">${en[k].map((l) => `<a href="#" data-url="${esc(l.url)}">${esc(l.texto)}</a>`).join("")}</div>` : "");
  const error = (red) => (red && red.estado === "error" ? `<div class="error-sec">${esc(errorAmable(red.error))}</div>` : "");
  const tarjeta = (k, nombre, cuerpo) => `<section class="red-card c-${k}"><h2>${fuente(nombre)} ${esc(nombre)}</h2><p class="que">${TEXTO_RED[k]}</p>${cuerpo}</section>`;
  const pal = (E.analisis.palabras || []);
  const yt = redes.youtube || {};
  c.innerHTML = `<div class="encabezado"><div><h1>Redes sociales</h1><p class="sub" style="margin:0">«${esc(E.estado.activo)}» · investigado ${esc(fechaBonita(E.analisis.fecha_redes || E.analisis.fecha))}</p></div>
      <button class="btn" id="bInv">Investigar de nuevo</button></div>
    ${r.coinciden && r.coinciden.length ? `<section class="tarjeta"><div class="tarjeta-cab"><div><h2>🔥 Sube en varias redes a la vez</h2><p>El mismo tema creciendo en más de una red: la señal más fuerte para invertir en anuncios o contenido.</p></div></div>
      <ul class="lista">${r.coinciden.map((x) => `<li><div class="txt"><b>${esc(x.busqueda)}</b></div>${x.fuentes.map(fuente).join(" ")}<span class="acc"><button class="btn fantasma" data-cop="${esc(x.busqueda)}">Copiar</button></span></li>`).join("")}</ul></section>`
      : `<p class="nota">En esta revisión ningún tema apareció subiendo en dos redes a la vez. Abajo está lo que sube en cada una.</p>`}
    <div class="redes-grid">
      ${pal.length ? tarjeta("google", "Google", filas(pal.slice(0, 6))) : ""}
      ${tarjeta("youtube", "YouTube", error(yt) + filas(yt.palabras) + suben(yt.suben, "YouTube") + (yt.sugerencias && yt.sugerencias.length ? `<h3>Lo que la gente escribe en YouTube</h3><div class="chips-texto">${yt.sugerencias.slice(0, 14).map((s) => `<span>${esc(s.texto)}</span>`).join("")}</div>` : "") + links("youtube"))}
      ${tarjeta("imagenes", "Google Imágenes", error(redes.imagenes) + filas((redes.imagenes || {}).palabras) + suben((redes.imagenes || {}).suben, "Google Imágenes"))}
      ${tarjeta("shopping", "Google Shopping", error(redes.shopping) + filas((redes.shopping || {}).palabras) + suben((redes.shopping || {}).suben, "Google Shopping"))}
      ${tarjeta("pinterest", "Pinterest", ((redes.pinterest || {}).estado === "sin_clave" ? `<p class="nota">Conecta Pinterest en Ajustes (token gratuito) para ver aquí lo que crece. Mientras, ábrelo directo:</p>`
        : error(redes.pinterest) + ((redes.pinterest || {}).estado === "ok" && !((redes.pinterest || {}).suben || []).length ? `<p class="nota">Esta semana no hubo ideas de tu mercado entre lo que más crece en Pinterest. Tip: en «Mi mercado › Más opciones» elige su categoría (por ejemplo «Bodas» o «Planeación de eventos»).</p>` : suben((redes.pinterest || {}).suben, "Pinterest"))) + links("pinterest"))}
      ${tarjeta("instagram", "Instagram", ((redes.instagram || {}).estado === "sin_clave" ? `<p class="nota">Conecta tu cuenta profesional de Instagram en Ajustes para ver aquí las publicaciones que más pegan. Mientras, ábrelo directo:</p>`
        : error(redes.instagram) + (((redes.instagram || {}).publicaciones || []).length ? `<ul class="lista">${redes.instagram.publicaciones.map((p) => `<li><div class="txt"><a href="#" data-url="${esc(p.url)}">${esc(p.texto || "(sin texto)")}</a><small>${fuente("Instagram")} #${esc(p.hashtag)}</small></div><span class="chip">♥ ${fnum(p.likes)}</span><span class="chip">💬 ${fnum(p.comentarios)}</span></li>`).join("")}</ul>` : "")) + links("instagram"))}
      ${tarjeta("tiktok", "TikTok", links("tiktok"))}
      ${tarjeta("facebook", "Facebook", links("facebook"))}
      ${tarjeta("x", "X", links("x"))}
    </div>`;
  $("#bInv").onclick = investigarRedes;
  $$("[data-cop]", c).forEach((b) => (b.onclick = () => copiar(b.dataset.cop)));
}

// ------------------------------------------------------------ COMPARAR
const PERIODOS = ["Últimos 7 días", "Últimos 30 días", "Últimos 90 días", "Últimos 12 meses", "Últimos 5 años"];

function vistaComparar(c) {
  const mer = E.estado.mercados.find((m) => m.nombre === E.estado.activo);
  if (!E.comparar) E.comparar = { terminos: mer ? mer.palabras.slice(0, 3) : [], periodo: "Últimos 90 días", juntas: false, ajustar: true };
  const st = E.comparar;
  c.innerHTML = `<h1>Comparar palabras</h1><p class="sub">Mira cómo va cada palabra por separado (cada una con su propia escala) o júntalas para ver cuál se busca más.</p>
    <section class="tarjeta">
      <label class="campo"><span>Palabras (hasta 5)</span></label>
      <div class="etiquetas" id="cTer">${st.terminos.map((t, i) => `<span class="etiqueta">${esc(t)}<button data-q="${i}" aria-label="Quitar">×</button></span>`).join("")}
        ${st.terminos.length < 5 ? `<input type="text" id="cNuevo" placeholder="Escribe y presiona Enter" style="min-width:240px">` : ""}</div>
      <div class="fila" style="margin-top:16px">
        <label class="campo"><span>Periodo</span><select id="cPer">${PERIODOS.map((p) => `<option ${p === st.periodo ? "selected" : ""}>${p}</option>`).join("")}</select></label>
        <div class="campo"><span>Ver</span><div class="segmentado" id="cModo"><button data-j="0" class="${!st.juntas ? "activo" : ""}">Cada una por separado</button><button data-j="1" class="${st.juntas ? "activo" : ""}">Juntas</button></div></div>
        ${mer ? `<label class="switch" style="margin-bottom:8px"><input type="checkbox" id="cAj" ${st.ajustar !== false ? "checked" : ""}>Ajustar a mi mercado</label>` : ""}
        <button class="btn primario" id="cIr" style="margin-left:auto">Comparar</button></div>
    </section><div id="cRes"></div>`;
  $$("[data-q]", c).forEach((b) => (b.onclick = () => { st.terminos.splice(+b.dataset.q, 1); vistaComparar(c); }));
  const inp = $("#cNuevo", c);
  if (inp) inp.onkeydown = (e) => { if (e.key === "Enter" && inp.value.trim()) { st.terminos.push(inp.value.trim()); vistaComparar(c); $("#cNuevo")?.focus(); } };
  $("#cPer", c).onchange = (e) => (st.periodo = e.target.value);
  $$("#cModo button", c).forEach((b) => (b.onclick = () => { st.juntas = b.dataset.j === "1"; $$("#cModo button").forEach((x) => x.classList.toggle("activo", x === b)); }));
  if ($("#cAj", c)) $("#cAj", c).onchange = (e) => (st.ajustar = e.target.checked);
  $("#cIr", c).onclick = compararAhora;
  if (st.resultado) pintarComparacion(st.resultado);
}

async function compararAhora() {
  const st = E.comparar;
  const inp = $("#cNuevo");
  if (inp && inp.value.trim()) st.terminos.push(inp.value.trim());
  if (!st.terminos.length) return aviso("Escribe al menos una palabra.", "error");
  const res = $("#cRes");
  res.innerHTML = progresoHTML("Consultando Google Trends", { pct: 2, paso: "Empezando…" }, [{ hasta: 100, txt: "Medir cada palabra" }]);
  try {
    const { trabajo } = await api("comparar", { terminos: st.terminos, periodo: st.periodo, juntas: st.juntas, ajustar: st.ajustar !== false });
    const r = await esperar(trabajo, (t) => { barra(t.pct); if ($("#cRes .progreso")) $("#cRes").innerHTML = progresoHTML("Consultando Google Trends", t, [{ hasta: 100, txt: "Medir cada palabra" }]); });
    st.resultado = r;
    if (E.vista === "comparar") pintarComparacion(r);
  } catch (err) {
    if ($("#cRes")) $("#cRes").innerHTML = `<div class="error-sec">${esc(errorAmable(err.message))}</div>`;
  } finally { barra(null); }
}

function pintarComparacion(r) {
  const res = $("#cRes");
  if (!res) return;
  if (r.juntas) {
    res.innerHTML = `<section class="tarjeta"><div class="tarjeta-cab"><h2>Todas juntas</h2><button class="btn" id="cExp">Guardar en Excel (CSV)</button></div>
      <div class="leyenda">${r.series.map((s, i) => `<span><i style="background:${COLORES[i]}"></i>${esc(s.palabra)} ${chipVer(s.veredicto)}</span>`).join("")}</div><div id="cG"></div>
      <p class="chico">100 = el momento con más búsquedas entre todas. Si una palabra se ve plana, cámbiate a «Cada una por separado».</p></section>`;
    graficaLinea($("#cG"), { etiquetas: r.fechas, series: r.series.map((s, i) => ({ nombre: s.palabra, valores: s.serie, color: COLORES[i] })) });
    $("#cExp").onclick = () => exportar("comparacion", ["Fecha", ...r.series.map((s) => s.palabra)], r.fechas.map((f, j) => [f, ...r.series.map((s) => s.serie[j])]));
  } else {
    res.innerHTML = `${r.aviso ? `<p class="nota">${esc(r.aviso)}</p>` : ""}<div class="mini-graficas">${r.series.map((s, i) => `<div class="mini"><div class="cab"><h3>${esc(s.palabra)}</h3>${chipVer(s.veredicto)}</div>
        <p class="chico" style="margin:0 0 6px">${s.error ? esc(errorAmable(s.error)) : `Cambio reciente: <b class="cambio ${s.cambio > 0 ? "pos" : s.cambio < 0 ? "neg" : ""}">${fpct(s.cambio)}</b>`}</p><div id="cg${i}"></div></div>`).join("")}</div>`;
    r.series.forEach((s, i) => { if (s.serie.length) graficaLinea($("#cg" + i), { etiquetas: s.fechas, series: [{ nombre: s.palabra, valores: s.serie, color: COLORES[i % 5], area: true }], alto: 170 }); });
  }
}

async function exportar(nombre, columnas, filas) {
  try { const r = await api("exportar", { nombre, columnas, filas }); aviso("Guardado en " + r.ruta, "", "Listo"); }
  catch (err) { aviso(err.message, "error"); }
}

// ------------------------------------------------------------ NOTICIAS Y VIDEOS
function vistaRedes(c) {
  if (!E.redes) E.redes = { tema: "", dias: 7 };
  const st = E.redes;
  c.innerHTML = `<h1>Noticias y videos</h1><p class="sub">Cuántas noticias hablan de tu mercado y qué videos están pegando. Deja el tema vacío para ver todo tu mercado.</p>
    <section class="tarjeta"><div class="fila">
      <label class="campo" style="flex:1;max-width:420px"><span>Tema dentro de tu mercado <span class="chico">(opcional)</span></span><input type="text" id="rTema" value="${esc(st.tema)}" placeholder="Por ejemplo: decoración"></label>
      <div class="campo"><span>Periodo</span><div class="segmentado" id="rDias">${[3, 7, 14, 30].map((d) => `<button data-d="${d}" class="${d === st.dias ? "activo" : ""}">${d} días</button>`).join("")}</div></div>
      <button class="btn primario" id="rIr">Buscar</button></div></section><div id="rRes"></div>`;
  $("#rTema", c).oninput = (e) => (st.tema = e.target.value);
  $("#rTema", c).onkeydown = (e) => { if (e.key === "Enter") buscarRedes(); };
  $$("#rDias button", c).forEach((b) => (b.onclick = () => { st.dias = +b.dataset.d; $$("#rDias button").forEach((x) => x.classList.toggle("activo", x === b)); }));
  $("#rIr", c).onclick = buscarRedes;
  if (st.resultado) pintarRedes(st.resultado);
}

async function buscarRedes() {
  const st = E.redes;
  $("#rRes").innerHTML = progresoHTML("Buscando noticias y videos", { pct: 3, paso: "Empezando…" }, [{ hasta: 50, txt: "Noticias" }, { hasta: 100, txt: "Videos" }]);
  try {
    const { trabajo } = await api("redes", { tema: st.tema, dias: st.dias });
    st.resultado = await esperar(trabajo, (t) => { barra(t.pct); if ($("#rRes .progreso")) $("#rRes").innerHTML = progresoHTML("Buscando noticias y videos", t, [{ hasta: 50, txt: "Noticias" }, { hasta: 100, txt: "Videos" }]); });
    if (E.vista === "redes") pintarRedes(st.resultado);
  } catch (err) { if ($("#rRes")) $("#rRes").innerHTML = `<div class="error-sec">${esc(errorAmable(err.message))}</div>`; }
  finally { barra(null); }
}

function pintarRedes(r) {
  const no = r.noticias, vid = r.videos, er = r.errores || {};
  $("#rRes").innerHTML = `<section class="tarjeta"><div class="tarjeta-cab"><div><h2>Noticias sobre «${esc(r.tema)}»</h2>
      <p>${no ? `${no.total} notas${no.pico ? " · hoy hay más de lo normal 🔥" : ""}${no.total >= 100 ? " · Google entrega máximo 100: el tema es muy grande" : ""}` : ""}</p></div></div>
      ${er.noticias ? `<div class="error-sec">${esc(errorAmable(er.noticias))}</div>` : `<div id="rG"></div><ul class="lista">${no.items.map((n) => `<li><div class="txt"><a href="#" data-url="${esc(n.url)}">${esc(n.titulo)}</a><small>${esc(n.medio)} · ${esc(fechaBonita(n.fecha))}</small></div></li>`).join("")}</ul>`}</section>
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Videos que más rápido crecen</h2><p>Ordenados por vistas por hora desde que se publicaron.</p></div></div>
      ${vid == null ? `<p class="nota">Agrega tu clave gratuita de YouTube en Ajustes para ver videos.</p>` : er.videos ? `<div class="error-sec">${esc(errorAmable(er.videos))}</div>`
        : vid.length ? `<table><thead><tr><th>Video</th><th>Canal</th><th class="num">Vistas</th><th class="num">Vistas por hora</th><th class="num">Interacción</th></tr></thead><tbody>
          ${vid.map((v, i) => `<tr class="${i < 3 ? "pico" : ""}"><td><a href="#" data-url="${esc(v.url)}">${esc(v.titulo)}</a></td><td>${esc(v.canal)}</td><td class="num">${fnum(v.vistas)}</td><td class="num">${fnum(v.vistas_hora)}</td><td class="num">${v.engagement}%</td></tr>`).join("")}</tbody></table>`
        : `<p class="nota">No hubo videos nuevos en este periodo.</p>`}</section>`;
  if (no && !er.noticias) graficaLinea($("#rG"), { etiquetas: no.por_dia.map((d) => d[0]), series: [{ nombre: "Notas", valores: no.por_dia.map((d) => d[1]), color: "#93B4F5", colores: no.por_dia.map((d, i) => (i === no.por_dia.length - 1 && no.pico ? "#D97706" : "#93B4F5")) }], alto: 170, barras: true });
}

// ------------------------------------------------------------ MIS VENTAS
function vistaVentas(c) {
  const st = E.ventas;
  c.innerHTML = `<h1>Mis ventas</h1><p class="sub">Abre tu Excel o CSV de ventas, reservas o tu reporte de Google Analytics. Te digo cómo vas, qué productos suben y cuánto podrías vender después.</p>
    <label class="zona-archivo" id="vZona"><b>Arrastra tu archivo aquí o haz clic para elegirlo</b><span class="chico">Excel (.xlsx) o CSV, con una columna de fecha</span><input type="file" id="vArch" accept=".csv,.xlsx,.xlsm,.txt" hidden></label>
    <div id="vCfg"></div><div id="vRes"></div>`;
  const zona = $("#vZona", c), inp = $("#vArch", c);
  inp.onchange = () => inp.files[0] && leerArchivo(inp.files[0]);
  zona.ondragover = (e) => { e.preventDefault(); zona.classList.add("encima"); };
  zona.ondragleave = () => zona.classList.remove("encima");
  zona.ondrop = (e) => { e.preventDefault(); zona.classList.remove("encima"); if (e.dataTransfer.files[0]) leerArchivo(e.dataTransfer.files[0]); };
  if (st) { pintarCfgVentas(); if (st.resultado) pintarVentas(); }
}

async function leerArchivo(archivo) {
  barra(30);
  try {
    const b64 = await new Promise((ok, mal) => { const fr = new FileReader(); fr.onload = () => ok(fr.result.split(",")[1]); fr.onerror = mal; fr.readAsDataURL(archivo); });
    const r = await api("datos/leer", { nombre: archivo.name, contenido: b64 });
    E.ventas = { ...r, fecha: r.sugeridas.fecha || r.encabezados[0], valor: r.sugeridas.valor || "", categoria: r.sugeridas.categoria || "", freq: "W", pron: 4 };
    pintarCfgVentas(); analizarVentas();
  } catch (err) { aviso(err.message, "error", "No se pudo leer el archivo"); }
  finally { barra(null); }
}

function pintarCfgVentas() {
  const st = E.ventas;
  const opts = (sel, extra) => (extra ? `<option value="">${extra}</option>` : "") + st.encabezados.map((h) => `<option ${h === sel ? "selected" : ""}>${esc(h)}</option>`).join("");
  $("#vCfg").innerHTML = `<section class="tarjeta" style="margin-top:18px"><div class="tarjeta-cab"><div><h2>${esc(st.archivo)}</h2><p>${fnum(st.filas)} filas. Revisa que las columnas sean correctas.</p></div></div>
    <div class="fila">
      <label class="campo"><span>Fecha</span><select id="vF">${opts(st.fecha)}</select></label>
      <label class="campo"><span>Cantidad a sumar</span><select id="vV">${opts(st.valor, "Contar filas")}</select></label>
      <label class="campo"><span>Producto o categoría</span><select id="vC">${opts(st.categoria, "Ninguna")}</select></label>
      <div class="campo"><span>Agrupar por</span><div class="segmentado" id="vFr">${[["D", "Día"], ["W", "Semana"], ["M", "Mes"]].map(([k, t]) => `<button data-f="${k}" class="${k === st.freq ? "activo" : ""}">${t}</button>`).join("")}</div></div>
      <button class="btn primario" id="vIr">Analizar</button></div></section>`;
  $("#vF").onchange = (e) => (st.fecha = e.target.value);
  $("#vV").onchange = (e) => (st.valor = e.target.value);
  $("#vC").onchange = (e) => (st.categoria = e.target.value);
  $$("#vFr button").forEach((b) => (b.onclick = () => { st.freq = b.dataset.f; $$("#vFr button").forEach((x) => x.classList.toggle("activo", x === b)); analizarVentas(); }));
  $("#vIr").onclick = analizarVentas;
}

async function analizarVentas() {
  const st = E.ventas;
  try {
    st.resultado = await api("datos/analizar", { id: st.id, fecha: st.fecha, valor: st.valor, categoria: st.categoria, freq: st.freq, pronostico: st.pron, incompleto: true });
    st.cat = null;
    pintarVentas();
  } catch (err) { aviso(err.message, "error"); }
}

function pintarVentas() {
  const st = E.ventas, r = st.resultado, k = r.kpis;
  const uni = { D: ["día", "días"], W: ["semana", "semanas"], M: ["mes", "meses"] }[r.freq];
  const etiqueta = (iso) => { const f = new Date(iso + "T12:00"); return r.freq === "M" ? `${MESES[f.getMonth()]} ${f.getFullYear()}` : r.freq === "W" ? `sem. ${f.getDate()} ${MESES[f.getMonth()]}` : `${f.getDate()} ${MESES[f.getMonth()]}`; };
  const tend = k.pendiente_pct > 0.5 ? "Subiendo" : k.pendiente_pct < -0.5 ? "Bajando" : "Estable";
  const dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
  let mejorDia = "";
  if (k.factores_dia) { const i = k.factores_dia.indexOf(Math.max(...k.factores_dia)); mejorDia = `Tu mejor día es el ${dias[i]} (${fpct((k.factores_dia[i] - 1) * 100)} sobre el promedio).`; }
  $("#vRes").innerHTML = `<div class="kpis">
      <div class="cifra"><b>${fnum(k.total)}</b><span>total del periodo</span></div>
      <div class="cifra"><b>${fnum(k.promedio)}</b><span>promedio por ${uni[0]}</span></div>
      <div class="cifra ${k.crecimiento > 0 ? "verde" : k.crecimiento < 0 ? "rojo" : ""}"><b>${fpct(k.crecimiento)}</b><span>últimas ${k.ventana} ${uni[k.ventana === 1 ? 0 : 1]} vs anteriores</span></div>
      <div class="cifra"><b>${tend}</b><span>${fpct(k.pendiente_pct)} por ${uni[0]}</span></div>
      <div class="cifra ambar"><b>${fnum(r.pronostico.valores[0])}</b><span>pronóstico próximo ${uni[0]}</span></div></div>
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Cómo vas</h2><p>Mejor ${uni[0]}: ${esc(etiqueta(k.mejor.periodo))} con ${fnum(k.mejor.valor)}. ${esc(mejorDia)}${r.incompleto ? (r.freq === "W" ? " No conté la semana actual porque está incompleta." : ` No conté el ${uni[0]} actual porque está incompleto.`) : ""}</p></div>
      <button class="btn" id="vExp">Guardar en Excel (CSV)</button></div>
      <div class="leyenda"><span><i style="background:#2563EB"></i>Total</span><span><i style="background:#8A97AE"></i>Promedio</span><span><i style="background:#D97706"></i>Pronóstico</span>${st.cat ? `<span><i style="background:#16A34A"></i>${esc(st.cat)}</span>` : ""}</div><div id="vG"></div></section>
    ${r.ranking.length ? `<section class="tarjeta"><div class="tarjeta-cab"><div><h2>Qué sube y qué baja</h2><p>Últimas ${r.kpis.ventana} ${uni[1]} contra las ${r.kpis.ventana} anteriores. Haz clic en uno para verlo en la gráfica.</p></div></div>
      <table><thead><tr><th>Producto o categoría</th><th class="num">Total</th><th></th><th class="num">Reciente</th><th class="num">Cambio</th></tr></thead><tbody>
      ${(() => { const tope = Math.max(...r.ranking.map((x) => x.total), 1); return r.ranking.map((x) => `<tr data-cat="${esc(x.categoria)}" style="cursor:pointer" class="${st.cat === x.categoria ? "pico" : ""}"><td><b>${esc(x.categoria)}</b></td><td class="num">${fnum(x.total)}</td><td style="width:22%"><div class="barra-tabla" style="width:${(x.total / tope) * 100}%"></div></td><td class="num">${fnum(x.reciente)}</td><td class="num"><span class="chip ${x.cambio === "nuevo" || x.cambio > 0 ? "sube" : x.cambio < 0 ? "baja" : "estable"}">${fpct(x.cambio)}</span></td></tr>`).join(""); })()}
      </tbody></table></section>` : `<p class="nota">Elige una columna de producto o categoría para ver qué sube y qué baja.</p>`}`;
  const n = r.periodos.length, p = r.pronostico.periodos.length;
  const etiquetas = [...r.periodos, ...r.pronostico.periodos];
  const series = [
    { nombre: "Total", valores: [...r.valores, ...Array(p).fill(null)], color: "#2563EB", area: true },
    { nombre: "Promedio", valores: [...r.media_movil, ...Array(p).fill(null)], color: "#8A97AE", punteada: true, grosor: 1.6 },
    { nombre: "Pronóstico", valores: [...Array(n - 1).fill(null), r.valores[n - 1], ...r.pronostico.valores], color: "#D97706", punteada: true },
  ];
  if (st.cat && r.por_categoria[st.cat]) series.push({ nombre: st.cat, valores: [...r.por_categoria[st.cat], ...Array(p).fill(null)], color: "#16A34A" });
  graficaLinea($("#vG"), { etiquetas, series, alto: 300, formatoX: etiqueta });
  $$("[data-cat]").forEach((tr) => (tr.onclick = () => { st.cat = st.cat === tr.dataset.cat ? null : tr.dataset.cat; pintarVentas(); }));
  $("#vExp").onclick = () => exportar("ventas", ["Periodo", "Total", "Pronóstico"], [...r.periodos.map((x, i) => [x, r.valores[i], ""]), ...r.pronostico.periodos.map((x, i) => [x, "", Math.round(r.pronostico.valores[i])])]);
}

// ------------------------------------------------------------ ALERTAS
async function vistaAlertas(c) {
  cargando(c, "Cargando alertas…");
  const a = await api("alertas");
  if (E.vista !== "alertas") return;
  $("#globoAlertas").hidden = true;
  c.innerHTML = `<h1>Alertas</h1><p class="sub">Elige palabras para vigilar. Si una se dispara en Google o en las noticias, te aviso con un mensaje y un sonido. Deja el programa abierto (puede estar minimizado).</p>
    <section class="tarjeta"><div class="tarjeta-cab"><h2>Palabras vigiladas</h2>${E.estado.activo ? `<button class="btn" id="aMer">Vigilar las palabras de mi mercado</button>` : ""}</div>
      <div class="etiquetas">${a.terminos.map((t) => `<span class="etiqueta">${esc(t)}<button data-q="${esc(t)}" aria-label="Quitar">×</button></span>`).join("") || `<span class="chico">Todavía no vigilas ninguna palabra.</span>`}</div>
      <div class="fila" style="margin-top:12px"><input type="text" id="aNueva" placeholder="Agregar palabra y presionar Enter" style="max-width:340px"></div>
      <div class="fila" style="margin-top:20px;align-items:center">
        <label class="switch"><input type="checkbox" id="aAuto" ${a.auto ? "checked" : ""}>Revisar solo cada</label>
        <select id="aInt">${[30, 60, 120, 240].map((m) => `<option value="${m}" ${m === a.intervalo ? "selected" : ""}>${m < 60 ? m + " minutos" : m / 60 + (m === 60 ? " hora" : " horas")}</option>`).join("")}</select>
        <button class="btn primario" id="aYa" style="margin-left:auto">Revisar ahora</button></div>
      <p class="chico" id="aUlt">${a.ultimo ? "Última revisión: " + esc(fechaBonita(a.ultimo)) : ""}</p></section>
    <section class="tarjeta"><div class="tarjeta-cab"><h2>Historial</h2></div>
      ${a.historial.length ? `<table><thead><tr><th>Cuándo</th><th>Palabra</th><th>Dónde</th><th class="num">Cambio</th><th>Detalle</th></tr></thead><tbody>
        ${a.historial.map((h) => `<tr class="${h.pico ? "pico" : ""}"><td>${esc(fechaBonita(h.fecha))}</td><td><b>${esc(h.termino)}</b>${h.pico ? " 🔥" : ""}</td><td>${esc(h.fuente)}</td><td class="num">${fpct(h.cambio)}</td><td class="chico">${esc(h.detalle)}</td></tr>`).join("")}</tbody></table>`
        : `<p class="nota">Aquí verás cada revisión. Los picos se marcan en amarillo.</p>`}</section>`;
  $$("[data-q]", c).forEach((b) => (b.onclick = async () => { await api("alertas/quitar", { termino: b.dataset.q }); vistaAlertas(c); }));
  $("#aNueva", c).onkeydown = async (e) => { if (e.key === "Enter" && e.target.value.trim()) { await api("alertas/agregar", { termino: e.target.value.trim() }); vistaAlertas(c); } };
  if ($("#aMer", c)) $("#aMer", c).onclick = async () => { await api("alertas/desde_mercado"); vistaAlertas(c); };
  $("#aAuto", c).onchange = async (e) => { await api("config", { auto_escaneo: e.target.checked, intervalo_min: +$("#aInt").value }); aviso(e.target.checked ? "Vigilancia automática encendida." : "Vigilancia automática apagada."); };
  $("#aInt", c).onchange = async (e) => api("config", { intervalo_min: +e.target.value });
  $("#aYa", c).onclick = async (e) => {
    const b = e.target; b.disabled = true;
    try {
      const { trabajo } = await api("alertas/escanear");
      const r = await esperar(trabajo, (t) => { barra(t.pct); b.textContent = `Revisando… ${t.pct}%`; $("#aUlt").textContent = t.paso; });
      aviso(r.picos ? `${r.picos} pico(s) detectado(s).` : "Sin picos por ahora.", "", "Revisión terminada");
      if (E.vista === "alertas") vistaAlertas(c);
    } catch (err) { aviso(errorAmable(err.message), "error"); b.disabled = false; b.textContent = "Revisar ahora"; }
    finally { barra(null); }
  };
}

async function revisarAvisos() {
  try {
    const { avisos } = await api("avisos");
    for (const a of avisos) for (const p of a.picos) aviso(`${p.fuente}: ${p.detalle} (${fpct(p.cambio)})`, "pico", `🔥 «${p.termino}» se está disparando`);
    if (avisos.length && E.vista !== "alertas") { const g = $("#globoAlertas"); g.hidden = false; g.textContent = avisos.reduce((s, a) => s + a.picos.length, 0); }
  } catch { /* el programa se está cerrando */ }
}

// ------------------------------------------------------------ AJUSTES
const PAISES = [["MX", "México"], ["US", "Estados Unidos"], ["ES", "España"], ["AR", "Argentina"], ["CO", "Colombia"], ["CL", "Chile"], ["PE", "Perú"], ["GT", "Guatemala"], ["", "Todo el mundo"]];

async function vistaAjustes(c) {
  const cl = await api("config/claves");
  const cfg = E.estado.config;
  c.innerHTML = `<h1>Ajustes</h1><p class="sub">Todo se guarda solo en esta computadora.</p>
    <section class="tarjeta"><h2 style="margin-bottom:14px">Región</h2><div class="fila">
      <label class="campo"><span>País</span><select id="jPais">${PAISES.map(([k, t]) => `<option value="${k}" ${k === (cfg.pais || "") ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="campo"><span>Idioma de Google</span><select id="jIdi">${[["es-419", "Español (Latinoamérica)"], ["es", "Español (España)"], ["en-US", "Inglés"]].map(([k, t]) => `<option value="${k}" ${k === cfg.idioma ? "selected" : ""}>${t}</option>`).join("")}</select></label></div></section>
    <section class="tarjeta"><h2>Claves opcionales (gratis)</h2><p class="chico">Sin claves ya funcionan Google, las búsquedas que suben, las preguntas y las noticias. Estas agregan videos y Pinterest.</p>
      <div class="fila" style="margin-top:10px"><label class="campo" style="flex:1"><span>YouTube Data API</span><input type="password" id="jYt" value="${esc(cl.youtube_api_key)}" placeholder="Pega aquí tu clave"></label>
        <a href="#" class="btn fantasma" data-url="https://console.cloud.google.com/apis/library/youtube.googleapis.com">Cómo conseguirla</a></div>
      <p class="chico">En console.cloud.google.com: crea un proyecto → habilita «YouTube Data API v3» → Credenciales → Crear clave de API.</p>
      <div class="fila" style="margin-top:10px"><label class="campo" style="flex:1"><span>Pinterest (token)</span><input type="password" id="jPin" value="${esc(cl.pinterest_token)}" placeholder="Pega aquí tu token"></label>
        <a href="#" class="btn fantasma" data-url="https://developers.pinterest.com/apps/">Cómo conseguirlo</a></div>
      <h3 style="margin-top:22px">Instagram (oficial, con tu cuenta profesional)</h3>
      <p class="chico">Permite ver las publicaciones con más interacción de los hashtags de tu mercado. Necesitas una cuenta profesional de Instagram ligada a una página de Facebook y una app en developers.facebook.com con el permiso de búsqueda de hashtags. Meta permite 30 hashtags distintos por semana.</p>
      <div class="fila"><label class="campo" style="flex:2"><span>Token de acceso</span><input type="password" id="jIgT" value="${esc(cl.instagram_token)}" placeholder="Pega aquí tu token de Meta"></label>
        <label class="campo" style="flex:1"><span>Número de tu cuenta de Instagram</span><input type="text" id="jIgU" value="${esc(cl.instagram_usuario)}" placeholder="Ej. 17841400000000000"></label>
        <button class="btn" id="jIgP">Probar conexión</button>
        <a href="#" class="btn fantasma" data-url="https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-hashtag-search">Cómo conseguirlo</a></div>
      <label class="switch" style="margin-top:14px"><input type="checkbox" id="jVer">Mostrar claves</label></section>
    <section class="tarjeta"><h2 style="margin-bottom:14px">Avisos</h2>
      <div class="campo"><span>¿Qué tanto debe subir algo para avisarte?</span><div class="segmentado" id="jZ">${[[1.5, "Avísame seguido"], [2, "Normal"], [3, "Solo picos fuertes"]].map(([v, t]) => `<button data-z="${v}" class="${+cfg.umbral_z === v ? "activo" : ""}">${t}</button>`).join("")}</div></div>
      <label class="switch" style="margin-top:14px"><input type="checkbox" id="jSon" ${cfg.sonido !== false ? "checked" : ""}>Sonido al detectar un pico</label></section>
    <div class="fila"><button class="btn primario" id="jGuardar">Guardar ajustes</button><button class="btn" id="jCarpeta">Abrir carpeta de datos</button></div>`;
  let z = +cfg.umbral_z || 2;
  $$("#jZ button", c).forEach((b) => (b.onclick = () => { z = +b.dataset.z; $$("#jZ button").forEach((x) => x.classList.toggle("activo", x === b)); }));
  $("#jVer", c).onchange = (e) => { $("#jYt").type = $("#jPin").type = $("#jIgT").type = e.target.checked ? "text" : "password"; };
  $("#jIgP", c).onclick = async () => {
    try { const r = await api("config/probar_instagram", { token: $("#jIgT").value, usuario: $("#jIgU").value }); aviso(r.mensaje, "", "Instagram conectado"); }
    catch (err) { aviso(errorAmable(err.message), "error", "Instagram no respondió"); }
  };
  $("#jCarpeta", c).onclick = () => api("abrir", { url: "carpeta" });
  $("#jGuardar", c).onclick = async () => {
    E.estado = await api("config", { pais: $("#jPais").value, idioma: $("#jIdi").value, youtube_api_key: $("#jYt").value, pinterest_token: $("#jPin").value, instagram_token: $("#jIgT").value, instagram_usuario: $("#jIgU").value.trim(), umbral_z: z, sonido: $("#jSon").checked });
    aviso("Ajustes guardados.");
  };
}

// ------------------------------------------------------------ arranque
(async function iniciar() {
  try {
    await cargarEstado();
    render();
    setInterval(revisarAvisos, 20000);
    programarVivo();
    const { nueva } = await api("actualizacion");
    if (nueva) {
      const a = $("#avisoVersion");
      a.hidden = false;
      a.innerHTML = `Hay una versión nueva (${esc(nueva.version)}).<br><button class="btn" data-url="${esc(nueva.url)}">Descargar</button>`;
      $("button", a).onclick = () => api("abrir", { url: nueva.url });
    }
  } catch (err) {
    $("#contenido").innerHTML = `<div class="tarjeta error-sec">No se pudo iniciar: ${esc(err.message)}</div>`;
  }
})();
