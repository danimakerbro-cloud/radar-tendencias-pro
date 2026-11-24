/* Radar de Tendencias Pro: interfaz */
"use strict";

// ------------------------------------------------------------ utilidades
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const nf = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
const fnum = (v) => (v == null || isNaN(v) ? "—" : nf.format(v));
const fpct = (v) => (v == null ? "" : (v > 0 ? "+" : "") + Math.round(v) + "%");
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const FORMATOS = ["Anuncio de Facebook", "Publicación de Instagram", "Reel o TikTok"];
const TONOS = ["Cercano", "Profesional", "Urgente"];
const MINUTOS_REFRESCO = 15;

function fechaBonita(iso) {
  if (!iso) return "";
  const f = new Date(iso);
  const hora = f.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  if (f.toDateString() === new Date().toDateString()) return `hoy a las ${hora}`;
  return `${f.getDate()} de ${MESES[f.getMonth()]} a las ${hora}`;
}

function errorAmable(msg) {
  const t = String(msg || "");
  if (/limitando|429/.test(t)) return "Google pidió una pausa porque hubo muchas consultas seguidas. Espera unos 5 minutos y vuelve a intentar.";
  if (/conectar|Connection|timed out|Max retries/i.test(t)) return "No hubo respuesta de internet. Revisa tu conexión y vuelve a intentar.";
  return t;
}

// Badge de la red de donde salió cada dato
const CLASE_RED = { Google: "f-google", YouTube: "f-youtube", Pinterest: "f-pinterest", Instagram: "f-instagram",
                    TikTok: "f-tiktok", Facebook: "f-facebook", Noticias: "f-noticias" };
const fuente = (red) => `<span class="fuente ${CLASE_RED[red] || ""}">${esc(red)}</span>`;

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
  setTimeout(() => t.remove(), 6000);
}

async function copiar(texto) {
  try { await navigator.clipboard.writeText(texto); aviso("Copiado: " + texto.slice(0, 80)); }
  catch { aviso("No se pudo copiar"); }
}

// ------------------------------------------------------------ estado de la interfaz
const E = {
  estado: null,
  vista: "inicio",
  pais: "MX",                       // país de «Virales ahora»
  paisIA: "MX",
  paisHashtags: "MX",
  lugar: new Set(["MX", "US", "ES"]),
  filtro: "",
  tema: "",                         // tema que viaja a Copys y a TikTok y Facebook
  formato: FORMATOS[0],
  tono: TONOS[0],
  hashRed: "",
  res: {}, err: {}, prog: {}, corre: {},   // por sección: resultado, error, avance, si está corriendo
  pegado: {},                       // último resumen pegado de TikTok / Facebook
};

const PASOS = {
  virales: [{ hasta: 40, txt: "Tendencias de Google por país" }, { hasta: 70, txt: "Videos virales de YouTube" },
            { hasta: 100, txt: "Ideas que crecen en Pinterest y ordenando" }],
  lugar: [{ hasta: 100, txt: "Tendencias de cada país" }],
  ia: [{ hasta: 60, txt: "Midiendo herramientas de IA en Google" }, { hasta: 74, txt: "Búsquedas y videos de IA" },
       { hasta: 100, txt: "Noticias de IA de hoy" }],
  hashtags: [{ hasta: 30, txt: "Hashtags de lo que pegaste y de YouTube" }, { hasta: 88, txt: "Hashtags de Instagram" },
             { hasta: 100, txt: "Ordenando los más usados" }],
};

function nombrePais(codigo) {
  const p = E.estado && E.estado.paises.find((x) => x.codigo === codigo);
  return p ? p.nombre : codigo;
}

function opcionesPais(sel, conMundo = true) {
  const mundo = conMundo ? `<option value="MUNDO" ${sel === "MUNDO" ? "selected" : ""}>Todo el mundo</option>` : "";
  return mundo + E.estado.paises.map((p) => `<option value="${p.codigo}" ${p.codigo === sel ? "selected" : ""}>${esc(p.nombre)}</option>`).join("");
}

async function cargarEstado() {
  E.estado = await api("estado");
  E.pais = E.estado.pais; E.paisIA = E.estado.pais; E.paisHashtags = E.estado.pais;
  $("#versionTxt").textContent = `Versión ${E.estado.version}`;
}

// Un trabajo en segundo plano: muestra la barra con pasos y guarda el resultado de su sección
async function correr(vista, accion, datos) {
  if (E.corre[vista]) return;
  E.corre[vista] = true; E.err[vista] = null; E.prog[vista] = { pct: 1, paso: "Empezando…" };
  barra(1); pintarZona(vista);
  try {
    const { trabajo } = await api(accion, datos);
    E.res[vista] = await esperar(trabajo, (t) => { E.prog[vista] = t; barra(t.pct); pintarZona(vista); });
  } catch (err) {
    E.err[vista] = errorAmable(err.message);
  } finally {
    E.corre[vista] = false; E.prog[vista] = null; barra(null); pintarZona(vista);
  }
}

