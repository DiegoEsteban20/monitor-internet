@echo off
chcp 65001 >NUL
cd /d "%~dp0"
where py >NUL 2>&1 && (set PY=py) || (set PY=python)
%PY% monitor_internet.py --reporte
