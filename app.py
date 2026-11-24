"""EMG Kapter-TEC — aplicación de procesamiento y visualización (Streamlit).

Ejecutar:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="EMG Kapter-TEC", page_icon=":material/monitor_heart:", layout="wide")

paginas = st.navigation([
    st.Page("paginas/inicio.py", title="Inicio", icon=":material/home:", default=True),
    st.Page("paginas/procesamiento.py", title="Procesamiento", icon=":material/analytics:"),
    st.Page("paginas/en_vivo.py", title="En vivo (ESP32)", icon=":material/sensors:"),
    st.Page("paginas/termografia.py", title="Termografía", icon=":material/thermostat:"),
])
paginas.run()
