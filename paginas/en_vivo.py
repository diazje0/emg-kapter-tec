from datetime import datetime
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from emg.envivo import Receptor, ReceptorSerie, Simulador

TOMAS = ["1_reposo", "1_contracciones", "ejercicio", "2_reposo", "2_contracciones", "3_reposo", "3_contracciones"]
CARPETA = Path(__file__).resolve().parent.parent / "registros"

st.title(":material/sensors: Señal en vivo (ESP32)")
st.caption("Funciona cuando la app corre en **tu computadora** (`streamlit run app.py`), con la ESP32 conectada por USB "
           "(aparece como un puerto COM en Windows o /dev/ttyACM… en Mac/Linux).")

rx: Receptor | None = st.session_state.get("rx")

# ------------------------------------------------------------------ conexión
with st.sidebar:
    st.header(":material/usb: Conexión")
    modo = st.radio("Fuente", ["ESP32-C3 (USB)", "Simulador (sin hardware)"])
    puerto = None
    if modo.startswith("ESP32"):
        try:
            from serial.tools import list_ports
            puertos = [p.device for p in list_ports.comports()]
        except Exception:
            puertos = []
        puerto = st.selectbox("Puerto", puertos or ["(no se encontraron puertos)"])
        baudios = st.selectbox("Velocidad (USB)", [921600, 115200], help="Con el USB nativo del ESP32-C3 la velocidad no importa.")
    seg_vista = st.slider("Segundos en pantalla", 2, 10, 5)
    escala = st.slider("Escala vertical (± mV en el ADC)", 100, 1300, 800, 50)

    c1, c2 = st.columns(2)
    if c1.button("Conectar", type="primary", disabled=bool(rx and rx.activo), use_container_width=True):
        if modo.startswith("Simulador"):
            rx = Simulador()
        elif puerto and not puerto.startswith("("):
            rx = ReceptorSerie(puerto, baudios)
        else:
            st.error("Elige un puerto válido.")
            rx = None
        if rx:
            rx.iniciar()
            st.session_state["rx"] = rx
            st.rerun()
    if c2.button("Desconectar", disabled=not (rx and rx.activo), use_container_width=True):
        rx.detener()
        st.rerun()

if not rx:
    st.info("Elige la fuente y presiona **Conectar**. Para probar la página sin la ESP32, usa el **Simulador**.")
    st.stop()
if rx.error:
    st.error(f"Error de conexión: {rx.error}")

# ------------------------------------------------------------------ controles de grabación
toma = st.selectbox("¿Qué toma vas a grabar?", TOMAS)
b1, b2, b3 = st.columns(3)
if b1.button("Pitido / marca de inicio", icon=":material/notifications_active:", use_container_width=True, help="La ESP32 suena y guarda la marca para calcular la latencia."):
    rx.marcar()
if b2.button("Grabar", icon=":material/radio_button_checked:", disabled=rx.grabando, use_container_width=True):
    rx.iniciar_grabacion()
    st.rerun()
if b3.button("Detener y guardar", icon=":material/save:", disabled=not rx.grabando, use_container_width=True):
    filas = rx.detener_grabacion()
    if filas:
        CARPETA.mkdir(exist_ok=True)
        nombre = f"{toma}.csv"
        csv = Receptor.a_csv(filas)
        (CARPETA / f"{toma}_{datetime.now():%Y%m%d_%H%M%S}.csv").write_text(csv)
        st.session_state["ultima"] = (nombre, csv, len(filas))
    st.rerun()

if "ultima" in st.session_state:
    nombre, csv, n = st.session_state["ultima"]
    st.success(f"Toma guardada en la carpeta `registros/` ({n} muestras). También puedes descargarla:")
    st.download_button(f"Descargar {nombre}", csv, nombre, "text/csv", icon=":material/download:")


# ------------------------------------------------------------------ gráfica en vivo
@st.fragment(run_every=0.5)
def vista():
    d = rx.ventana()
    estado = ":red[:material/fiber_manual_record: GRABANDO]" if rx.grabando else (":blue[:material/wifi_tethering: recibiendo]" if rx.activo else ":gray[:material/link_off: desconectado]")
    n_grab = len(rx.grabacion) if rx.grabando else 0
    st.markdown(f"**{estado}** · muestras recibidas: {rx.muestras:,}" + (f" · grabadas: {n_grab:,}" if rx.grabando else ""))
    if len(d) < 10:
        st.caption("Esperando datos…")
        return
    t = (d[:, 0] - d[-1, 0]) / 1e6
    sel = t >= -seg_vista
    t, d = t[sel], d[sel]
    paso = max(1, len(t) // 4000)
    fs = 1 / np.median(np.diff(t)) if len(t) > 2 else 0
    offset = np.median(d[:, 1:3], axis=0)          # offset real de cada canal
    fig = go.Figure()
    for j, (nombre, color) in enumerate((("TFL", "#1D4E89"), ("Aductor", "#2E9BD6")), start=1):
        fig.add_scatter(x=t[::paso], y=d[::paso, j] - offset[j - 1], mode="lines",
                        line=dict(color=color, width=1), name=nombre, yaxis=f"y{'' if j == 1 else 2}")
    for tm in t[d[:, 3] == 1]:
        fig.add_vline(x=tm, line=dict(color="#0B2545", dash="dash", width=2))
    fig.update_layout(template="plotly_white", height=460, margin=dict(l=60, r=20, t=30, b=40), showlegend=True,
                      xaxis=dict(title="Tiempo (s)", range=[-seg_vista, 0]),
                      yaxis=dict(title="TFL (mV, sin offset)", domain=[0.53, 1], range=[-escala, escala]),
                      yaxis2=dict(title="Aductor (mV, sin offset)", domain=[0, 0.47], range=[-escala, escala]),
                      legend=dict(orientation="h", y=1.08, x=1, xanchor="right"))
    st.plotly_chart(fig, use_container_width=True, key="vivo")
    v = d[:, 1:3]
    rms = np.sqrt(np.mean((v[-int(max(fs, 1) * 0.5):] - v.mean(axis=0)) ** 2, axis=0))
    satur = (v.min() < 100) or (v.max() > 2450)
    c = st.columns(3)
    c[0].metric("RMS TFL (últimos 0.5 s, mV ADC)", f"{rms[0]:.0f}")
    c[1].metric("RMS aductor (últimos 0.5 s, mV ADC)", f"{rms[1]:.0f}")
    c[2].metric("Muestreo", f"{fs:.0f} Hz")
    if satur:
        st.warning("La señal llega a los límites del ADC del ESP32-C3 (≈0–2.5 V): baja la ganancia o ajusta el offset.", icon=":material/warning:")


vista()
