# Radar de Tendencias Pro

Programa para Windows que vigila las tendencias **de tu mercado** (salones de fiestas, oficinas, cafeterías o el que elijas) en Google, YouTube, Pinterest, las noticias y tus propias ventas, y te avisa cuando algo se dispara.

**[Descargar para Windows](https://github.com/danimakerbro-cloud/radar-tendencias-pro/releases/latest/download/RadarTendenciasPro-Setup.exe)** · [Página del programa](https://danimakerbro-cloud.github.io/radar-tendencias-pro/) · [Todas las versiones](https://github.com/danimakerbro-cloud/radar-tendencias-pro/releases)

Desarrollado por Daniel Belmont, CEO de Obsidiana Technology.

## Qué hace

1. **Mi mercado**: escribes tu giro y el programa propone palabras clave reales de Google, separadas en *para vender*, *ideas* y *probablemente no* (informativas, de otros países, ambiguas como «xview» para «xv»).
2. **Analizar mi mercado** (barra de avance con pasos): cada palabra con su propia curva y veredicto; búsquedas que despegan separadas por tipo; lo que pregunta la gente; temas de hoy; noticias; videos de YouTube; Pinterest.
3. **Comparar palabras**, **Noticias y videos**, **Mis ventas** (CSV/Excel con pronóstico) y **Alertas** automáticas.

Fuentes: Google Trends, autocompletado de Google, Google Trending Now, Google Noticias, YouTube Data API y Pinterest Trends (estas dos con clave opcional).

## Cómo publicar una versión nueva

1. Haz los cambios en el código y súbelos a `main`.
2. En GitHub entra a **Releases → Draft a new release**, escribe una etiqueta nueva (por ejemplo `v1.1.0`), un título y da **Publish release**.
3. GitHub Actions (`.github/workflows/instalador.yml`) compila el programa en Windows, crea el instalador `RadarTendenciasPro-Setup.exe` con Inno Setup y la versión portátil `.zip`, y los agrega a esa versión (tarda unos 10 minutos).
4. La página de descarga y el aviso de actualización dentro del programa toman la versión nueva automáticamente.

También puedes correrlo a mano: pestaña **Actions** → **Crear instalador** → **Run workflow** (crea los archivos sin publicar la versión).

## Página web

La página está en `docs/index.html` y se publica sola con GitHub Pages (`.github/workflows/pagina.yml`) cada vez que cambia.
Requisito único: **Settings → Pages → Source: GitHub Actions**.

## Crear el instalador en tu propia PC (sin GitHub)

Doble clic en `CREAR_INSTALADOR.bat`. Instala lo que haga falta (Python, librerías, PyInstaller e Inno Setup) y deja el instalador en `salida\RadarTendenciasPro-Setup.exe`.

Para abrir el programa sin instalarlo, mientras lo modificas: `1_ABRIR_PROGRAMA.bat`.

Para compilar y probar en GitHub sin publicar una versión, sube los cambios a la rama `prueba`. Para publicar sin entrar a la página de GitHub, cambia `APP_VERSION` en `motor.py` y sube a la rama `publicar`.

## Estructura

```
app.py                  arranque: abre la ventana (pywebview / WebView2); --prueba hace una autoprueba con internet
servidor.py             servidor local 127.0.0.1 con las acciones de la interfaz y los trabajos con avance
analisis.py             análisis del mercado: veredictos por palabra, clasificación de búsquedas, sugerencias
motor.py                fuentes de datos (Google Trends, autocompletado, noticias, YouTube, Pinterest) y ventas
ui/                     interfaz (HTML, CSS y JavaScript, sin dependencias)
instalador/*.iss        script del instalador (Inno Setup)
docs/                   página de descarga (GitHub Pages)
.github/workflows/      compilación, pruebas y publicación
```

Las claves de API, los mercados y el historial se guardan solo en la PC del usuario, en `%APPDATA%\RadarTendenciasPro`.
