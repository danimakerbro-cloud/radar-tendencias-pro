@echo off
setlocal
cd /d "%~dp0"
title Radar de Tendencias Pro

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto :sinpython

if not exist ".venv\Scripts\python.exe" (
    echo Preparando el programa por primera vez, tarda de 1 a 3 minutos...
    %PY% -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:sinpython
echo.
echo  No encontre Python en esta PC.
echo  1. Se abrira la pagina de descarga: instala la version mas reciente.
echo  2. IMPORTANTE: marca la casilla "Add python.exe to PATH" al instalar.
echo  3. Vuelve a abrir este archivo.
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:error
echo.
echo  Algo fallo al instalar. Revisa tu conexion a internet y vuelve a intentar.
echo  Si se repite, borra la carpeta .venv y abre este archivo otra vez.
pause
exit /b 1