function progresoHTML(titulo, t, pasos) {
  const pct = t.pct || 0;
  const actual = pasos.findIndex((p) => pct < p.hasta);
  return `<div class="progreso"><h1>${esc(titulo)}</h1><div class="riel-grande"><span style="width:${pct}%"></span></div>
    <div class="pct"><span>${esc(t.paso || "")}</span><b>${pct}%</b></div>
    <ul class="pasos">${pasos.map((p, i) => {
      const cls = actual < 0 || i < actual ? "hecho" : i === actual ? "ahora" : "";
      return `<li class="${cls}"><span class="marca">${cls === "hecho" ? "✓" : ""}</span>${esc(p.txt)}</li>`;
    }).join("")}</ul></div>`;
}

function avisosHTML(r) {
  const errores = Object.entries(r.errores || {}).map(([k, v]) => `<div class="error-sec"><b>${esc(k)}:</b> ${esc(errorAmable(v))}</div>`).join("");
  const avisos = (r.avisos || []).map((a) => `<div class="aviso-amb">${esc(a)}</div>`).join("");
  return errores + avisos;
}

function vacioHTML(texto) { return `<p class="nota">${esc(texto)}</p>`; }

// Cada resultado pertenece a una sección de la página; «virales» vive en la sección «inicio»
const SECCION = { virales: "inicio", lugar: "lugar", ia: "ia", copys: "copys", hashtags: "hashtags" };

// Pinta solo la zona de resultados (no redibuja la página, para no perder lo que escribiste)
function pintarZona(clave) {
  if (E.vista !== SECCION[clave]) return;
  const z = $("#zona");
  if (!z) return;
  if (E.corre[clave]) {
    z.innerHTML = clave === "copys" ? vacioHTML("Creando copys…")
      : progresoHTML(TITULOS_PROGRESO[clave], E.prog[clave] || {}, PASOS[clave] || []);
    return;
  }
  if (E.err[clave]) { z.innerHTML = `<div class="error-sec">${esc(E.err[clave])}</div>`; return; }
  const r = E.res[clave];
  z.innerHTML = r ? RENDERS[clave](r) : "";
}

const TITULOS_PROGRESO = { virales: "Buscando lo más viral", lugar: "Comparando países", ia: "Midiendo la IA", hashtags: "Buscando hashtags" };

// ------------------------------------------------------------ navegación
function ir(vista) {
  E.vista = vista;
  $$("#menu button").forEach((b) => b.classList.toggle("activo", b.dataset.vista === vista));
  VISTAS[vista]();
}

$$("#menu button").forEach((b) => b.addEventListener("click", () => ir(b.dataset.vista)));

// Un solo manejador para todos los botones de las secciones
$("#contenido").addEventListener("click", (e) => {
  const t = e.target.closest("button, a");
  if (!t) return;
  const d = t.dataset;
  if (d.url) { e.preventDefault(); api("abrir", { url: d.url }); return; }
  if (d.dentro) { e.preventDefault(); api("abrir", { url: d.dentro, dentro: true, titulo: d.tit }); return; }
  if (d.cop !== undefined) { copiar(d.cop); return; }
  if (d.copyTema !== undefined) { E.tema = d.copyTema; ir("copys"); return; }
  if (d.pegar) { pegar(d.pegar); return; }
  if (d.borrarPegado) { borrarPegado(d.borrarPegado); return; }
  if (d.grupo) {
    E[d.grupo] = d.v;
    $$(`[data-grupo="${d.grupo}"]`).forEach((b) => b.classList.toggle("activo", b === t));
    if (d.grupo === "hashRed") pintarZona("hashtags");
  }
});

// Refresco automático de «Virales ahora» mientras esa pantalla esté abierta
setInterval(() => {
  if (E.vista === "inicio" && E.estado && !E.corre.virales) {
    correr("virales", "virales", { pais: E.pais, filtro: E.filtro });
  }
}, MINUTOS_REFRESCO * 60 * 1000);

