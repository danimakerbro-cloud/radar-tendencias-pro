# -*- coding: utf-8 -*-
"""
Radar de Tendencias Pro — programa de escritorio para Windows.

Pestañas:
  1. Búsquedas (Google Trends + búsquedas que suben + ideas de palabras clave)
  2. Tendencias del día (Google "Trending now" + Pinterest Trends)
  3. Redes y menciones (YouTube + Google Noticias)
  4. Mis datos (ventas, Google Analytics o cualquier CSV/Excel con fechas)
  5. Alertas (lista de vigilancia que avisa cuando algo se dispara)
  6. Configuración (país, claves de API, alertas)
"""
from __future__ import annotations

import datetime as dt
import os
import queue
import statistics
import sys
import threading
import traceback
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

import matplotlib

matplotlib.use("TkAgg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import motor as m  # noqa: E402

try:
    import winsound  # solo existe en Windows
except ImportError:  # pragma: no cover
    winsound = None

COLORES = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed"]
FONDO = "#f4f5f9"
OSCURO = "#111827"
ACENTO = "#2563eb"
GRIS = "#6b7280"
AMARILLO = "#fde68a"
SIN_MERCADO = "Sin filtro (todos los temas)"

PAISES = {
    "MX – México": "MX", "US – Estados Unidos": "US", "ES – España": "ES", "AR – Argentina": "AR",
    "CO – Colombia": "CO", "CL – Chile": "CL", "PE – Perú": "PE", "GT – Guatemala": "GT",
    "BR – Brasil": "BR", "CA – Canadá": "CA", "Mundial (todos)": "",
}
INTERESES_PINTEREST = {
    "(todos)": "", "Comida y bebida": "food_and_drinks", "Decoración del hogar": "home_decor",
    "Moda mujer": "womens_fashion", "Moda hombre": "mens_fashion", "Belleza": "beauty",
    "Bodas": "wedding", "Planeación de eventos": "event_planning", "Viajes": "travel",
    "Entretenimiento": "entertainment", "Arte": "art", "Diseño": "design",
    "Manualidades (DIY)": "diy_and_crafts", "Electrónica": "electronics", "Salud": "health",
    "Deporte": "sport", "Educación": "education", "Finanzas": "finance", "Jardinería": "gardening",
    "Crianza": "parenting", "Mascotas/animales": "animals", "Vehículos": "vehicles",
}


def ruta_recurso(nombre: str) -> str:
    """Ruta de un archivo incluido, tanto en el .py como dentro del .exe de PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nombre)


def registrar_error(texto: str) -> str:
    os.makedirs(m.APP_DIR, exist_ok=True)
    ruta = os.path.join(m.APP_DIR, "errores.log")
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(f"\n[{dt.datetime.now():%Y-%m-%d %H:%M:%S}]\n{texto}\n")
    return ruta


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------
def fnum(v, dec=0) -> str:
    if v is None:
        return "—"
    return f"{v:,.{dec}f}"


def fpct(v) -> str:
    if v is None:
        return "—"
    if v == float("inf"):
        return "Nuevo"
    return f"{v:+.1f}%"


def formatear_eje_fechas(ax, fechas, fmt=None):
    if not fechas:
        return
    if fmt:
        ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=12))
        return
    dias = (max(fechas) - min(fechas)).total_seconds() / 86400 if isinstance(fechas[0], dt.datetime) \
        else (max(fechas) - min(fechas)).days
    if dias <= 2:
        fmt = "%H:%M"
    elif dias <= 10:
        fmt = "%d/%m %Hh" if isinstance(fechas[0], dt.datetime) else "%d/%m"
    elif dias <= 400:
        fmt = "%d/%m"
    else:
        fmt = "%m/%Y"
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))


# ---------------------------------------------------------------------------
# Componentes reutilizables
# ---------------------------------------------------------------------------
class Tabla(ttk.Frame):
    """Tabla con ordenar por columna, exportar a CSV y doble clic para abrir enlaces."""

    def __init__(self, padre, columnas, anchos=None, nombre="datos", al_doble_clic=None, al_seleccionar=None):
        super().__init__(padre)
        self.columnas, self.nombre = columnas, nombre
        self.al_doble_clic, self.al_seleccionar = al_doble_clic, al_seleccionar
        self.filas, self.urls, self.indices = [], {}, {}

        barra = ttk.Frame(self)
        barra.pack(fill="x", pady=(0, 4))
        self.lbl = ttk.Label(barra, text="Sin datos todavía", style="Sub.TLabel")
        self.lbl.pack(side="left")
        ttk.Button(barra, text="Exportar a CSV", command=self.exportar).pack(side="right")

        cont = ttk.Frame(self)
        cont.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(cont, columns=columnas, show="headings", selectmode="browse")
        for i, c in enumerate(columnas):
            self.tree.heading(c, text=c, command=lambda c=c: self.ordenar(c, True))
            self.tree.column(c, width=(anchos[i] if anchos else 120), anchor="w", stretch=True)
        sy = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(cont, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)
        self.tree.tag_configure("pico", background=AMARILLO)
        self.tree.tag_configure("par", background="#f9fafb")
        self.tree.bind("<Double-1>", self._doble)
        self.tree.bind("<<TreeviewSelect>>", self._sel)

    def cargar(self, filas, urls=None, picos=None, nota=None):
        self.tree.delete(*self.tree.get_children())
        self.filas, self.urls, self.indices = filas, {}, {}
        for i, f in enumerate(filas):
            tags = ("pico",) if picos and picos[i] else (("par",) if i % 2 else ())
            iid = self.tree.insert("", "end", values=f, tags=tags)
            self.indices[iid] = i
            if urls and urls[i]:
                self.urls[iid] = urls[i]
        if nota is None:
            nota = f"{len(filas)} resultados"
            if self.urls:
                nota += "  ·  doble clic para abrir"
            elif self.al_doble_clic:
                nota += "  ·  doble clic para analizar"
        self.lbl.config(text=nota)

    def ordenar(self, col, desc):
        def clave(k):
            v = self.tree.set(k, col)
            limpio = v.replace(",", "").replace("%", "").replace("+", "").replace("$", "").strip()
            try:
                return (0, float(limpio))
            except ValueError:
                return (1, v.lower())
        orden = sorted(self.tree.get_children(""), key=clave, reverse=desc)
        for i, k in enumerate(orden):
            self.tree.move(k, "", i)
        self.tree.heading(col, command=lambda: self.ordenar(col, not desc))

    def _doble(self, _e):
        sel = self.tree.focus()
        if not sel:
            return
        if sel in self.urls:
            webbrowser.open(self.urls[sel])
        elif self.al_doble_clic:
            self.al_doble_clic(self.tree.item(sel, "values"))

    def _sel(self, _e):
        sel = self.tree.focus()
        if sel and self.al_seleccionar:
            self.al_seleccionar(self.indices.get(sel))

    def exportar(self):
        if not self.filas:
            messagebox.showinfo(m.APP_NOMBRE, "No hay datos para exportar todavía.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV para Excel", "*.csv")],
                                            initialfile=f"{self.nombre}_{dt.date.today()}.csv")
        if ruta:
            m.exportar_csv(ruta, self.columnas, self.filas)
            messagebox.showinfo(m.APP_NOMBRE, f"Guardado en:\n{ruta}")


class Grafica(ttk.Frame):
    """Gráfica de matplotlib con barra de zoom y botón para exportar los datos graficados."""

    def __init__(self, padre, alto=4.2, nombre="grafica"):
        super().__init__(padre)
        self.nombre = nombre
        self.datos = ([], [])
        self.fig = Figure(figsize=(7, alto), dpi=100, facecolor="white")
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        abajo = ttk.Frame(self)
        abajo.pack(side="bottom", fill="x")
        barra = NavigationToolbar2Tk(self.canvas, abajo, pack_toolbar=False)
        barra.update()
        barra.pack(side="left")
        ttk.Button(abajo, text="Exportar datos", command=self.exportar).pack(side="right", padx=4)
        ttk.Button(abajo, text="Guardar imagen", command=self.guardar_imagen).pack(side="right")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.vacia("Aquí aparecerá la gráfica")

    def _limpiar_ejes_extra(self):
        for eje in self.fig.axes[1:]:      # p. ej. el segundo eje de una categoría graficada antes
            eje.remove()

    def nueva(self):
        self._limpiar_ejes_extra()
        self.ax.clear()
        self.ax.set_axis_on()
        for lado in ("top", "right"):
            self.ax.spines[lado].set_visible(False)
        self.ax.grid(alpha=0.25)
        return self.ax

    def vacia(self, texto):
        self._limpiar_ejes_extra()
        self.ax.clear()
        self.ax.set_axis_off()
        self.ax.text(0.5, 0.5, texto, ha="center", va="center", color=GRIS, fontsize=11,
                     transform=self.ax.transAxes)
        self.canvas.draw_idle()

    def dibujar(self, columnas=None, filas=None):
        if columnas is not None:
            self.datos = (columnas, filas or [])
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def exportar(self):
        cols, filas = self.datos
        if not filas:
            messagebox.showinfo(m.APP_NOMBRE, "Primero genera una gráfica.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV para Excel", "*.csv")],
                                            initialfile=f"{self.nombre}_{dt.date.today()}.csv")
        if ruta:
            m.exportar_csv(ruta, cols, filas)
            messagebox.showinfo(m.APP_NOMBRE, f"Guardado en:\n{ruta}")

    def guardar_imagen(self):
        ruta = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("Imagen PNG", "*.png")],
                                            initialfile=f"{self.nombre}_{dt.date.today()}.png")
        if ruta:
            self.fig.savefig(ruta, dpi=150, bbox_inches="tight")


class Tarjeta(ttk.Frame):
    """Indicador (KPI) con título y número grande."""

    def __init__(self, padre, titulo):
        super().__init__(padre, style="Card.TFrame", padding=(12, 8))
        ttk.Label(self, text=titulo, style="CardTit.TLabel").pack(anchor="w")
        self.valor = ttk.Label(self, text="—", style="CardVal.TLabel")
        self.valor.pack(anchor="w")
        self.nota = ttk.Label(self, text="", style="CardNota.TLabel")
        self.nota.pack(anchor="w")

    def poner(self, valor, nota=""):
        self.valor.config(text=valor)
        self.nota.config(text=nota)


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(m.APP_NOMBRE)
        self.geometry("1360x860")
        self.minsize(1080, 700)
        self.configure(bg=FONDO)
        try:
            self.iconbitmap(ruta_recurso("radar.ico"))
        except tk.TclError:
            pass

        self.cfg = m.cargar_config()
        self.db = m.BaseDatos()
        self._nuevo_cliente_trends()
        self.cola: queue.Queue = queue.Queue()
        self.trabajando = 0
        self.escaneando = False
        self._id_escaneo = None
        self.negocio = None      # datos importados
        self.pinterest = []

        self._estilos()
        self._encabezado()
        self._franja_mercado()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        self._tab_mercado()
        self._tab_busquedas()
        self._tab_tendencias_dia()
        self._tab_redes()
        self._tab_negocio()
        self._tab_alertas()
        self._tab_config()
        self._barra_estado()
        self._aplicar_mercado(inicial=True)
        if not self.mercado:
            self.nb.select(0)        # primera vez: que elija su mercado

        self.after(120, self._revisar_cola)
        self._programar_escaneo()
        self.after(2500, self._revisar_actualizacion)

    def report_callback_exception(self, exc, val, tb):
        """Cualquier error de un botón se guarda en errores.log y se muestra, sin cerrar el programa."""
        ruta = registrar_error("".join(traceback.format_exception(exc, val, tb)))
        messagebox.showerror(m.APP_NOMBRE, f"Ocurrió un error: {val}\n\nDetalle guardado en:\n{ruta}")

    # ----------------------------------------------------------- apariencia
    def _estilos(self):
        for nombre in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            try:
                tkfont.nametofont(nombre).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=FONDO, font=("Segoe UI", 10))
        st.configure("TFrame", background=FONDO)
        st.configure("TLabel", background=FONDO)
        st.configure("Sub.TLabel", foreground=GRIS, background=FONDO)
        st.configure("Titulo.TLabel", font=("Segoe UI Semibold", 12), background=FONDO)
        st.configure("TNotebook", background=FONDO, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI Semibold", 10))
        st.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", ACENTO)])
        st.configure("TButton", padding=(10, 5))
        st.configure("Accent.TButton", background=ACENTO, foreground="white", padding=(12, 5))
        st.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#93c5fd")])
        st.configure("Treeview", rowheight=26, background="white", fieldbackground="white")
        st.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), background="#e5e7eb")
        st.map("Treeview", background=[("selected", "#bfdbfe")], foreground=[("selected", OSCURO)])
        st.configure("Card.TFrame", background="white", relief="solid", borderwidth=1)
        st.configure("CardTit.TLabel", background="white", foreground=GRIS, font=("Segoe UI", 9))
        st.configure("CardVal.TLabel", background="white", foreground=OSCURO, font=("Segoe UI Semibold", 17))
        st.configure("CardNota.TLabel", background="white", foreground=GRIS, font=("Segoe UI", 9))
        st.configure("TLabelframe", background=FONDO)
        st.configure("TLabelframe.Label", background=FONDO, font=("Segoe UI Semibold", 10))
        st.configure("TCheckbutton", background=FONDO)

    def _encabezado(self):
        cab = tk.Frame(self, bg=OSCURO, height=58)
        cab.pack(fill="x")
        tk.Label(cab, text="●  " + m.APP_NOMBRE, bg=OSCURO, fg="white",
                 font=("Segoe UI Semibold", 16)).pack(side="left", padx=16, pady=10)
        tk.Label(cab, text="Mercado:", bg=OSCURO, fg="#9ca3af", font=("Segoe UI", 10)).pack(side="left", padx=(28, 6))
        self.cmb_mercado = ttk.Combobox(cab, state="readonly", width=34)
        self.cmb_mercado.pack(side="left")
        self.cmb_mercado.bind("<<ComboboxSelected>>", lambda _e: self._cambiar_mercado(self.cmb_mercado.get()))
        self.lbl_pais = tk.Label(cab, text="", bg=OSCURO, fg="#d1d5db", font=("Segoe UI", 10))
        self.lbl_pais.pack(side="right", padx=16)
        self._actualizar_lbl_pais()

    def _franja_mercado(self):
        self.franja = tk.Frame(self, bg="#fef3c7")
        self.franja.pack(fill="x")
        self.lbl_franja = tk.Label(self.franja, text="", bg="#fef3c7", fg="#78350f", font=("Segoe UI", 10),
                                   anchor="w", justify="left")
        self.lbl_franja.pack(side="left", fill="x", expand=True, padx=16, pady=6)

    # ------------------------------------------------------------ mercado
    @property
    def mercado(self):
        return m.mercado_activo(self.cfg)

    def _lista_mercados(self):
        return sorted(self.cfg.get("mercados") or {})

    def _cambiar_mercado(self, nombre):
        self.cfg["mercado_activo"] = "" if nombre == SIN_MERCADO else nombre
        m.guardar_config(self.cfg)
        self._aplicar_mercado()

    def _aplicar_mercado(self, inicial=False):
        """Ajusta todas las pestañas al mercado elegido."""
        mer = self.mercado
        self.cmb_mercado.config(values=[SIN_MERCADO] + self._lista_mercados())
        self.cmb_mercado.set(mer.nombre if mer else SIN_MERCADO)
        if mer:
            muestra = ", ".join(mer.palabras[:7]) + ("…" if len(mer.palabras) > 7 else "")
            self.franja.config(bg="#fef3c7")
            self.lbl_franja.config(bg="#fef3c7", fg="#78350f",
                                   text=f"Analizando solo el mercado «{mer.nombre}»:  {muestra}")
            self.b_terminos.delete(0, "end")
            self.b_terminos.insert(0, ", ".join(mer.palabras[:5]))
            self.btn_rel.config(text="Búsquedas que suben en mi mercado")
            self.btn_ideas.config(text="Ideas de palabras clave de mi mercado")
            self.chk_ajustar.state(["!disabled"])
            self.p_interes.set(next((k for k, v in INTERESES_PINTEREST.items() if v == mer.pinterest), "(todos)"))
            self.r_tema_lbl.config(text="Tema dentro de tu mercado (opcional):")
            self.r_tema.delete(0, "end")
            self.lbl_hoy.config(text=f"Tendencias de «{mer.nombre}»")
        else:
            self.franja.config(bg="#e5e7eb")
            self.lbl_franja.config(bg="#e5e7eb", fg="#374151",
                                   text="Sin mercado: estás viendo todos los temas. Crea o elige tu mercado en la "
                                        "pestaña «Mi mercado» para analizar solo tu giro.")
            self.btn_rel.config(text="Búsquedas que suben (del 1er término)")
            self.btn_ideas.config(text="Ideas de palabras clave (del 1er término)")
            self.chk_ajustar.state(["disabled"])
            self.r_tema_lbl.config(text="Tema, marca o hashtag:")
            self.lbl_hoy.config(text="Lo más buscado hoy en Google")
        self._mk_refrescar_lista()
        if not inicial:
            self.estado.set(f"Mercado: {mer.nombre if mer else 'sin filtro'}")

    def _revisar_actualizacion(self):
        def listo(nueva):
            if not nueva:
                return
            barra = tk.Frame(self, bg="#dbeafe")
            barra.pack(fill="x", before=self.franja)
            tk.Label(barra, text=f"Hay una versión nueva ({nueva['version']}) de {m.APP_NOMBRE}.", bg="#dbeafe",
                     fg="#1e3a8a", font=("Segoe UI Semibold", 10)).pack(side="left", padx=16, pady=6)
            ttk.Button(barra, text="Descargar", command=lambda: webbrowser.open(nueva["url"])).pack(side="left")
            ttk.Button(barra, text="Ahora no", command=barra.destroy).pack(side="left", padx=6)

        self.en_hilo(m.buscar_actualizacion, listo, "Buscando actualizaciones…", silencioso=True)

    def _actualizar_lbl_pais(self):
        pais = self.cfg.get("pais") or "Mundial"
        self.lbl_pais.config(text=f"País: {pais}   ·   Idioma: {self.cfg.get('idioma')}   ·   v{m.APP_VERSION}")

    def _barra_estado(self):
        barra = ttk.Frame(self, padding=(10, 4))
        barra.pack(fill="x", side="bottom")
        self.estado = tk.StringVar(value="Listo.")
        ttk.Label(barra, textvariable=self.estado, style="Sub.TLabel").pack(side="left")
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=160)
        self.progreso.pack(side="right")

    # ------------------------------------------------- trabajo en segundo plano
    def _nuevo_cliente_trends(self):
        self.gt = m.GoogleTrends(self.cfg.get("pais", "MX"), self.cfg.get("idioma", "es-419"),
                                 int(self.cfg.get("zona_horaria_min", 360)))

    def ui(self, funcion):
        """Pide al hilo principal que ejecute algo (Tkinter no es seguro entre hilos)."""
        self.cola.put(("ui", funcion))

    def en_hilo(self, trabajo, al_terminar, mensaje="Consultando…", boton=None, silencioso=False,
                al_fallar=None):
        self.trabajando += 1
        self.estado.set(mensaje)
        self.progreso.start(12)
        if boton is not None:
            boton.state(["disabled"])

        def correr():
            try:
                res, err = trabajo(), None
            except m.ErrorFuente as e:
                res, err = None, str(e)
            except Exception as e:  # noqa: BLE001
                res, err = None, f"Error inesperado: {e}"
            self.cola.put(("fin", al_terminar, res, err, boton, silencioso, al_fallar))

        threading.Thread(target=correr, daemon=True).start()

    def _revisar_cola(self):
        try:
            while True:
                item = self.cola.get_nowait()
                if item[0] == "ui":
                    item[1]()
                    continue
                _, al_terminar, res, err, boton, silencioso, al_fallar = item
                self.trabajando = max(0, self.trabajando - 1)
                if not self.trabajando:
                    self.progreso.stop()
                if boton is not None:
                    boton.state(["!disabled"])
                if err:
                    self.estado.set("Aviso: " + err)
                    if al_fallar:
                        al_fallar()
                    if not silencioso:
                        messagebox.showwarning(m.APP_NOMBRE, err)
                    continue
                try:
                    al_terminar(res)
                    if not self.trabajando:
                        self.estado.set(f"Listo · {dt.datetime.now():%H:%M:%S}")
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror(m.APP_NOMBRE, f"No se pudo mostrar el resultado: {e}")
        except queue.Empty:
            pass
        self.after(120, self._revisar_cola)

    # =====================================================================
    # 0) MI MERCADO
    # =====================================================================
    def _tab_mercado(self):
        t = ttk.Frame(self.nb, padding=16)
        self.nb.add(t, text="Mi mercado")
        izq = ttk.Frame(t)
        izq.pack(side="left", fill="y", padx=(0, 22))
        ttk.Label(izq, text="Tus mercados", style="Titulo.TLabel").pack(anchor="w")
        self.mk_lista = tk.Listbox(izq, height=14, width=32, font=("Segoe UI", 10), activestyle="none",
                                   selectbackground="#bfdbfe", selectforeground=OSCURO, relief="solid", bd=1,
                                   exportselection=False)
        self.mk_lista.pack(fill="y", expand=True, pady=6)
        self.mk_lista.bind("<<ListboxSelect>>", self._mk_seleccion)
        ttk.Button(izq, text="Nuevo mercado", command=self._mk_nuevo).pack(fill="x")
        ttk.Button(izq, text="Borrar mercado", command=self._mk_borrar).pack(fill="x", pady=(6, 0))

        der = ttk.Frame(t)
        der.pack(side="left", fill="both", expand=True)
        ttk.Label(der, text="Analiza solo las tendencias de tu mercado", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(der, text="Escribe tu giro (salones de fiestas, oficinas, cafeterías o el que sea) y las palabras "
                            "con las que la gente lo busca. Búsquedas, tendencias del día, YouTube, noticias, "
                            "Pinterest y alertas se limitan a ese mercado.",
                  style="Sub.TLabel", wraplength=900, justify="left").pack(anchor="w", pady=(2, 14))
        f = ttk.Frame(der)
        f.pack(fill="x")
        ttk.Label(f, text="Nombre del mercado:").grid(row=0, column=0, sticky="w")
        self.mk_nombre = ttk.Entry(f, width=38)
        self.mk_nombre.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(f, text="o empieza con una plantilla:").grid(row=0, column=2, sticky="w", padx=(18, 6))
        self.mk_plantilla = ttk.Combobox(f, values=list(m.PLANTILLAS_MERCADO), state="readonly", width=30)
        self.mk_plantilla.grid(row=0, column=3, sticky="w")
        ttk.Button(f, text="Usar plantilla", command=self._mk_usar_plantilla).grid(row=0, column=4, padx=6)

        cols = ttk.Frame(der)
        cols.pack(fill="both", expand=True, pady=(16, 0))
        c1 = ttk.Frame(cols)
        c1.pack(side="left", fill="both", expand=True)
        ttk.Label(c1, text="Palabras que definen tu mercado (una por línea)").pack(anchor="w")
        ttk.Label(c1, text="Servicios, productos y ocasiones, como los buscaría un cliente. La primera es la principal.",
                  style="Sub.TLabel").pack(anchor="w")
        self.mk_palabras = tk.Text(c1, height=13, font=("Segoe UI", 10), relief="solid", bd=1, wrap="none", undo=True)
        self.mk_palabras.pack(fill="both", expand=True, pady=6)
        self.btn_sugerir = ttk.Button(c1, text="Sugerir palabras con Google", command=self._mk_sugerir)
        self.btn_sugerir.pack(anchor="w")
        c2 = ttk.Frame(cols, padding=(22, 0, 0, 0))
        c2.pack(side="left", fill="y")
        ttk.Label(c2, text="Palabras a ignorar (opcional)").pack(anchor="w")
        ttk.Label(c2, text="Lo que no quieres ver, por ejemplo:\nempleo, vacantes, gratis.", style="Sub.TLabel",
                  justify="left").pack(anchor="w")
        self.mk_excluir = tk.Text(c2, height=6, width=34, font=("Segoe UI", 10), relief="solid", bd=1, wrap="none")
        self.mk_excluir.pack(anchor="w", pady=6)
        ttk.Label(c2, text="Categoría en Pinterest:").pack(anchor="w", pady=(10, 2))
        self.mk_pin = ttk.Combobox(c2, values=list(INTERESES_PINTEREST), state="readonly", width=30)
        self.mk_pin.set("(todos)")
        self.mk_pin.pack(anchor="w")
        ttk.Button(der, text="Guardar y analizar este mercado", style="Accent.TButton",
                   command=self._mk_guardar).pack(anchor="w", pady=16)

    @staticmethod
    def _mk_leer(widget):
        return [linea.strip() for linea in widget.get("1.0", "end").splitlines() if linea.strip()]

    @staticmethod
    def _mk_poner(widget, lineas):
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(lineas))

    def _mk_refrescar_lista(self):
        self.mk_lista.delete(0, "end")
        activo = self.cfg.get("mercado_activo")
        for i, nombre in enumerate(self._lista_mercados()):
            self.mk_lista.insert("end", ("●  " if nombre == activo else "    ") + nombre)
            if nombre == activo:
                self.mk_lista.selection_clear(0, "end")
                self.mk_lista.selection_set(i)

    def _mk_seleccion(self, _e=None):
        sel = self.mk_lista.curselection()
        if not sel:
            return
        nombre = self.mk_lista.get(sel[0]).replace("●", "").strip()
        datos = (self.cfg.get("mercados") or {}).get(nombre)
        if datos:
            self._mk_llenar(nombre, datos)

    def _mk_llenar(self, nombre, datos):
        self.mk_nombre.delete(0, "end")
        self.mk_nombre.insert(0, nombre)
        self._mk_poner(self.mk_palabras, datos.get("palabras", []))
        self._mk_poner(self.mk_excluir, datos.get("excluir", []))
        self.mk_pin.set(next((k for k, v in INTERESES_PINTEREST.items() if v == datos.get("pinterest", "")),
                             "(todos)"))

    def _mk_nuevo(self):
        self._mk_llenar("", {})
        self.mk_lista.selection_clear(0, "end")
        self.mk_nombre.focus_set()

    def _mk_usar_plantilla(self):
        nombre = self.mk_plantilla.get()
        if not nombre:
            messagebox.showinfo(m.APP_NOMBRE, "Elige una plantilla de la lista.")
            return
        actual = self.mk_nombre.get().strip()
        self._mk_llenar(actual or nombre, m.PLANTILLAS_MERCADO[nombre])

    def _mk_sugerir(self):
        nombre = self.mk_nombre.get().strip() or next(iter(self._mk_leer(self.mk_palabras)), "")
        if not nombre:
            messagebox.showinfo(m.APP_NOMBRE, "Escribe primero el nombre de tu mercado, por ejemplo «salones de fiestas».")
            return

        def listo(sugerencias):
            actuales = self._mk_leer(self.mk_palabras)
            vistas = {m.normalizar(x).strip() for x in actuales}
            nuevas = [s for s in sugerencias if m.normalizar(s).strip() not in vistas]
            if not actuales:
                actuales = [nombre]
            self._mk_poner(self.mk_palabras, actuales + nuevas)
            self.estado.set(f"Agregué {len(nuevas)} palabras que la gente busca. Borra las que no sean de tu mercado.")

        self.en_hilo(lambda: m.sugerir_palabras_mercado(nombre, self.cfg.get("pais", "MX"),
                                                        self.cfg.get("idioma", "es-419")),
                     listo, "Buscando cómo busca la gente tu mercado…", self.btn_sugerir)

    def _mk_guardar(self):
        nombre = self.mk_nombre.get().strip()
        if not nombre:
            messagebox.showinfo(m.APP_NOMBRE, "Ponle nombre a tu mercado, por ejemplo «Salones de fiestas».")
            return
        mer = m.Mercado(nombre, self._mk_leer(self.mk_palabras), self._mk_leer(self.mk_excluir),
                        INTERESES_PINTEREST.get(self.mk_pin.get(), ""))
        self.cfg.setdefault("mercados", {})[nombre] = mer.a_dict()
        self.cfg["mercado_activo"] = nombre
        m.guardar_config(self.cfg)
        self._mk_poner(self.mk_palabras, mer.palabras)
        self._aplicar_mercado()
        messagebox.showinfo(m.APP_NOMBRE, f"Listo. Desde ahora todo se analiza dentro de «{nombre}».\n\n"
                                          f"Puedes cambiar de mercado arriba, junto al nombre del programa.")
        self.nb.select(self.tab_busquedas)

    def _mk_borrar(self):
        sel = self.mk_lista.curselection()
        if not sel:
            messagebox.showinfo(m.APP_NOMBRE, "Selecciona en la lista el mercado que quieres borrar.")
            return
        nombre = self.mk_lista.get(sel[0]).replace("●", "").strip()
        if not messagebox.askyesno(m.APP_NOMBRE, f"¿Borrar el mercado «{nombre}»?"):
            return
        (self.cfg.get("mercados") or {}).pop(nombre, None)
        if self.cfg.get("mercado_activo") == nombre:
            self.cfg["mercado_activo"] = ""
        m.guardar_config(self.cfg)
        self._mk_nuevo()
        self._aplicar_mercado()

    # =====================================================================
    # 1) BÚSQUEDAS
    # =====================================================================
    def _tab_busquedas(self):
        t = ttk.Frame(self.nb, padding=12)
        self.tab_busquedas = t
        self.nb.add(t, text="Búsquedas (Google)")

        f1 = ttk.Frame(t)
        f1.pack(fill="x")
        ttk.Label(f1, text="Términos (hasta 5, separados por coma):").pack(side="left")
        self.b_terminos = ttk.Entry(f1, width=55)
        self.b_terminos.insert(0, "café de especialidad, matcha, chai")
        self.b_terminos.pack(side="left", padx=6)
        self.b_terminos.bind("<Return>", lambda _e: self._b_comparar())
        ttk.Label(f1, text="Periodo:").pack(side="left", padx=(8, 0))
        self.b_periodo = ttk.Combobox(f1, values=list(m.PERIODOS_TRENDS), state="readonly", width=17)
        self.b_periodo.set("Últimos 90 días")
        self.b_periodo.pack(side="left", padx=6)
        self.ajustar = tk.BooleanVar(value=True)
        self.chk_ajustar = ttk.Checkbutton(f1, text="Ajustar términos a mi mercado", variable=self.ajustar)
        self.chk_ajustar.pack(side="left", padx=(10, 0))

        f2 = ttk.Frame(t)
        f2.pack(fill="x", pady=(8, 0))
        self.btn_comparar = ttk.Button(f2, text="Comparar interés", style="Accent.TButton", command=self._b_comparar)
        self.btn_comparar.pack(side="left")
        self.btn_rel = ttk.Button(f2, text="Búsquedas que suben (del 1er término)", command=self._b_relacionadas)
        self.btn_rel.pack(side="left", padx=6)
        self.btn_ideas = ttk.Button(f2, text="Ideas de palabras clave (del 1er término)", command=self._b_ideas)
        self.btn_ideas.pack(side="left")
        ttk.Label(f2, text="Interés 0-100: 100 = el momento de más búsquedas en el periodo.",
                  style="Sub.TLabel").pack(side="right")

        self.b_resumen = ttk.Label(t, text="", wraplength=1250, justify="left")
        self.b_resumen.pack(fill="x", pady=(8, 0))

        pan = ttk.PanedWindow(t, orient="horizontal")
        pan.pack(fill="both", expand=True, pady=(8, 0))
        self.b_graf = Grafica(pan, nombre="interes_google")
        pan.add(self.b_graf, weight=3)
        self.b_lado = ttk.Notebook(pan)
        pan.add(self.b_lado, weight=2)
        usar = lambda vals: self._b_usar_termino(vals[0])  # noqa: E731
        self.b_subiendo = Tabla(self.b_lado, ["Búsqueda", "Crecimiento", "Viene de"], [230, 110, 130],
                                "busquedas_que_suben", usar)
        self.b_top = Tabla(self.b_lado, ["Búsqueda", "Interés", "Viene de"], [230, 80, 130], "busquedas_top", usar)
        self.b_ideas = Tabla(self.b_lado, ["Idea de palabra clave", "Fuerza", "Viene de"], [250, 70, 130],
                             "ideas_palabras", usar)
        self.b_lado.add(self.b_subiendo, text="Suben rápido")
        self.b_lado.add(self.b_top, text="Más buscadas")
        self.b_lado.add(self.b_ideas, text="Ideas (autocompletar)")

    def _b_terminos_lista(self):
        lista = [x.strip() for x in self.b_terminos.get().split(",") if x.strip()]
        if not lista:
            messagebox.showinfo(m.APP_NOMBRE, "Escribe al menos un término.")
        return lista

    def _b_usar_termino(self, termino):
        self.b_terminos.delete(0, "end")
        self.b_terminos.insert(0, termino)
        self._b_comparar()

    def _b_comparar(self):
        terminos = self._b_terminos_lista()[:5]
        if not terminos:
            return
        mer = self.mercado
        ajustados = []
        if mer and self.ajustar.get():
            originales = terminos
            terminos = list(dict.fromkeys(mer.ajustar_termino(x) for x in terminos))
            ajustados = [f"«{a}» → «{b}»" for a, b in zip(originales, terminos) if a != b]
        tiempo = m.PERIODOS_TRENDS[self.b_periodo.get()]
        umbral = float(self.cfg.get("umbral_z", 2.0))

        def listo(res):
            fechas, series = res
            ax = self.b_graf.nueva()
            textos, filas = [], []
            for i, (t, v) in enumerate(series.items()):
                ax.plot(fechas, v, label=t, color=COLORES[i % len(COLORES)], linewidth=2)
                base = v[:-1] if len(v) > 8 else v          # el último punto suele estar incompleto
                p = m.detectar_pico(base, umbral, ventana=max(1, len(base) // 15))
                marca = "  ▲ PICO" if p["es_pico"] else ""
                textos.append(f"{t}: promedio {statistics.fmean(v):.0f}/100 · reciente {p['reciente']:.0f} "
                              f"({fpct(p['cambio_pct'])} vs normal){marca}")
            for j, f in enumerate(fechas):
                filas.append([f.strftime("%Y-%m-%d %H:%M")] + [series[t][j] for t in series])
            ax.set_ylabel("Interés relativo (0-100)")
            ax.set_ylim(0, 105)
            ax.set_title(f"Interés de búsqueda en Google · {self.b_periodo.get()} · {self.cfg.get('pais') or 'Mundial'}",
                         fontsize=11, loc="left")
            ax.legend(frameon=False)
            formatear_eje_fechas(ax, fechas)
            self.b_graf.fig.autofmt_xdate()
            self.b_graf.dibujar(["Fecha"] + list(series), filas)
            if ajustados:
                textos.append("Ajustado a tu mercado: " + ", ".join(ajustados))
            self.b_resumen.config(text="     |     ".join(textos))

        self.en_hilo(lambda: self.gt.interes_en_el_tiempo(terminos, tiempo), listo,
                     "Consultando Google Trends…", self.btn_comparar)

    def _avance(self, texto):
        def avisar(i, n, palabra=""):
            extra = f" «{palabra}»" if palabra else ""
            self.ui(lambda: self.estado.set(f"{texto}{extra} ({i}/{n})…"))
        return avisar

    def _b_relacionadas(self):
        mer = self.mercado
        terminos = [] if mer else self._b_terminos_lista()
        if not mer and not terminos:
            return
        tiempo = m.PERIODOS_TRENDS[self.b_periodo.get()]
        if tiempo.startswith("now 1") or tiempo == "now 4-H":
            tiempo = "now 7-d"      # en pocas horas Google casi nunca tiene búsquedas relacionadas
        origen = mer.nombre if mer else terminos[0]

        def trabajo():
            if mer:
                return m.relacionadas_mercado(self.gt, mer, tiempo, 5, self._avance("Revisando"))
            r = self.gt.relacionadas(terminos[0], tiempo)
            return {"subiendo": [(q, v, terminos[0]) for q, v in r["subiendo"]],
                    "top": [(q, v, terminos[0]) for q, v in r["top"]], "errores": []}

        def listo(res):
            nota = f"Búsquedas de «{origen}» que más crecieron · doble clic para analizar"
            if res.get("errores"):
                nota += f" · {len(res['errores'])} palabra(s) sin datos"
            self.b_subiendo.cargar([list(x) for x in res["subiendo"]], nota=nota)
            self.b_top.cargar([list(x) for x in res["top"]])
            self.b_lado.select(self.b_subiendo)
            if not res["subiendo"] and not res["top"]:
                messagebox.showinfo(m.APP_NOMBRE, "Google no tiene suficientes datos de búsquedas relacionadas. "
                                                  "Prueba palabras más generales o un periodo más largo.")

        self.en_hilo(trabajo, listo, "Buscando búsquedas relacionadas…", self.btn_rel)

    def _b_ideas(self):
        mer = self.mercado
        terminos = [] if mer else self._b_terminos_lista()
        if not mer and not terminos:
            return
        pais, idioma = self.cfg.get("pais", "MX"), self.cfg.get("idioma", "es-419")
        origen = mer.nombre if mer else terminos[0]

        def trabajo():
            if mer:
                return m.ideas_mercado(mer, pais, idioma, self._avance("Recolectando ideas de"))
            avance = self._avance("Recolectando ideas de Google")
            return [(s, c, terminos[0]) for s, c in
                    m.ideas_palabras(terminos[0], pais, idioma, True, lambda i, n: avance(i, n))]

        def listo(res):
            self.b_ideas.cargar([[s, c, o] for s, c, o in res],
                                nota=f"{len(res)} ideas reales que la gente escribe sobre «{origen}» · "
                                     f"doble clic para analizar")
            self.b_lado.select(self.b_ideas)

        self.en_hilo(trabajo, listo, "Recolectando ideas de Google…", self.btn_ideas)

    # =====================================================================
    # 2) TENDENCIAS DEL DÍA
    # =====================================================================
    def _tab_tendencias_dia(self):
        t = ttk.Frame(self.nb, padding=12)
        self.nb.add(t, text="Tendencias del día")
        pan = ttk.PanedWindow(t, orient="horizontal")
        pan.pack(fill="both", expand=True)

        izq = ttk.Frame(pan)
        pan.add(izq, weight=3)
        f = ttk.Frame(izq)
        f.pack(fill="x", pady=(0, 6))
        self.lbl_hoy = ttk.Label(f, text="Lo más buscado hoy en Google", style="Titulo.TLabel")
        self.lbl_hoy.pack(side="left")
        self.btn_hoy = ttk.Button(f, text="Actualizar", style="Accent.TButton", command=self._d_google)
        self.btn_hoy.pack(side="right")
        self.d_nb = ttk.Notebook(izq)
        self.d_nb.pack(fill="both", expand=True)
        self.d_semana = Tabla(self.d_nb, ["Búsqueda", "Crecimiento", "Viene de"], [300, 140, 180],
                              "suben_esta_semana", lambda vals: self._ir_a_busqueda(vals[0]))
        self.d_google = Tabla(self.d_nb, ["Tema", "Búsquedas", "Hora", "Noticia relacionada", "Medio"],
                              [200, 90, 70, 380, 120], "tendencias_hoy_google")
        self.d_nb.add(self.d_semana, text="Suben esta semana en tu mercado")
        self.d_nb.add(self.d_google, text="Hoy en Google")

        der = ttk.Frame(pan, padding=(12, 0, 0, 0))
        pan.add(der, weight=2)
        ttk.Label(der, text="Pinterest Trends (ideas que vienen)", style="Titulo.TLabel").pack(anchor="w")
        f2 = ttk.Frame(der)
        f2.pack(fill="x", pady=6)
        self.p_tipo = ttk.Combobox(f2, values=list(m.TIPOS_PINTEREST), state="readonly", width=15)
        self.p_tipo.set("Creciendo ahora")
        self.p_tipo.pack(side="left")
        self.p_interes = ttk.Combobox(f2, values=list(INTERESES_PINTEREST), state="readonly", width=22)
        self.p_interes.set("(todos)")
        self.p_interes.pack(side="left", padx=6)
        self.btn_pin = ttk.Button(f2, text="Consultar", command=self._d_pinterest)
        self.btn_pin.pack(side="left")
        self.d_pin = Tabla(der, ["Palabra", "Semana", "Mes", "Año"], [200, 80, 80, 80], "pinterest_trends",
                           al_seleccionar=self._d_pin_grafica)
        self.d_pin.pack(fill="both", expand=True)
        self.d_pin_graf = Grafica(der, alto=2.6, nombre="pinterest")
        self.d_pin_graf.pack(fill="both", expand=False, pady=(6, 0))
        self.d_pin_graf.vacia("Selecciona una palabra para ver su curva")

    def _ir_a_busqueda(self, termino):
        self.nb.select(self.tab_busquedas)
        self._b_usar_termino(termino)

    def _d_google(self):
        mer = self.mercado
        pais = self.cfg.get("pais") or "MX"

        def trabajo():
            hoy = m.tendencias_del_dia(pais)
            semana, error = None, ""
            if mer:
                try:
                    semana = m.relacionadas_mercado(self.gt, mer, "now 7-d", 5, self._avance("Revisando"))
                except m.ErrorFuente as e:
                    error = str(e)
            return hoy, m.filtrar_por_mercado(hoy, mer), semana, error

        def listo(res):
            hoy, filtrados, semana, error = res
            filas = [[r["tema"], r["busquedas"], r["fecha"].strftime("%H:%M") if r["fecha"] else "",
                      r["noticia"], r["medio"]] for r in filtrados]
            if mer:
                nota = (f"{len(filtrados)} de {len(hoy)} temas de hoy tocan «{mer.nombre}» · doble clic abre la noticia"
                        if filtrados else f"Hoy ninguno de los {len(hoy)} temas generales de Google toca "
                                          f"«{mer.nombre}». Revisa «Suben esta semana».")
            else:
                nota = f"{len(hoy)} temas en tendencia ahora · doble clic abre la noticia"
            self.d_google.cargar(filas, urls=[r["url"] for r in filtrados], nota=nota)
            if semana is not None:
                self.d_semana.cargar([list(x) for x in semana["subiendo"]],
                                     nota=f"Lo que más creció en «{mer.nombre}» en los últimos 7 días · "
                                          f"doble clic para graficar")
                self.d_nb.select(self.d_semana)
            elif mer:
                self.d_semana.cargar([], nota=f"No se pudo consultar: {error}")
            else:
                self.d_semana.cargar([], nota="Elige un mercado en «Mi mercado» para ver qué está subiendo en tu giro.")
                self.d_nb.select(self.d_google)

        self.en_hilo(trabajo, listo, "Descargando tendencias del día…", self.btn_hoy)

    def _d_pinterest(self):
        tipo = m.TIPOS_PINTEREST[self.p_tipo.get()]
        interes = INTERESES_PINTEREST[self.p_interes.get()]

        mer = self.mercado

        def listo(res):
            nota = None
            if mer:
                # Si la categoría es la de tu mercado se muestran todas, con las tuyas primero y en amarillo;
                # si no, solo las que mencionan tu mercado.
                propias = [r for r in res if mer.coincide(r["palabra"])]
                if interes and interes == mer.pinterest:
                    res = propias + [r for r in res if r not in propias]
                    nota = f"{len(res)} ideas de la categoría de tu mercado · en amarillo las que lo mencionan"
                else:
                    res = propias
                    nota = (f"{len(res)} ideas que mencionan «{mer.nombre}»" if res else
                            "Ninguna idea de esta categoría toca tu mercado; elige la categoría de tu mercado")
            self.pinterest = res
            self.d_pin.cargar([[r["palabra"], fpct(r["semana"]), fpct(r["mes"]), fpct(r["anio"])] for r in res],
                              picos=[bool(mer and mer.coincide(r["palabra"])) for r in res], nota=nota)

        self.en_hilo(lambda: m.pinterest_tendencias(self.cfg.get("pinterest_token", ""),
                                                    self.cfg.get("pais") or "MX", tipo, interes),
                     listo, "Consultando Pinterest…", self.btn_pin)

    def _d_pin_grafica(self, idx):
        if idx is None or idx >= len(self.pinterest):
            return
        r = self.pinterest[idx]
        pares = [(m.parse_fecha(k), v) for k, v in r["serie"]]
        pares = [(f, v) for f, v in pares if f]
        if not pares:
            self.d_pin_graf.vacia("Sin serie de tiempo para esta palabra")
            return
        ax = self.d_pin_graf.nueva()
        fechas = [f for f, _ in pares]
        ax.plot(fechas, [v for _, v in pares], color="#e60023", linewidth=2)
        ax.set_title(r["palabra"], fontsize=10, loc="left")
        formatear_eje_fechas(ax, fechas)
        self.d_pin_graf.fig.autofmt_xdate()
        self.d_pin_graf.dibujar(["Fecha", r["palabra"]], [[f.isoformat(), v] for f, v in pares])

    # =====================================================================
    # 3) REDES Y MENCIONES
    # =====================================================================
    def _tab_redes(self):
        t = ttk.Frame(self.nb, padding=12)
        self.nb.add(t, text="Redes y menciones")
        f = ttk.Frame(t)
        f.pack(fill="x")
        self.r_tema_lbl = ttk.Label(f, text="Tema, marca o hashtag:")
        self.r_tema_lbl.pack(side="left")
        self.r_tema = ttk.Entry(f, width=40)
        self.r_tema.insert(0, "matcha")
        self.r_tema.pack(side="left", padx=6)
        self.r_tema.bind("<Return>", lambda _e: self._r_ambos())
        ttk.Label(f, text="Últimos").pack(side="left", padx=(8, 0))
        self.r_dias = ttk.Combobox(f, values=["1", "3", "7", "14", "30"], state="readonly", width=4)
        self.r_dias.set("7")
        self.r_dias.pack(side="left", padx=4)
        ttk.Label(f, text="días").pack(side="left")
        self.btn_ambos = ttk.Button(f, text="Analizar todo", style="Accent.TButton", command=self._r_ambos)
        self.btn_ambos.pack(side="left", padx=(12, 6))
        self.btn_yt = ttk.Button(f, text="Solo YouTube", command=self._r_youtube)
        self.btn_yt.pack(side="left")
        self.btn_news = ttk.Button(f, text="Solo noticias", command=self._r_noticias)
        self.btn_news.pack(side="left", padx=6)

        self.r_resumen = ttk.Label(t, text="", wraplength=1250, justify="left")
        self.r_resumen.pack(fill="x", pady=(8, 0))
        self._r_txt = {"yt": "", "news": ""}

        nb = ttk.Notebook(t)
        nb.pack(fill="both", expand=True, pady=(8, 0))
        self.r_nb = nb
        self.r_yt = Tabla(nb, ["Título", "Canal", "Publicado", "Vistas", "Vistas/hora", "Likes", "Coment.",
                               "Engagement"], [420, 160, 110, 90, 90, 80, 70, 90], "youtube_tendencia")
        nb.add(self.r_yt, text="Videos que más rápido crecen (YouTube)")
        news = ttk.PanedWindow(nb, orient="horizontal")
        nb.add(news, text="Menciones en noticias")
        self.r_news_graf = Grafica(news, nombre="menciones_noticias")
        news.add(self.r_news_graf, weight=2)
        self.r_news = Tabla(news, ["Fecha", "Medio", "Título"], [110, 140, 420], "menciones_noticias")
        news.add(self.r_news, weight=3)
        ttk.Label(t, text="Nota: TikTok e Instagram no tienen una API pública gratuita para medir tendencias; "
                          "aquí se usan YouTube (API oficial) y Google Noticias. Herramientas como Brand24, "
                          "Hootsuite o Sprout Social cubren esas redes con suscripción.",
                  style="Sub.TLabel", wraplength=1250).pack(fill="x", pady=(6, 0))

    def _r_poner_resumen(self):
        self.r_resumen.config(text="     |     ".join(x for x in self._r_txt.values() if x))

    def _r_ambos(self):
        if not self._r_consulta():
            return
        if self.cfg.get("youtube_api_key"):
            self._r_youtube()
        else:
            self._r_txt["yt"] = "YouTube: agrega tu clave gratuita en Configuración para ver videos en tendencia."
        self._r_noticias()

    def _r_consulta(self):
        """Regresa (tema, mercado, nombre para mostrar) o None si falta el tema."""
        tema, mer = self.r_tema.get().strip(), self.mercado
        if not tema and not mer:
            messagebox.showinfo(m.APP_NOMBRE, "Escribe un tema, o elige tu mercado en «Mi mercado».")
            return None
        nombre = f"{tema} en {mer.nombre}" if (tema and mer) else (tema or mer.nombre)
        return tema, mer, nombre

    def _r_youtube(self):
        c = self._r_consulta()
        if not c:
            return
        tema, mer, nombre = c
        dias = int(self.r_dias.get())
        consulta = mer.consulta_youtube(tema) if mer else tema

        def listo(res):
            filas = [[v["titulo"], v["canal"], v["publicado"].strftime("%d/%m %H:%M"), fnum(v["vistas"]),
                      fnum(v["vistas_hora"]), fnum(v["likes"]), fnum(v["comentarios"]), f"{v['engagement']:.2f}%"]
                     for v in res]
            picos = [i < 3 for i in range(len(res))]
            self.r_yt.cargar(filas, urls=[v["url"] for v in res], picos=picos,
                             nota=f"{len(res)} videos de «{nombre}» · ordenados por velocidad (vistas por hora) · "
                                  f"en amarillo los 3 más rápidos · doble clic para abrir")
            if res:
                total = sum(v["vistas"] for v in res)
                eng = statistics.fmean(v["engagement"] for v in res)
                self._r_txt["yt"] = (f"YouTube: {len(res)} video{'s' if len(res) != 1 else ''} en {dias} días · {fnum(total)} vistas · "
                                     f"el más rápido va a {fnum(res[0]['vistas_hora'])} vistas/hora · "
                                     f"engagement promedio {eng:.2f}%")
            else:
                self._r_txt["yt"] = f"YouTube: sin videos recientes de «{nombre}»."
            self._r_poner_resumen()
            self.r_nb.select(self.r_yt)

        self.en_hilo(lambda: m.youtube_tendencia(self.cfg.get("youtube_api_key", ""), consulta, dias,
                                                 self.cfg.get("pais", "MX"), self.cfg.get("idioma", "es"),
                                                 50 if mer else 25, mer),
                     listo, "Consultando YouTube…", self.btn_yt)

    def _r_noticias(self):
        c = self._r_consulta()
        if not c:
            return
        tema, mer, nombre = c
        dias = int(self.r_dias.get())
        consulta = mer.consulta_noticias(tema) if mer else tema
        umbral = float(self.cfg.get("umbral_z", 2.0))

        def listo(res):
            self.r_news.cargar([[n["fecha"].strftime("%d/%m %H:%M"), n["medio"], n["titulo"]] for n in res],
                               urls=[n["url"] for n in res])
            fechas, cuentas = m.conteo_por_dia(res, max(dias, 2))
            p = m.detectar_pico(cuentas, umbral, 1)
            ax = self.r_news_graf.nueva()
            colores = [ACENTO] * (len(cuentas) - 1) + ["#dc2626" if p["es_pico"] else "#60a5fa"]
            ax.bar(fechas, cuentas, color=colores, width=0.8)
            ax.set_title(f"Notas por día sobre «{nombre}»", fontsize=11, loc="left")
            ax.set_ylabel("Notas")
            formatear_eje_fechas(ax, fechas)
            self.r_news_graf.fig.autofmt_xdate()
            self.r_news_graf.dibujar(["Fecha", "Notas"], [[f.isoformat(), c] for f, c in zip(fechas, cuentas)])
            marca = "  ▲ PICO HOY" if p["es_pico"] else ""
            self._r_txt["news"] = (f"Noticias: {len(res)} notas en {dias} días · hoy {cuentas[-1]} "
                                   f"(normal {p['normal']:.1f}/día){marca}")
            if len(res) >= 100:
                self._r_txt["news"] += " · Google entrega máx. ~100 notas: el tema es muy grande, usa menos días"
            self._r_poner_resumen()
            if not self.cfg.get("youtube_api_key"):
                self.r_nb.select(1)

        self.en_hilo(lambda: m.menciones_noticias(consulta, dias, self.cfg.get("pais", "MX"),
                                                  self.cfg.get("idioma", "es-419")),
                     listo, "Buscando menciones en noticias…", self.btn_news)

    # =====================================================================
    # 4) MIS DATOS (ventas / Analytics)
    # =====================================================================
    def _tab_negocio(self):
        t = ttk.Frame(self.nb, padding=12)
        self.nb.add(t, text="Mis datos (ventas)")
        f1 = ttk.Frame(t)
        f1.pack(fill="x")
        ttk.Button(f1, text="Abrir CSV o Excel…", style="Accent.TButton", command=self._n_abrir).pack(side="left")
        self.n_archivo = ttk.Label(f1, text="Ventas, reservas, Google Analytics (Exportar → CSV) o cualquier tabla "
                                            "con una columna de fecha.", style="Sub.TLabel")
        self.n_archivo.pack(side="left", padx=10)

        f2 = ttk.Frame(t)
        f2.pack(fill="x", pady=(10, 0))
        ttk.Label(f2, text="Fecha:").pack(side="left")
        self.n_col_fecha = ttk.Combobox(f2, state="readonly", width=18)
        self.n_col_fecha.pack(side="left", padx=(4, 10))
        ttk.Label(f2, text="Valor:").pack(side="left")
        self.n_col_valor = ttk.Combobox(f2, state="readonly", width=18)
        self.n_col_valor.pack(side="left", padx=(4, 10))
        ttk.Label(f2, text="Categoría:").pack(side="left")
        self.n_col_cat = ttk.Combobox(f2, state="readonly", width=18)
        self.n_col_cat.pack(side="left", padx=(4, 10))
        ttk.Label(f2, text="Agrupar por:").pack(side="left")
        self.n_freq = ttk.Combobox(f2, values=["Día", "Semana", "Mes"], state="readonly", width=8)
        self.n_freq.set("Semana")
        self.n_freq.pack(side="left", padx=(4, 10))
        ttk.Label(f2, text="Pronosticar:").pack(side="left")
        self.n_pron = ttk.Spinbox(f2, from_=0, to=52, width=4)
        self.n_pron.set("4")
        self.n_pron.pack(side="left", padx=4)
        ttk.Label(f2, text="periodos").pack(side="left")
        self.n_incompleto = tk.BooleanVar(value=True)
        ttk.Checkbutton(f2, text="Ignorar periodo incompleto", variable=self.n_incompleto).pack(side="left", padx=10)
        self.btn_analizar = ttk.Button(f2, text="Analizar", style="Accent.TButton", command=self._n_analizar)
        self.btn_analizar.pack(side="left")

        kpis = ttk.Frame(t)
        kpis.pack(fill="x", pady=10)
        self.k_total = Tarjeta(kpis, "Total del periodo analizado")
        self.k_prom = Tarjeta(kpis, "Promedio por periodo")
        self.k_crec = Tarjeta(kpis, "Crecimiento reciente")
        self.k_mejor = Tarjeta(kpis, "Mejor periodo")
        self.k_tend = Tarjeta(kpis, "Tendencia")
        self.k_pron = Tarjeta(kpis, "Pronóstico próximo periodo")
        for k in (self.k_total, self.k_prom, self.k_crec, self.k_mejor, self.k_tend, self.k_pron):
            k.pack(side="left", fill="x", expand=True, padx=(0, 8))

        pan = ttk.PanedWindow(t, orient="horizontal")
        pan.pack(fill="both", expand=True)
        self.n_graf = Grafica(pan, nombre="tendencia_ventas")
        pan.add(self.n_graf, weight=3)
        self.n_rank = Tabla(pan, ["Categoría", "Total", "Reciente", "Anterior", "Cambio"],
                            [170, 90, 90, 90, 80], "ranking_categorias", al_seleccionar=self._n_sel_categoria)
        pan.add(self.n_rank, weight=2)
        self.n_graf.vacia("Abre un archivo para ver la tendencia y el pronóstico")
        self._n_filas = None
        self._n_ranking = []

    def _n_abrir(self):
        ruta = filedialog.askopenfilename(title="Abrir datos", filetypes=[
            ("Datos", "*.csv *.xlsx *.xlsm *.txt"), ("CSV", "*.csv"), ("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not ruta:
            return

        def listo(res):
            enc, filas = res
            self._n_enc, self._n_filas = enc, filas
            g = m.adivinar_columnas(enc)
            self.n_col_fecha.config(values=enc)
            self.n_col_valor.config(values=["(contar filas)"] + enc)
            self.n_col_cat.config(values=["(ninguna)"] + enc)
            self.n_col_fecha.set(enc[g["fecha"]] if g["fecha"] is not None else enc[0])
            self.n_col_valor.set(enc[g["valor"]] if g["valor"] is not None else "(contar filas)")
            self.n_col_cat.set(enc[g["categoria"]] if g["categoria"] is not None else "(ninguna)")
            self.n_archivo.config(text=f"{os.path.basename(ruta)} · {len(filas):,} filas · revisa las columnas y "
                                       f"pulsa Analizar")
            self._n_analizar()

        self.en_hilo(lambda: m.leer_tabla(ruta), listo, "Leyendo archivo…")

    def _n_analizar(self):
        if not self._n_filas:
            messagebox.showinfo(m.APP_NOMBRE, "Primero abre un archivo CSV o Excel.")
            return
        enc = self._n_enc
        i_f = enc.index(self.n_col_fecha.get())
        v = self.n_col_valor.get()
        i_v = None if v == "(contar filas)" else enc.index(v)
        c = self.n_col_cat.get()
        i_c = None if c == "(ninguna)" else enc.index(c)
        freq = {"Día": "D", "Semana": "W", "Mes": "M"}[self.n_freq.get()]
        try:
            n_pron = max(0, int(self.n_pron.get()))
        except ValueError:
            n_pron = 4
        try:
            a = m.agrupar(self._n_filas, i_f, i_v, i_c, freq, self.n_incompleto.get())
        except m.ErrorFuente as e:
            messagebox.showwarning(m.APP_NOMBRE, str(e))
            return
        a["freq"], a["n_pron"], a["nombre_valor"] = freq, n_pron, (v if i_v is not None else "Registros")
        self.negocio = a
        n = m.ventana_efectiva(freq, len(a["periodos"]))
        a["ventana"] = n
        self._n_ranking = m.ranking_categorias(a["por_categoria"], n) if a["por_categoria"] else []
        self.n_rank.cargar([[r["categoria"], fnum(r["total"]), fnum(r["reciente"]), fnum(r["anterior"]),
                             fpct(r["cambio"])] for r in self._n_ranking],
                           picos=[(r["cambio"] or 0) > 15 for r in self._n_ranking],
                           nota=(f"{self._ultimos(freq, n).capitalize()} vs {'las' if freq == 'W' else 'los'} {n} anteriores · en amarillo: suben "
                                 f"más de 15% · clic para graficar") if self._n_ranking
                           else "Elige una columna de categoría (producto, servicio…) para ver qué sube y qué baja")
        self._n_kpis()
        self._n_dibujar()

    @staticmethod
    def _ultimos(freq, n):
        return ("últimas" if freq == "W" else "últimos") + f" {n} " + App._unidad(freq, n)

    @staticmethod
    def _unidad(freq, n):
        nombres = {"D": ("día", "días"), "W": ("semana", "semanas"), "M": ("mes", "meses")}[freq]
        return nombres[0] if n == 1 else nombres[1]

    def _n_kpis(self):
        a = self.negocio
        vals, per, freq, n = a["valores"], a["periodos"], a["freq"], a["ventana"]
        self.k_total.poner(fnum(sum(vals)), f"{per[0]:%d/%m/%Y} – {per[-1]:%d/%m/%Y}")
        self.k_prom.poner(fnum(statistics.fmean(vals)), f"por {self._unidad(freq, 1)}")
        cr = m.crecimiento(vals, n)
        self.k_crec.poner(fpct(cr), f"{self._ultimos(freq, n)} vs anteriores")
        i_max = max(range(len(vals)), key=vals.__getitem__)
        self.k_mejor.poner(fnum(vals[i_max]), self._etiqueta_periodo(per[i_max], freq))
        pr = m.pronostico(per, vals, max(a["n_pron"], 1), freq)
        a["pron"] = pr if a["n_pron"] else {"fechas": [], "valores": []}
        prom = statistics.fmean(vals) or 1
        pend_pct = pr["pendiente"] / prom * 100
        direccion = "Subiendo" if pend_pct > 0.5 else ("Bajando" if pend_pct < -0.5 else "Estable")
        self.k_tend.poner(direccion, f"{pend_pct:+.1f}% del promedio por {self._unidad(freq, 1)}")
        nota = self._etiqueta_periodo(pr["fechas"][0], freq) if pr["fechas"] else ""
        if pr.get("factores_dia"):
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            mejor = max(range(7), key=pr["factores_dia"].__getitem__)
            nota += f" · mejor día: {dias[mejor]} ({(pr['factores_dia'][mejor] - 1) * 100:+.0f}%)"
        self.k_pron.poner(fnum(pr["valores"][0]) if pr["valores"] else "—", nota)

    @staticmethod
    def _etiqueta_periodo(f, freq):
        if freq == "M":
            meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
            return f"{meses[f.month - 1]} {f.year}"
        if freq == "W":
            return f"semana del {f:%d/%m/%Y}"
        return f"{f:%d/%m/%Y}"

    def _n_sel_categoria(self, idx):
        if idx is not None and idx < len(self._n_ranking):
            self._n_dibujar(self._n_ranking[idx]["categoria"])

    def _n_dibujar(self, categoria=None):
        a = self.negocio
        if not a:
            return
        per, vals, freq = a["periodos"], a["valores"], a["freq"]
        ax = self.n_graf.nueva()
        ax.plot(per, vals, color=ACENTO, linewidth=2, marker="o" if len(per) <= 60 else None, markersize=3,
                label=f"Total ({a['nombre_valor']})")
        mm_n = {"D": 7, "W": 4, "M": 3}[freq]
        if len(vals) > mm_n:
            mm = m.media_movil(vals, mm_n)
            ax.plot(per, mm, color=GRIS, linestyle="--", linewidth=1.5, label=f"Promedio móvil {mm_n}")
        pr = a.get("pron") or {"fechas": [], "valores": []}
        if pr["fechas"]:
            ax.plot([per[-1]] + pr["fechas"], [vals[-1]] + pr["valores"], color="#d97706", linestyle=":",
                     linewidth=2.2, marker="o", markersize=4, label="Pronóstico")
        filas = [[p.isoformat(), round(v, 2), ""] for p, v in zip(per, vals)]
        filas += [[f.isoformat(), "", round(v, 2)] for f, v in zip(pr["fechas"], pr["valores"])]
        columnas = ["Periodo", a["nombre_valor"], "Pronóstico"]
        if categoria is not None:
            serie = a["por_categoria"].get(categoria, [])
            ax2 = ax.twinx()
            ax2.plot(per, serie, color="#16a34a", linewidth=1.8, label=categoria)
            ax2.set_ylabel(categoria, color="#16a34a")
            ax2.spines["top"].set_visible(False)
            l1, e1 = ax.get_legend_handles_labels()
            l2, e2 = ax2.get_legend_handles_labels()
            ax.legend(l1 + l2, e1 + e2, frameon=False, loc="upper left")
            columnas.append(categoria)
            for i, fila in enumerate(filas[:len(serie)]):
                fila.append(round(serie[i], 2))
        else:
            ax.legend(frameon=False, loc="upper left")
        titulo = f"Tendencia por {self._unidad(freq, 1)}"
        if a.get("periodo_incompleto_excluido"):
            titulo += f"  (se ignoró el periodo incompleto del {a['periodo_incompleto_excluido']:%d/%m})"
        ax.set_title(titulo, fontsize=11, loc="left")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _p: f"{x:,.0f}"))
        formatear_eje_fechas(ax, per + pr["fechas"], "%m/%Y" if freq == "M" else None)
        self.n_graf.fig.autofmt_xdate()
        self.n_graf.dibujar(columnas, filas)

    # =====================================================================
    # 5) ALERTAS
    # =====================================================================
    def _tab_alertas(self):
        t = ttk.Frame(self.nb, padding=12)
        self.tab_alertas = t
        self.nb.add(t, text="Alertas")
        izq = ttk.Frame(t, width=300)
        izq.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(izq, text="Lista de vigilancia", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(izq, text="Te aviso cuando un término se dispara en\nbúsquedas de Google o en noticias,\n"
                            "siempre dentro de tu mercado.",
                  style="Sub.TLabel", justify="left").pack(anchor="w", pady=(2, 8))
        f = ttk.Frame(izq)
        f.pack(fill="x")
        self.a_nuevo = ttk.Entry(f, width=24)
        self.a_nuevo.pack(side="left", fill="x", expand=True)
        self.a_nuevo.bind("<Return>", lambda _e: self._a_agregar())
        ttk.Button(f, text="Agregar", command=self._a_agregar).pack(side="left", padx=(6, 0))
        self.a_lista = tk.Listbox(izq, height=14, font=("Segoe UI", 10), activestyle="none",
                                  selectbackground="#bfdbfe", selectforeground=OSCURO, relief="solid", bd=1)
        self.a_lista.pack(fill="both", expand=True, pady=6)
        ttk.Button(izq, text="Quitar seleccionado", command=self._a_quitar).pack(fill="x")
        ttk.Button(izq, text="Vigilar las palabras de mi mercado", command=self._a_desde_mercado).pack(fill="x", pady=(6, 0))
        ttk.Separator(izq).pack(fill="x", pady=10)
        self.btn_escanear = ttk.Button(izq, text="Escanear ahora", style="Accent.TButton", command=self._a_escanear)
        self.btn_escanear.pack(fill="x")
        self.a_auto = tk.BooleanVar(value=bool(self.cfg.get("auto_escaneo", False)))
        self.a_chk = ttk.Checkbutton(izq, variable=self.a_auto, command=self._a_cambiar_auto,
                                     text=f"Escanear solo cada {self.cfg.get('intervalo_min', 60)} min")
        self.a_chk.pack(anchor="w", pady=(8, 0))
        self.a_ultimo = ttk.Label(izq, text="Aún no se ha escaneado.", style="Sub.TLabel")
        self.a_ultimo.pack(anchor="w", pady=(4, 0))
        ttk.Label(izq, text="Deja el programa abierto (puede estar\nminimizado) para que vigile solo.",
                  style="Sub.TLabel").pack(anchor="w", pady=(8, 0))

        der = ttk.Frame(t)
        der.pack(side="left", fill="both", expand=True)
        ttk.Label(der, text="Historial de lecturas", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(der, text="«Fuerza» = cuántas veces se aleja lo reciente de lo normal (desviaciones). "
                            "Desde el umbral de Configuración se marca como PICO (en amarillo).",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 6))
        self.a_hist = Tabla(der, ["Fecha", "Término", "Fuente", "Reciente", "Normal", "Fuerza", "Cambio",
                                  "¿Pico?", "Detalle"], [120, 140, 120, 70, 70, 60, 70, 60, 360], "historial_alertas")
        self.a_hist.pack(fill="both", expand=True)
        self._a_refrescar()

    def _a_refrescar(self):
        self.a_lista.delete(0, "end")
        for termino in self.db.terminos():
            self.a_lista.insert("end", termino)
        hist = self.db.historial()
        self.a_hist.cargar([[h[0].replace("T", " "), h[1], h[2], fnum(h[3], 1), fnum(h[4], 1), f"{h[5]:.1f}",
                             fpct(h[6]), "SÍ" if h[7] else "", h[8]] for h in hist],
                           picos=[bool(h[7]) for h in hist])

    def _a_agregar(self):
        termino = self.a_nuevo.get().strip()
        if termino:
            self.db.agregar_termino(termino)
            self.a_nuevo.delete(0, "end")
            self._a_refrescar()

    def _a_desde_mercado(self):
        mer = self.mercado
        if not mer:
            messagebox.showinfo(m.APP_NOMBRE, "Primero elige o crea tu mercado en la pestaña «Mi mercado».")
            return
        for palabra in mer.palabras[:5]:
            self.db.agregar_termino(palabra)
        self._a_refrescar()

    def _a_quitar(self):
        sel = self.a_lista.curselection()
        if sel:
            self.db.quitar_termino(self.a_lista.get(sel[0]))
            self._a_refrescar()

    def _a_escanear(self, automatico=False):
        if self.escaneando:
            return
        terminos = self.db.terminos()
        if not terminos:
            if not automatico:
                messagebox.showinfo(m.APP_NOMBRE, "Agrega al menos un término a la lista de vigilancia.")
            return
        self.escaneando = True
        mer = self.mercado

        def trabajo():
            todas = []
            for i, termino in enumerate(terminos):
                self.ui(lambda i=i, t=termino: self.estado.set(f"Escaneando «{t}» ({i + 1}/{len(terminos)})…"))
                lecturas = m.escanear_termino(termino, self.cfg, self.gt, mer)
                for lect in lecturas:
                    self.db.guardar_lectura(lect)
                todas.extend(lecturas)
                if i < len(terminos) - 1:
                    threading.Event().wait(3)   # pausa para que Google no nos limite
            return todas

        def listo(lecturas):
            self.escaneando = False
            self._a_refrescar()
            self.a_ultimo.config(text=f"Último escaneo: {dt.datetime.now():%d/%m %H:%M}")
            picos = [lect for lect in lecturas if lect["es_pico"]]
            if picos:
                self._avisar(picos)
            elif not automatico:
                self.estado.set(f"Escaneo terminado: sin picos · {dt.datetime.now():%H:%M}")

        def fallo():
            self.escaneando = False

        self.en_hilo(trabajo, listo, "Escaneando lista de vigilancia…", self.btn_escanear,
                     silencioso=automatico, al_fallar=fallo)

    def _avisar(self, picos):
        if self.cfg.get("sonido", True):
            try:
                if winsound:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                else:
                    self.bell()
            except RuntimeError:
                pass
        v = tk.Toplevel(self)
        v.title("Algo se está disparando")
        v.configure(bg="white")
        v.attributes("-topmost", True)
        v.resizable(False, False)
        tk.Label(v, text="▲  Tendencia detectada", bg="white", fg="#dc2626",
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(14, 6))
        for p in picos:
            tk.Label(v, text=f"• {p['termino']}  —  {p['fuente']}: {p['detalle']}  ({fpct(p['cambio'])})",
                     bg="white", fg=OSCURO, font=("Segoe UI", 10), justify="left",
                     wraplength=520).pack(anchor="w", padx=18)
        fila = tk.Frame(v, bg="white")
        fila.pack(fill="x", padx=18, pady=14)

        def ver():
            self.deiconify()
            self.lift()
            self.nb.select(self.tab_alertas)
            v.destroy()

        ttk.Button(fila, text="Ver en el programa", style="Accent.TButton", command=ver).pack(side="right")
        ttk.Button(fila, text="Cerrar", command=v.destroy).pack(side="right", padx=6)
        v.update_idletasks()
        x = self.winfo_screenwidth() - v.winfo_reqwidth() - 30
        y = self.winfo_screenheight() - v.winfo_reqheight() - 80
        v.geometry(f"+{x}+{y}")

    def _a_cambiar_auto(self):
        self.cfg["auto_escaneo"] = bool(self.a_auto.get())
        m.guardar_config(self.cfg)
        self._programar_escaneo()
        if self.a_auto.get():
            self.estado.set(f"Vigilancia automática activada: cada {self.cfg.get('intervalo_min', 60)} min.")

    def _programar_escaneo(self):
        if self._id_escaneo:
            self.after_cancel(self._id_escaneo)
            self._id_escaneo = None
        if self.cfg.get("auto_escaneo"):
            minutos = max(5, int(self.cfg.get("intervalo_min", 60)))
            self._id_escaneo = self.after(minutos * 60_000, self._escaneo_automatico)

    def _escaneo_automatico(self):
        self._id_escaneo = None
        self._a_escanear(automatico=True)
        self._programar_escaneo()

    # =====================================================================
    # 6) CONFIGURACIÓN
    # =====================================================================
    def _tab_config(self):
        t = ttk.Frame(self.nb, padding=16)
        self.nb.add(t, text="Configuración")
        g = ttk.LabelFrame(t, text="  Región  ", padding=12)
        g.pack(fill="x")
        ttk.Label(g, text="País:").grid(row=0, column=0, sticky="w")
        self.c_pais = ttk.Combobox(g, values=list(PAISES), state="readonly", width=24)
        actual = next((k for k, v in PAISES.items() if v == self.cfg.get("pais", "MX")), "MX – México")
        self.c_pais.set(actual)
        self.c_pais.grid(row=0, column=1, sticky="w", padx=8, pady=3)
        ttk.Label(g, text="Idioma de Google:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.c_idioma = ttk.Combobox(g, values=["es-419", "es", "en-US"], width=10)
        self.c_idioma.set(self.cfg.get("idioma", "es-419"))
        self.c_idioma.grid(row=0, column=3, sticky="w", padx=8)
        ttk.Label(g, text="Zona horaria (minutos detrás de UTC):").grid(row=0, column=4, sticky="w", padx=(20, 0))
        self.c_tz = ttk.Spinbox(g, from_=-720, to=720, increment=60, width=6)
        self.c_tz.set(str(self.cfg.get("zona_horaria_min", 360)))
        self.c_tz.grid(row=0, column=5, sticky="w", padx=8)
        ttk.Label(g, text="CDMX = 360", style="Sub.TLabel").grid(row=0, column=6, sticky="w")

        k = ttk.LabelFrame(t, text="  Claves de API (opcionales, gratis)  ", padding=12)
        k.pack(fill="x", pady=12)
        ttk.Label(k, text="YouTube Data API v3:").grid(row=0, column=0, sticky="w")
        self.c_yt = ttk.Entry(k, width=52, show="•")
        self.c_yt.insert(0, self.cfg.get("youtube_api_key", ""))
        self.c_yt.grid(row=0, column=1, padx=8, pady=4, sticky="w")
        ttk.Button(k, text="¿Cómo la consigo?", command=lambda: webbrowser.open(
            "https://console.cloud.google.com/apis/library/youtube.googleapis.com")).grid(row=0, column=2)
        ttk.Label(k, text="Pinterest (token de acceso):").grid(row=1, column=0, sticky="w")
        self.c_pin = ttk.Entry(k, width=52, show="•")
        self.c_pin.insert(0, self.cfg.get("pinterest_token", ""))
        self.c_pin.grid(row=1, column=1, padx=8, pady=4, sticky="w")
        ttk.Button(k, text="¿Cómo lo consigo?", command=lambda: webbrowser.open(
            "https://developers.pinterest.com/apps/")).grid(row=1, column=2)
        self.c_ver = tk.BooleanVar(value=False)
        ttk.Checkbutton(k, text="Mostrar claves", variable=self.c_ver, command=lambda: [
            e.config(show="" if self.c_ver.get() else "•") for e in (self.c_yt, self.c_pin)]).grid(
            row=2, column=1, sticky="w", padx=8)

        a = ttk.LabelFrame(t, text="  Alertas  ", padding=12)
        a.pack(fill="x")
        ttk.Label(a, text="Escanear cada (minutos):").grid(row=0, column=0, sticky="w")
        self.c_int = ttk.Spinbox(a, from_=5, to=1440, increment=5, width=6)
        self.c_int.set(str(self.cfg.get("intervalo_min", 60)))
        self.c_int.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(a, text="Sensibilidad (fuerza mínima para avisar):").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.c_z = ttk.Spinbox(a, from_=1.0, to=5.0, increment=0.5, width=5)
        self.c_z.set(str(self.cfg.get("umbral_z", 2.0)))
        self.c_z.grid(row=0, column=3, sticky="w", padx=8)
        ttk.Label(a, text="1.5 = avisa más seguido · 3 = solo picos fuertes", style="Sub.TLabel").grid(
            row=0, column=4, sticky="w")
        self.c_sonido = tk.BooleanVar(value=bool(self.cfg.get("sonido", True)))
        ttk.Checkbutton(a, text="Sonido al detectar un pico", variable=self.c_sonido).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        b = ttk.Frame(t)
        b.pack(fill="x", pady=14)
        ttk.Button(b, text="Guardar configuración", style="Accent.TButton", command=self._c_guardar).pack(side="left")
        ttk.Button(b, text="Abrir carpeta de datos", command=self._c_carpeta).pack(side="left", padx=8)

        ayuda = (
            "QUÉ HACE CADA FUENTE\n"
            "• Google Trends (sin clave): interés de búsqueda 0-100, comparación de hasta 5 términos, búsquedas que "
            "suben y tendencias del día. Si consultas muy seguido, Google pide esperar unos minutos.\n"
            "• Autocompletado de Google (sin clave): ideas de palabras clave reales, como alternativa gratuita a "
            "Keyword Planner (Keyword Planner da volúmenes exactos, pero exige cuenta de Google Ads con gasto).\n"
            "• Google Noticias (sin clave): cuántas notas mencionan tu tema por día.\n"
            "• YouTube Data API (clave gratis): en console.cloud.google.com crea un proyecto → habilita "
            "«YouTube Data API v3» → Credenciales → Crear clave de API. Alcanza para ~100 búsquedas al día.\n"
            "• Pinterest Trends (token): en developers.pinterest.com crea una app, pide acceso a la API y genera un "
            "token con permiso de lectura. Los resultados muestran qué ideas crecen antes de volverse masivas.\n"
            "• Mis datos: exporta tus ventas o tu reporte de Google Analytics/Mixpanel a CSV o Excel y ábrelo en "
            "la pestaña «Mis datos».\n\n"
            f"Tus claves y tu historial se guardan solo en esta PC: {m.APP_DIR}"
        )
        ttk.Label(t, text=ayuda, justify="left", wraplength=1200, style="Sub.TLabel").pack(anchor="w")

    def _c_guardar(self):
        try:
            self.cfg.update({
                "pais": PAISES[self.c_pais.get()],
                "idioma": self.c_idioma.get().strip() or "es-419",
                "zona_horaria_min": int(self.c_tz.get()),
                "youtube_api_key": self.c_yt.get().strip(),
                "pinterest_token": self.c_pin.get().strip(),
                "intervalo_min": max(5, int(self.c_int.get())),
                "umbral_z": float(self.c_z.get()),
                "sonido": bool(self.c_sonido.get()),
            })
        except ValueError:
            messagebox.showwarning(m.APP_NOMBRE, "Revisa que los números estén bien escritos.")
            return
        m.guardar_config(self.cfg)
        self._nuevo_cliente_trends()
        self._actualizar_lbl_pais()
        self.a_chk.config(text=f"Escanear solo cada {self.cfg['intervalo_min']} min")
        self._programar_escaneo()
        messagebox.showinfo(m.APP_NOMBRE, "Configuración guardada.")

    def _c_carpeta(self):
        os.makedirs(m.APP_DIR, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(m.APP_DIR)  # noqa: S606 (solo Windows)
        else:
            messagebox.showinfo(m.APP_NOMBRE, m.APP_DIR)


def main():
    if sys.platform == "win32":
        try:  # texto nítido en pantallas con escala (125%, 150%…)
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    try:
        App().mainloop()
    except Exception:  # noqa: BLE001
        ruta = registrar_error(traceback.format_exc())
        try:
            messagebox.showerror(m.APP_NOMBRE, f"El programa no pudo iniciar.\nDetalle en:\n{ruta}")
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()
