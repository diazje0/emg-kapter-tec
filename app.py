"""EMG Kapter-TEC — aplicación de procesamiento y visualización (Streamlit).

Ejecutar:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="EMG Kapter-TEC", page_icon="💪", layout="wide")

paginas = st.navigation([
    st.Page("paginas/inicio.py", title="Inicio", icon="🏠", default=True),
    st.Page("paginas/procesamiento.py", title="Procesamiento", icon="📂"),
    st.Page("paginas/en_vivo.py", title="En vivo (ESP32)", icon="📡"),
    st.Page("paginas/termografia.py", title="Termografía", icon="🌡️"),
])
paginas.run()