// ------------------------------------------------------------ 1) VIRALES AHORA
function vInicio() {
  $("#contenido").innerHTML = `
    <h1>Lo más viral ahora</h1>
    <p class="sub">Lo que la gente está buscando y viendo en este momento. Se actualiza sola cada ${MINUTOS_REFRESCO} minutos mientras tengas esta pantalla abierta.</p>
    <div class="fila" style="margin-bottom:8px">
      <label class="campo"><span>País</span><select id="pais">${opcionesPais(E.pais)}</select></label>
      <label class="campo" style="flex:1;min-width:220px"><span>Filtrar por palabra (opcional)</span>
        <input type="text" id="filtro" value="${esc(E.filtro)}" placeholder="Ej. vals, IA, cocina"></label>
      <button class="btn primario" id="bActualizar">Actualizar ahora</button>
    </div>
    <p class="chico" id="cuando"></p>
    <div id="zona" style="margin-top:14px"></div>`;
  const actualizar = () => {
    E.pais = $("#pais").value;
    E.filtro = $("#filtro").value.trim();
    correr("virales", "virales", { pais: E.pais, filtro: E.filtro });
  };
  $("#bActualizar").onclick = actualizar;
  $("#pais").onchange = actualizar;
  $("#filtro").onkeydown = (e) => { if (e.key === "Enter") actualizar(); };
  if (E.res.virales) $("#cuando").textContent = `Actualizado ${fechaBonita(E.res.virales.fecha)}`;
  if (!E.res.virales && !E.corre.virales && !E.err.virales) actualizar();
  pintarZona("virales");
}

function renderVirales(r) {
  const temas = r.temas || [];
  $("#cuando") && ($("#cuando").textContent = `Actualizado ${fechaBonita(r.fecha)}`);
  const videos = r.videos || [];
  return `${avisosHTML(r)}
    <div class="cifras">
      <div class="cifra"><b>${temas.length}</b><span>temas que se buscan</span></div>
      <div class="cifra"><b>${videos.length}</b><span>videos virales</span></div>
      <div class="cifra"><b>${r.paises.length}</b><span>${r.paises.length === 1 ? "país" : "países"}</span></div>
    </div>
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Lo que más se busca ${fuente("Google")}</h2>
        <p>Primero sale lo que aparece en más países, y después lo que tiene más búsquedas.</p></div></div>
      ${temas.length ? `<ul class="lista">${temas.map((t) => `<li>
          <div class="txt"><b>${esc(t.tema)}</b><small>${esc(t.busquedas || "")} búsquedas${t.noticia ? ` · ${esc(t.medio || "")}: ${esc(t.noticia)}` : ""}</small></div>
          <span class="chips-texto">${t.paises.map((p) => `<span class="chip pais">${esc(nombrePais(p))}</span>`).join("")}</span>
          <span class="acc"><button class="btn fantasma" data-copy-tema="${esc(t.tema)}">Crear copy</button>
          ${t.url ? `<button class="btn fantasma" data-url="${esc(t.url)}">Ver noticia</button>` : ""}</span></li>`).join("")}</ul>`
        : vacioHTML("No hay temas con ese filtro. Prueba con otra palabra o quita el filtro.")}
    </section>
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Videos que están explotando ${fuente("YouTube")}</h2>
        <p>Ordenados por vistas por hora en los últimos días.</p></div></div>
      ${videos.length ? `<ul class="lista">${videos.slice(0, 25).map((v) => `<li>
          <div class="txt"><a href="#" data-url="${esc(v.url)}">${esc(v.titulo)}</a><small>${esc(v.canal)} · ${fnum(v.vistas)} vistas</small></div>
          <span class="chip pais">${esc(nombrePais(v.pais))}</span><span class="chip fuerte">${fnum(v.vistas_hora)} vistas por hora</span></li>`).join("")}</ul>`
        : vacioHTML(E.estado.claves.youtube ? "No hubo videos con ese filtro." : "Agrega tu clave gratuita de YouTube en Ajustes para ver los videos que están explotando.")}
    </section>
    ${(r.pinterest || []).length ? `<section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Ideas que crecen ${fuente("Pinterest")}</h2><p>Lo que empieza a crecer antes de volverse masivo.</p></div></div>
      <ul class="lista">${r.pinterest.map((x) => `<li><div class="txt"><b>${esc(x.palabra)}</b></div>
        ${x.semana != null ? `<span class="chip sube">${fpct(x.semana)} esta semana</span>` : ""}</li>`).join("")}</ul></section>` : ""}`;
}

// ------------------------------------------------------------ 2) POR LUGAR
function vLugar() {
  $("#contenido").innerHTML = `
    <h1>Por lugar</h1>
    <p class="sub">Elige uno o varios países, o todo el mundo, y mira qué se busca en cada uno. Lo que aparece en varios países a la vez sale primero.</p>
    <div class="campo"><span>Países</span>
      <div class="marcas" id="marcasLugar">${E.estado.paises.map((p) =>
        `<label><input type="checkbox" value="${p.codigo}" ${E.lugar.has(p.codigo) ? "checked" : ""}>${esc(p.nombre)}</label>`).join("")}</div></div>
    <div class="fila" style="margin-top:14px">
      <button class="btn" id="bMundo">Todo el mundo</button>
      <button class="btn primario" id="bComparar">Comparar</button>
    </div>
    <div id="zona" style="margin-top:18px"></div>`;
  $("#bMundo").onclick = () => { E.lugar = new Set(E.estado.paises.map((p) => p.codigo)); vLugar(); compararLugar(); };
  $("#bComparar").onclick = compararLugar;
  $$("#marcasLugar input").forEach((c) => c.onchange = () => {
    c.checked ? E.lugar.add(c.value) : E.lugar.delete(c.value);
  });
  pintarZona("lugar");
}

