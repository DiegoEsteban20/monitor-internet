@echo off
chcp 65001 >NUL
cd /d "%~dp0"
where py >NUL 2>&1 && (set PY=py) || (set PY=python)
echo Monitoreando. Deja esta ventana abierta mientras juegas. Cierra la ventana o Ctrl+C para detener.
%PY% monitor_internet.py --continuo
