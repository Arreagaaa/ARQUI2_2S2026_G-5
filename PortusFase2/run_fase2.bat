@echo off
REM Script de inicio rapido para PORTUS Fase 2 en Windows
cd /d "%~dp0\.."
echo =========================================================
echo       Iniciando PORTUS Fase 2 - Terminal Portuaria
echo =========================================================

REM Detectar ejecutable de Python con dependencias instaladas
set PYTHON_EXE=python
if exist "C:\Users\crjav\AppData\Local\Programs\Python\Python313\python.exe" (
    set "PYTHON_EXE=C:\Users\crjav\AppData\Local\Programs\Python\Python313\python.exe"
)

"%PYTHON_EXE%" PortusFase2\run_fase2.py %*