function compararLugar() {
  const sel = [...E.lugar];
  if (!sel.length) { aviso("Elige al menos un país.", "error"); return; }
  correr("lugar", "por_lugar", { paises: sel });
}

function renderLugar(r) {
  const paises = Object.entries(r.por_pais || {});
  return `${avisosHTML(r)}
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Se repite entre países</h2>
        <p>Temas que están en las listas de dos o más países al mismo tiempo.</p></div></div>
      ${(r.repetidos || []).length ? `<ul class="lista">${r.repetidos.map((f) => `<li>
          <div class="txt"><b>${esc(f.tema)}</b><small>Aparece en ${f.paises.length} ${f.paises.length === 1 ? "país" : "países"}</small></div>
          <span class="chips-texto">${f.paises.map((p) => `<span class="chip pais">${esc(nombrePais(p))}</span>`).join("")}</span></li>`).join("")}</ul>`
        : vacioHTML("Por ahora ningún tema se repite entre los países que elegiste.")}
    </section>
    <div class="malla-paises">${paises.map(([codigo, p]) => `<section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>${esc(p.nombre)} ${fuente("Google")}</h2></div></div>
      ${p.temas.length ? `<ul class="lista">${p.temas.map((t) => `<li><div class="txt">
        ${t.url ? `<a href="#" data-url="${esc(t.url)}">${esc(t.tema)}</a>` : `<b>${esc(t.tema)}</b>`}
        <small>${esc(t.busquedas || "")} búsquedas</small></div>
        <button class="btn fantasma" data-copy-tema="${esc(t.tema)}">Copy</button></li>`).join("")}</ul>`
        : vacioHTML("Sin temas hoy.")}</section>`).join("")}</div>`;
}

// ------------------------------------------------------------ 3) TENDENCIAS DE IA
function vIA() {
  $("#contenido").innerHTML = `
    <h1>Tendencias de IA</h1>
    <p class="sub">Qué herramientas de inteligencia artificial, búsquedas, videos y noticias están subiendo en el país que elijas.</p>
    <div class="fila">
      <label class="campo"><span>País</span><select id="paisIA">${opcionesPais(E.paisIA, false)}</select></label>
      <button class="btn primario" id="bIA">Medir tendencias de IA</button>
    </div>
    <div id="zona" style="margin-top:18px"></div>`;
  const medir = () => { E.paisIA = $("#paisIA").value; correr("ia", "ia", { pais: E.paisIA }); };
  $("#bIA").onclick = medir;
  $("#paisIA").onchange = medir;
  pintarZona("ia");
}

function renderIA(r) {
  const clase = (v) => /Explotando|fuerte|^Sube$/.test(v || "") ? "fuerte" : /Baja/.test(v || "") ? "baja" : "";
  return `${avisosHTML(r)}
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Herramientas de IA ${fuente("Google")}</h2>
        <p>Cómo va cada herramienta en los últimos tres meses, comparada consigo misma.</p></div></div>
      ${(r.terminos || []).length ? `<ul class="lista">${r.terminos.map((t) => `<li>
          <div class="txt"><b>${esc(t.palabra)}</b>${t.error ? `<small>${esc(errorAmable(t.error))}</small>` : ""}</div>
          <span class="chip ${clase(t.veredicto)}">${esc(t.veredicto)}</span>
          <span class="chip">${esc(fpct(t.cambio) || "—")}</span>
          <button class="btn fantasma" data-copy-tema="${esc(t.palabra)}">Crear copy</button></li>`).join("")}</ul>`
        : vacioHTML("Google no devolvió datos de IA en este momento.")}
    </section>
    <div class="dos-col">
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Búsquedas de IA que suben ${fuente("Google")}</h2></div></div>
        ${(r.subiendo || []).length ? `<ul class="lista">${r.subiendo.map((x) => `<li><div class="txt"><b>${esc(x.busqueda)}</b></div>
          <span class="chip fuerte">${esc(String(x.crecimiento))}</span></li>`).join("")}</ul>` : vacioHTML("Sin búsquedas que suban por ahora.")}
      </section>
      <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Noticias de IA de hoy ${fuente("Noticias")}</h2></div></div>
        ${(r.noticias || []).length ? `<ul class="lista">${r.noticias.map((n) => `<li><div class="txt">
          <a href="#" data-url="${esc(n.url)}">${esc(n.titulo)}</a><small>${esc(n.medio || "")} · ${esc(fechaBonita(n.fecha))}</small></div></li>`).join("")}</ul>`
          : vacioHTML("Sin noticias de IA en los últimos días.")}
      </section>
    </div>
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Videos de IA más vistos ${fuente("YouTube")}</h2></div></div>
      ${(r.videos || []).length ? `<ul class="lista">${r.videos.map((v) => `<li><div class="txt">
        <a href="#" data-url="${esc(v.url)}">${esc(v.titulo)}</a><small>${esc(v.canal)} · ${fnum(v.vistas)} vistas</small></div>
        <span class="chip fuerte">${fnum(v.vistas_hora)} vistas por hora</span></li>`).join("")}</ul>`
        : vacioHTML(E.estado.claves.youtube ? "No hubo videos de IA recientes." : "Agrega tu clave gratuita de YouTube en Ajustes para ver los videos de IA más vistos.")}
    </section>`;
}

