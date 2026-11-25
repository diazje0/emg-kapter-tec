@echo off
REM Doble clic para abrir la app EMG-Meras puntas de la flecha
cd /d "%~dp0"
echo Revisando librerias (la primera vez tarda un par de minutos)...
py -m pip install -q --disable-pip-version-check -r requirements.txt
echo.
echo Abriendo la app en el navegador. Para cerrarla, cierra esta ventana.
py -m streamlit run app.py
pause
