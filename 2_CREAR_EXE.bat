@echo off
setlocal
cd /d "%~dp0"
title Crear RadarTendenciasPro.exe

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    echo No encontre Python. Abre primero 1_ABRIR_PROGRAMA.bat para ver como instalarlo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Preparando entorno...
    %PY% -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

echo Instalando PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller || goto :error

echo Creando el .exe, tarda de 2 a 5 minutos...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name RadarTendenciasPro --icon radar.ico --add-data "radar.ico;." app.py || goto :error

copy /y ejemplo_ventas.csv dist\ >nul
echo.
echo  LISTO. Tu programa esta en:
echo  %cd%\dist\RadarTendenciasPro.exe
echo  Puedes copiar ese .exe a cualquier PC con Windows 10 u 11, no necesita Python.
echo.
explorer dist
pause
exit /b 0

:error
echo.
echo  Algo fallo. Revisa tu conexion a internet y vuelve a intentar.
pause
exit /b 1