// ------------------------------------------------------------ 4) COPYS E IDEAS
function vCopys() {
  const sugerencias = [...new Set([
    ...((E.res.virales && E.res.virales.temas) || []).map((t) => t.tema),
    ...((E.res.ia && E.res.ia.subiendo) || []).map((x) => x.busqueda)])].slice(0, 20);
  $("#contenido").innerHTML = `
    <h1>Copys e ideas</h1>
    <p class="sub">Textos para publicidad y contenido a partir de una tendencia. Son plantillas que llenan la tendencia con frases listas para editar: cámbiales las palabras para que suenen a tu marca.</p>
    <section class="tarjeta">
      <label class="campo"><span>Tendencia</span>
        <input type="text" id="cTema" list="temasSug" value="${esc(E.tema)}" placeholder="Ej. vals de xv años">
        <datalist id="temasSug">${sugerencias.map((s) => `<option value="${esc(s)}">`).join("")}</datalist></label>
      <div class="fila" style="margin-top:16px">
        <div class="campo"><span>Formato</span><div class="segmentado">${FORMATOS.map((f) =>
          `<button data-grupo="formato" data-v="${esc(f)}" class="${f === E.formato ? "activo" : ""}">${esc(f)}</button>`).join("")}</div></div>
        <div class="campo"><span>Tono</span><div class="segmentado">${TONOS.map((t) =>
          `<button data-grupo="tono" data-v="${esc(t)}" class="${t === E.tono ? "activo" : ""}">${esc(t)}</button>`).join("")}</div></div>
      </div>
      <label class="campo" style="margin-top:16px"><span>Hashtags (opcional)</span>
        <input type="text" id="cHash" value="${esc(E.hashCopy || "")}" placeholder="#xvaños #vals"></label>
      <div style="margin-top:16px"><button class="btn primario grande" id="bCopys">Crear copys</button></div>
    </section>
    <div id="zona"></div>`;
  $("#bCopys").onclick = crearCopys;
  pintarZona("copys");
}

async function crearCopys() {
  const tema = $("#cTema").value.trim();
  E.tema = tema; E.hashCopy = $("#cHash").value;
  if (!tema) { aviso("Escribe una tendencia para crear los copys.", "error"); return; }
  const hashtags = E.hashCopy.split(/\s+/).filter(Boolean);
  E.corre.copys = true; pintarZona("copys");
  try {
    const { copys } = await api("copys", { tema, formato: E.formato, tono: E.tono, hashtags });
    E.res.copys = copys; E.err.copys = null;
  } catch (err) { E.err.copys = err.message; E.res.copys = null; }
  finally { E.corre.copys = false; pintarZona("copys"); }
}

function renderCopys(c) {
  return `<h2 style="margin:6px 0 12px">Copys para «${esc(c.tema)}» · ${esc(c.formato)} · ${esc(c.tono)}</h2>
    ${c.variantes.map((v, i) => `<div class="copy"><div class="gancho">Opción ${i + 1}: ${esc(v.gancho)}</div>
      <p>${esc(v.texto)}</p><button class="btn" data-cop="${esc(v.texto)}">Copiar texto</button></div>`).join("")}
    ${c.guion.length ? `<section class="tarjeta"><div class="tarjeta-cab"><div><h2>Guion del video</h2></div></div>
      <ol class="guion">${c.guion.map((g) => `<li>${esc(g)}</li>`).join("")}</ol></section>` : ""}
    <section class="tarjeta"><div class="tarjeta-cab"><div><h2>Hashtags sugeridos</h2></div>
      <button class="btn" data-cop="${esc(c.hashtags)}">Copiar hashtags</button></div>
      <p>${esc(c.hashtags)}</p></section>`;
}

