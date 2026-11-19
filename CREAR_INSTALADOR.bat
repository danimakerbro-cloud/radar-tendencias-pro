@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Crear instalador - Radar de Tendencias Pro

echo.
echo  ============================================================
echo    Crear el instalador de Radar de Tendencias Pro
echo    La primera vez tarda de 5 a 10 minutos. No cierres esta ventana.
echo  ============================================================
echo.

rem ------------------------------------------------------------ 1. Python
call :buscar_python
if defined PY goto :python_ok
echo [1/4] No encontre Python. Instalandolo con winget...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :buscar_python
if not defined PY goto :sin_python
:python_ok
echo [1/4] Python listo: %PY%

rem ------------------------------------------------------------ 2. Librerias
if exist ".venv\Scripts\python.exe" goto :venv_ok
"%PY%" -m venv .venv
if errorlevel 1 goto :error
:venv_ok
echo [2/4] Instalando librerias, puede tardar unos minutos...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

rem ------------------------------------------------------------ 3. Programa
echo [3/4] Creando el programa...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name RadarTendenciasPro --icon radar.ico --add-data "radar.ico;." app.py
if errorlevel 1 goto :error

rem ------------------------------------------------------------ 4. Instalador
call :buscar_iscc
if defined ISCC goto :iscc_ok
echo [4/4] Instalando Inno Setup con winget, acepta si Windows pide permiso...
winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
call :buscar_iscc
if not defined ISCC goto :sin_inno
:iscc_ok
echo [4/4] Creando el instalador...
"%ISCC%" /Q "instalador\RadarTendenciasPro.iss"
if errorlevel 1 goto :error

echo.
echo  ============================================================
echo    LISTO. Tu instalador esta en:
echo    %cd%\salida\RadarTendenciasPro-Setup.exe
echo.
echo    Abrelo para instalar el programa. Despues lo encuentras en el
echo    menu Inicio y en el escritorio como "Radar de Tendencias Pro".
echo    Puedes copiar ese instalador a cualquier PC con Windows 10 u 11.
echo  ============================================================
echo.
explorer salida
pause
exit /b 0

rem ============================================================ funciones
:buscar_python
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python313\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe") do if not defined PY if exist "%%~P" set "PY=%%~P"
if defined PY exit /b 0
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY if exist "%PY%" exit /b 0
set "PY="
for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY if exist "%PY%" exit /b 0
set "PY="
exit /b 0

:buscar_iscc
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
exit /b 0

:sin_python
echo.
echo  No pude instalar Python automaticamente.
echo  1. Se abrira la pagina de descarga: instala Python 3.12 o mas nuevo.
echo  2. IMPORTANTE: marca la casilla "Add python.exe to PATH".
echo  3. Vuelve a abrir este archivo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:sin_inno
echo.
echo  No pude instalar Inno Setup automaticamente.
echo  1. Se abrira la pagina: descarga e instala "Inno Setup 6".
echo  2. Vuelve a abrir este archivo. Ya no repite lo que estaba listo.
start "" https://jrsoftware.org/isdl.php
pause
exit /b 1

:error
echo.
echo  Algo fallo. Revisa tu conexion a internet y vuelve a abrir este archivo.
echo  Si se repite, toma foto de esta ventana y mandamela.
pause
exit /b 1
