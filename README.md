# Radar de Tendencias Pro

Programa para Windows que te muestra **lo que se está haciendo viral** hoy, en tu país, en varios países o en todo el mundo, con tendencias de inteligencia artificial, los mejores hashtags para TikTok y Facebook y copys listos para publicidad.

**[Descargar para Windows](https://github.com/danimakerbro-cloud/radar-tendencias-pro/releases/latest/download/RadarTendenciasPro-Setup.exe)** · [Página del programa](https://danimakerbro-cloud.github.io/radar-tendencias-pro/) · [Todas las versiones](https://github.com/danimakerbro-cloud/radar-tendencias-pro/releases)

Desarrollado por Daniel Belmont, CEO de Obsidiana Technology.

## Qué hace

| Apartado | Qué muestra |
|---|---|
| **Virales ahora** | Lo más buscado hoy en Google, los videos más vistos en YouTube y lo que crece en Pinterest, con la red de origen en cada dato. Arriba, los temas que suben en varias redes a la vez. Se actualiza solo cada 15 minutos. Filtro opcional por palabra. |
| **Por lugar** | Un país, varios a la vez o todo el mundo (17 países). Compara lado a lado y marca lo que es tendencia en varios lugares. |
| **Tendencias de IA** | Cómo van ChatGPT, Gemini, Claude, Midjourney, Sora, Copilot, DeepSeek, Grok, Perplexity, agentes, video e imágenes con IA; lo que busca la gente sobre IA; videos y noticias. |
| **Copys e ideas** | Textos para anuncio, publicación, Reel/TikTok o historia en varios tonos, con guion de video y hashtags, a partir de la tendencia que elijas. Se arman con plantillas dentro del programa (no usan una IA externa). |
| **Hashtags** | Los mejores hashtags del momento por red (TikTok, Facebook, Instagram, YouTube), sacados de lo viral y de lo que pegues. |
| **TikTok y Facebook** | Abre TikTok y Facebook en tu navegador; copias lo que ves (Ctrl+A, Ctrl+C), lo pegas y el programa saca hashtags y temas. TikTok y Facebook no tienen una API pública de tendencias, por eso funciona así. |
| **Ajustes** | País e idioma, y claves opcionales de YouTube, Pinterest e Instagram. |

Fuentes: Google Trends, Google Trending Now, Google Noticias, YouTube Data API, Pinterest Trends e Instagram Graph API (estas tres con clave opcional).

## Cómo publicar una versión nueva

1. Haz los cambios en el código y súbelos a `main`.
2. En GitHub entra a **Releases → Draft a new release**, escribe una etiqueta nueva (por ejemplo `v2.1.0`), un título y da **Publish release**.
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
analisis.py             virales, por lugar, IA, copys y hashtags: veredictos por palabra y temas que se repiten
motor.py                fuentes de datos (Google Trends, Trending Now, noticias, YouTube, Pinterest, Instagram) y países
ui/                     interfaz (HTML, CSS y JavaScript, sin dependencias)
instalador/*.iss        script del instalador (Inno Setup)
docs/                   página de descarga (GitHub Pages)
.github/workflows/      compilación, pruebas y publicación
```

Las claves de API y lo que pegues de TikTok y Facebook se guardan solo en la PC del usuario, en `%APPDATA%\RadarTendenciasPro`.