// ------------------------------------------------------------ 5) HASHTAGS
function vHashtags() {
  const temas = (E.res.virales && E.res.virales.temas) || [];
  $("#contenido").innerHTML = `
    <h1>Hashtags en tendencia</h1>
    <p class="sub">Los hashtags que más se repiten en YouTube, Instagram, TikTok y Facebook. Para TikTok y Facebook, primero pega lo que copies en la sección «TikTok y Facebook».</p>
    <div class="fila">
      <label class="campo"><span>País</span><select id="paisH">${opcionesPais(E.paisHashtags, false)}</select></label>
      <button class="btn primario" id="bHash">Buscar hashtags</button>
    </div>
    ${temas.length ? "" : `<p class="nota" style="margin-top:14px">Para incluir Instagram, primero abre «Virales ahora»: usa los temas que aparecen ahí.</p>`}
    <div id="zona" style="margin-top:18px"></div>`;
  const buscar = () => {
    E.paisHashtags = $("#paisH").value;
    const top = ((E.res.virales && E.res.virales.temas) || []).slice(0, 3).map((t) => t.tema);
    correr("hashtags", "hashtags", { pais: E.paisHashtags, temas: top });
  };
  $("#bHash").onclick = buscar;
  $("#paisH").onchange = buscar;
  pintarZona("hashtags");
}

