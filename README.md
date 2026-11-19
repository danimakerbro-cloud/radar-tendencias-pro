# Radar de Tendencias Pro

Programa para Windows que vigila las tendencias **de tu mercado** (salones de fiestas, oficinas, cafeterías o el que elijas) en Google, YouTube, Pinterest, las noticias y tus propias ventas, y te avisa cuando algo se dispara.

**[Descargar para Windows](https://github.com/danimakerbro-cloud/radar-tendencias-pro/releases/latest/download/RadarTendenciasPro-Setup.exe)** · [Página del programa](https://danimakerbro-cloud.github.io/radar-tendencias-pro/) · [Todas las versiones](https://github.com/danimakerbro-cloud/radar-tendencias-pro/releases)

Desarrollado por Daniel Belmont, CEO de Obsidiana Technology.

## Qué hace

| Pestaña | Qué mide | Fuente |
|---|---|---|
| Mi mercado | Define tu giro, sus palabras clave y lo que hay que ignorar | Sugerencias del autocompletado de Google |
| Búsquedas | Interés 0-100, búsquedas que suben, ideas de palabras clave | Google Trends, autocompletado de Google |
| Tendencias del día | Lo que creció esta semana en tu mercado; temas de hoy que lo tocan | Google Trending Now, Pinterest Trends |
| Redes y menciones | Videos que más rápido ganan vistas; notas por día | YouTube Data API, Google Noticias |
| Mis datos | Tendencia, crecimiento, pronóstico y ranking de productos | Tu CSV/Excel, Google Analytics |
| Alertas | Avisa con ventana y sonido cuando un término se dispara | Google Trends + Google Noticias |

## Cómo publicar una versión nueva

1. Haz los cambios en el código y súbelos a `main`.
2. Crea una etiqueta con el número de versión y súbela:
   ```
   git tag v1.1.0
   git push origin v1.1.0
   ```
3. GitHub Actions (`.github/workflows/instalador.yml`) compila el programa en Windows, crea el instalador `RadarTendenciasPro-Setup.exe` con Inno Setup y la versión portátil `.zip`, y los publica en **Releases**.
4. La página de descarga y el aviso de actualización dentro del programa toman la versión nueva automáticamente.

También puedes lanzarlo a mano: pestaña **Actions** → **Crear instalador** → **Run workflow** (crea los archivos sin publicar la versión).

## Página web

La página está en `docs/index.html` y se publica sola con GitHub Pages (`.github/workflows/pagina.yml`) cada vez que cambia.
Requisito único: **Settings → Pages → Source: GitHub Actions**.

## Crear el instalador en tu propia PC (sin GitHub)

Doble clic en `CREAR_INSTALADOR.bat`. Instala lo que haga falta (Python, librerías, PyInstaller e Inno Setup) y deja el instalador en `salida\RadarTendenciasPro-Setup.exe`.

Para abrir el programa sin instalarlo, mientras lo modificas: `1_ABRIR_PROGRAMA.bat`.

## Estructura

```
app.py                  interfaz (Tkinter + matplotlib)
motor.py                fuentes de datos, mercado, análisis y alertas
instalador/*.iss        script del instalador (Inno Setup)
docs/                   página de descarga (GitHub Pages)
.github/workflows/      compilación del instalador y publicación de la página
```

Las claves de API, los mercados y el historial se guardan solo en la PC del usuario, en `%APPDATA%\RadarTendenciasPro`.
