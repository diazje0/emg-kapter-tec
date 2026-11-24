import streamlit as st

st.title("💪 EMG Kapter-TEC")
st.caption("Sistema wearable de sEMG — abducción de cadera · BI2005B · Tecnológico de Monterrey")

st.markdown(
    """
Esta aplicación procesa y visualiza las señales de electromiografía de superficie (sEMG) del
**tensor de la fascia lata (TFL)** y del **aductor largo**, y las relaciona con la **termografía** tomada en Kapter.

| Página | Para qué sirve |
|---|---|
| 📂 **Procesamiento** | Sube los 7 CSV de una sesión (osciloscopio o ESP32) y obtén RMS, frecuencia mediana, tiempo de activación, latencia y estadística, con gráficas y tablas descargables. |
| 📡 **En vivo (ESP32)** | Conecta la ESP32-C3 por USB, mira la señal en tiempo real, marca el inicio de cada contracción con el pitido y graba cada toma en el formato que usa la app. |
| 🌡️ **Termografía** | Captura la temperatura de cada región (T0–T2) y compárala con los indicadores de fatiga EMG. |
"""
)

st.subheader("Protocolo de medición")
c1, c2, c3 = st.columns(3)
c1.markdown("**1 · Llegada (inicio)**\n\n- Termograma T0\n- 30 s en reposo → `1_reposo`\n- 3 contracciones de 3 s (6 s de descanso) → `1_contracciones`")
c2.markdown("**2 · Post-ejercicio (pico)**\n\n- 1 min de abducción con polaina → `ejercicio`\n- Termograma T1\n- 30 s en reposo → `2_reposo`\n- 3 contracciones → `2_contracciones`")
c3.markdown("**3 · Post-enfriamiento (recuperación)**\n\n- 2 min caminando + 1 min quieto\n- Termograma T2\n- 30 s en reposo → `3_reposo`\n- 3 contracciones → `3_contracciones`")

st.info("Para probar sin datos, entra a **Procesamiento** y presiona *Cargar datos de ejemplo*.", icon="💡")