function renderHashtags(r) {
  const redes = r.redes || [];
  if (!E.hashRed || !redes.includes(E.hashRed)) E.hashRed = redes[0] || "";
  const lista = (r.por_red || {})[E.hashRed] || [];
  return `${avisosHTML(r)}
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Los más usados</h2><p>Juntando todas las redes que encontré.</p></div>
        ${(r.mejores || []).length ? `<button class="btn" data-cop="${esc(r.mejores.slice(0, 15).map((h) => "#" + h.hashtag).join(" "))}">Copiar los 15 primeros</button>` : ""}</div>
      ${(r.mejores || []).length ? `<div class="hashtags">${r.mejores.map((h) => `<span>#${esc(h.hashtag)} <small>×${h.veces}</small></span>`).join("")}</div>
        <p class="chico" style="margin-top:12px">Salen de: ${h2fuentes(r.mejores)}</p>`
        : vacioHTML("Todavía no hay hashtags. Busca en Virales ahora, o pega lo que copies de TikTok y Facebook.")}
    </section>
    ${redes.length ? `<section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Por red</h2></div>
        <div class="segmentado">${redes.map((x) => `<button data-grupo="hashRed" data-v="${esc(x)}" class="${x === E.hashRed ? "activo" : ""}">${esc(x)}</button>`).join("")}</div></div>
      ${lista.length ? `<div class="hashtags">${lista.map((h) => `<span>#${esc(h.hashtag)} <small>×${h.veces}</small></span>`).join("")}</div>`
        : vacioHTML("Sin hashtags de esta red.")}
    </section>` : ""}`;
}

function h2fuentes(lista) {
  const redes = [...new Set(lista.flatMap((h) => h.fuentes))];
  return redes.map(fuente).join(" ");
}

// ------------------------------------------------------------ 6) TIKTOK Y FACEBOOK
const RED_TEXTO = { tiktok: "TikTok", facebook: "Facebook" };

function enlacesRed(red, termino) {
  const q = encodeURIComponent(termino), pais = E.estado.pais === "MUNDO" ? "MX" : E.estado.pais;
  const tag = termino.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");     // «vals de xv años» -> «valsdexvaños»
  const tagUrl = encodeURIComponent(tag);
  if (red === "tiktok") return [
    [`Hashtags en tendencia en TikTok (${nombrePais(pais)})`, `https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/es?countryCode=${pais}&period=7`],
    [`Ver #${tag} en TikTok`, `https://www.tiktok.com/tag/${tagUrl}`],
    [`Buscar «${termino}» en TikTok`, `https://www.tiktok.com/search?q=${q}`]];
  return [
    [`Anuncios activos de «${termino}» (Biblioteca de anuncios)`, `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=${pais}&q=${q}&search_type=keyword_unordered`],
    [`Buscar «${termino}» en Facebook`, `https://www.facebook.com/search/top?q=${q}`]];
}

function vTikTokFb() {
  $("#contenido").innerHTML = `
    <h1>TikTok y Facebook</h1>
    <p class="sub">Estas redes no comparten sus tendencias con programas como este. Por eso las abres aquí, copias la página y el programa la analiza: hashtags, temas, quién se anuncia, precios y ofertas.</p>
    <label class="campo" style="max-width:520px;margin-bottom:18px"><span>Tema que quieres buscar</span>
      <input type="text" id="tTema" value="${esc(E.tema)}" placeholder="Ej. vals de xv años"></label>
    <div class="redes-grid" id="zona">${tarjetaRed("tiktok")}${tarjetaRed("facebook")}</div>`;
  $("#tTema").onchange = () => { E.tema = $("#tTema").value.trim(); vTikTokFb(); };
  ["tiktok", "facebook"].forEach(async (red) => {
    if (E.pegado[red] || !E.estado.pegados[red]) return;
    try { E.pegado[red] = (await api("pegados/ver", { red })).pegado; repintarRed(red); } catch { /* no hay nada pegado */ }
  });
}

function tarjetaRed(red) {
  const t = E.tema || "tu tema";
  return `<section class="red-card c-${red}" data-red="${red}"><h2>${fuente(RED_TEXTO[red])} ${RED_TEXTO[red]}</h2>
    <p class="que">${red === "tiktok" ? "Lo que más pega en el hashtag de tu tema y los hashtags en tendencia del país." : "Los anuncios que está pagando tu competencia: precios, ofertas y cómo lo dicen."}</p>
    <ol class="pasos-pegar">
      <li>Abre la página aquí abajo. Se abre dentro del programa; la primera vez inicia sesión si te la pide.</li>
      <li>En esa ventana presiona <kbd>Ctrl</kbd>+<kbd>A</kbd> y luego <kbd>Ctrl</kbd>+<kbd>C</kbd>. Si bajas un poco antes, se copian más resultados.</li>
      <li>Pega aquí con <kbd>Ctrl</kbd>+<kbd>V</kbd> y presiona «Analizar lo que pegué».</li></ol>
    <div class="enlaces-red">${enlacesRed(red, t).map(([txt, url]) => `<a href="#" data-dentro="${esc(url)}" data-tit="${esc(txt)}">${esc(txt)}</a>`).join("")}</div>
    <textarea class="pegar" id="t_${red}" placeholder="Pega aquí lo que copiaste de ${RED_TEXTO[red]}…" style="margin-top:14px"></textarea>
    <div class="fila" style="margin-top:8px">
      <button class="btn primario" data-pegar="${red}" id="b_${red}">Analizar lo que pegué</button>
      ${E.pegado[red] ? `<button class="btn fantasma peligro" data-borrar-pegado="${red}">Borrar lo pegado</button>` : ""}
    </div>
    <div id="r_${red}">${E.pegado[red] ? resumenPegado(E.pegado[red]) : ""}</div></section>`;
}

// Vuelve a pintar solo la tarjeta de una red (no toca lo que estés escribiendo en la otra)
function repintarRed(red) {
  const actual = $(`.red-card[data-red="${red}"]`);
  if (!actual) return;
  actual.outerHTML = tarjetaRed(red);
}

function resumenPegado(p) {
  return `<div style="margin-top:16px"><p class="chico">${fuente(p.red)} Analizado ${esc(fechaBonita(p.fecha))} · ${fnum(p.lineas)} renglones</p>
    ${p.anunciantes.length ? `<h3 style="margin:12px 0 6px">Quién se anuncia</h3><ul class="lista">${p.anunciantes.map((a) =>
      `<li><div class="txt"><b>${esc(a.nombre)}</b></div><span class="chip">${a.anuncios} anuncio${a.anuncios === 1 ? "" : "s"}</span></li>`).join("")}</ul>` : ""}
    ${p.precios.length ? `<h3 style="margin:12px 0 6px">Precios que mencionan</h3><div class="chips-texto">${p.precios.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
    ${p.ofertas.length ? `<h3 style="margin:12px 0 6px">Ofertas y ganchos</h3><ul class="lista">${p.ofertas.map((o) =>
      `<li><div class="txt">${esc(o)}</div><span class="acc"><button class="btn fantasma" data-cop="${esc(o)}">Copiar</button></span></li>`).join("")}</ul>` : ""}
    ${p.hashtags.length ? `<h3 style="margin:12px 0 6px">Hashtags</h3><div class="hashtags">${p.hashtags.map((h) => `<span>#${esc(h.hashtag)} <small>×${h.veces}</small></span>`).join("")}</div>` : ""}
    ${p.temas.length ? `<h3 style="margin:12px 0 6px">Temas que más se repiten</h3><div class="chips-texto">${p.temas.map((t) => `<span>${esc(t.tema)} ×${t.veces}</span>`).join("")}</div>` : ""}
  </div>`;
}

async function pegar(red) {
  const texto = $("#t_" + red).value;
  const boton = $("#b_" + red);
  boton.disabled = true; boton.textContent = "Analizando…";
  try {
    const { pegado } = await api("pegar", { red, texto });
    E.pegado[red] = pegado;
    E.estado = await api("estado");
    repintarRed(red);
    aviso(`Listo: ${pegado.hashtags.length} hashtags y ${pegado.temas.length} temas. Ya salen en Hashtags.`, "", `${RED_TEXTO[red]} analizado`);
  } catch (err) {
    aviso(err.message, "error");
    boton.disabled = false; boton.textContent = "Analizar lo que pegué";
  }
}

async function borrarPegado(red) {
  await api("pegados/borrar", { red });
  delete E.pegado[red];
  E.estado = await api("estado");
  repintarRed(red);
  aviso(`Se borró lo pegado de ${RED_TEXTO[red]}.`);
}

// ------------------------------------------------------------ 7) AJUSTES
function vAjustes() {
  $("#contenido").innerHTML = `
    <h1>Ajustes</h1>
    <p class="sub">Todo es gratis. Las claves se guardan solo en tu computadora.</p>
    <section class="tarjeta">
      <div class="fila">
        <label class="campo"><span>País que se muestra al abrir</span><select id="aPais">${opcionesPais(E.estado.pais, false)}</select></label>
      </div>
    </section>
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>YouTube ${E.estado.claves.youtube ? fuente("YouTube") : ""}</h2>
        <p>Para ver videos virales y hashtags. Clave gratuita de YouTube Data API v3.</p></div></div>
      <label class="campo"><span>Clave de API</span><input type="password" id="aYT" autocomplete="off"></label>
    </section>
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Pinterest ${E.estado.claves.pinterest ? fuente("Pinterest") : ""}</h2>
        <p>Ideas que crecen. Token gratuito de lectura de Pinterest.</p></div></div>
      <label class="campo"><span>Token</span><input type="password" id="aPin" autocomplete="off"></label>
    </section>
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>Instagram ${E.estado.claves.instagram ? fuente("Instagram") : ""}</h2>
        <p>Hashtags de Instagram. Necesitas una cuenta profesional de Instagram ligada a una página de Facebook.</p></div>
        <button class="btn" id="bProbarIG">Probar conexión</button></div>
      <div class="fila">
        <label class="campo" style="flex:1"><span>Token de acceso</span><input type="password" id="aIG" autocomplete="off"></label>
        <label class="campo"><span>Número de la cuenta</span><input type="text" id="aIGU"></label>
      </div>
    </section>
    <button class="btn primario grande" id="bGuardar">Guardar ajustes</button>`;
  api("config/claves").then((c) => {
    $("#aYT").value = c.youtube_api_key; $("#aPin").value = c.pinterest_token;
    $("#aIG").value = c.instagram_token; $("#aIGU").value = c.instagram_usuario;
  }).catch(() => {});
  $("#bGuardar").onclick = async () => {
    try {
      E.estado = await api("config", {
        pais: $("#aPais").value, youtube_api_key: $("#aYT").value, pinterest_token: $("#aPin").value,
        instagram_token: $("#aIG").value, instagram_usuario: $("#aIGU").value });
      E.pais = E.estado.pais; E.paisIA = E.estado.pais; E.paisHashtags = E.estado.pais;
      aviso("Ajustes guardados.", "", "Listo");
      vAjustes();
    } catch (err) { aviso(err.message, "error"); }
  };
  $("#bProbarIG").onclick = async () => {
    try { await api("config", { instagram_token: $("#aIG").value, instagram_usuario: $("#aIGU").value });
      const r = await api("config/probar_instagram"); aviso(`Conectado: encontré ${r.publicaciones} publicaciones de prueba.`, "", "Instagram");
    } catch (err) { aviso(err.message, "error", "Instagram"); }
  };
}

// ------------------------------------------------------------ mapa de vistas
const VISTAS = {
  inicio: vInicio, lugar: vLugar, ia: vIA, copys: vCopys, hashtags: vHashtags, tiktokfb: vTikTokFb, ajustes: vAjustes,
};
const RENDERS = { virales: renderVirales, lugar: renderLugar, ia: renderIA, copys: renderCopys, hashtags: renderHashtags };

// ------------------------------------------------------------ arranque
(async function arrancar() {
  try {
    await cargarEstado();
    const { nueva } = await api("actualizacion");
    if (nueva) {
      const a = $("#avisoVersion");
      a.hidden = false;
      a.innerHTML = `Hay una versión nueva (${esc(nueva.version)}).<br><button class="btn" id="bDescargar">Descargar</button>`;
      $("#bDescargar").onclick = () => api("abrir", { url: nueva.url });
    }
  } catch (err) {
    aviso(errorAmable(err.message), "error", "No se pudo abrir el programa");
  }
  ir("inicio");
})();
