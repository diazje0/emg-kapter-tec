from datetime import datetime
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from emg.envivo import Receptor, ReceptorSerie, Simulador

TOMAS = ["1_reposo", "1_contracciones", "ejercicio", "2_reposo", "2_contracciones", "3_reposo", "3_contracciones"]
DUR_DEF = {"reposo": 30, "contracciones": 26, "ejercicio": 60}   # segundos desde el primer pitido
PITIDOS_CONTR = (0, 9, 18)                                       # pitidos sugeridos en las contracciones (s)
tipo = lambda toma: toma.split("_", 1)[-1] if "_" in toma else toma
CARPETA = Path(__file__).resolve().parent.parent / "registros"

st.title(":material/sensors: Señal en vivo (ESP32)")
st.caption("Funciona cuando la app corre en **tu computadora** (`streamlit run app.py`), con la ESP32 conectada por USB "
           "o por Bluetooth (en ambos casos aparece como un puerto COM en Windows).")

rx: Receptor | None = st.session_state.get("rx")

# ------------------------------------------------------------------ conexión
with st.sidebar:
    st.header(":material/usb: Conexión")
    modo = st.radio("Fuente", ["ESP32 (USB o Bluetooth)", "Simulador (sin hardware)"],
                    help="Por Bluetooth: empareja **EMG_KapterTEC** en Windows y elige aquí el puerto COM *saliente* que creó.")
    placa = st.selectbox("Placa", ["ESP32 DevKit (convencional)", "ESP32-C3"],
                         help="Solo cambia el límite de saturación del aviso: ~3.1 V en la ESP32 DevKit, ~2.5 V en la C3.")
    st.session_state["lim_adc"], st.session_state["lim_min"] = (3050, 160) if placa.startswith("ESP32 DevKit") else (2450, 20)
    puerto = None
    if modo.startswith("ESP32"):
        try:
            from serial.tools import list_ports
            puertos = [p.device for p in list_ports.comports()]
        except Exception:
            puertos = []
        puerto = st.selectbox("Puerto", puertos or ["(no se encontraron puertos)"])
        baudios = st.selectbox("Velocidad (baudios)", [921600, 115200], help="Debe coincidir con BAUDIOS del firmware (921600). En la C3 con USB nativo no importa.")
    with st.expander("Duración de las tomas", icon=":material/timer:"):
        st.caption("Segundos que se graban **a partir del primer pitido** (además se guardan 2 s previos).")
        dur = {k: st.number_input(f"{k.capitalize()} (s)", 5, 180, v, 1, key=f"dur_{k}") for k, v in DUR_DEF.items()}
    seg_vista = st.slider("Segundos en pantalla", 2, 10, 5)
    escala = st.slider("Escala vertical (± mV en el ADC)", 100, 1600, 800, 50)

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
            st.session_state.pop("ultima", None)
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
if "_siguiente" in st.session_state:                 # después de guardar, pasa a la siguiente toma
    st.session_state["toma"] = st.session_state.pop("_siguiente")
with st.expander("Cómo grabar una sesión", icon=":material/help:"):
    st.markdown("1. **Conectar** (barra izquierda) y elige la **toma**.  \n"
                "2. **Grabar**: la app queda *lista*, pero todavía no guarda nada.  \n"
                "3. **Pitido**: suena el buzzer y **ahí empieza la grabación** (con 2 s previos).  \n"
                "4. En las contracciones, presiona **Pitido** otra vez en cada contracción (sugerido a los 9 y 18 s).  \n"
                "5. Al cumplirse la duración, **se detiene y guarda sola** y pasa a la siguiente toma.  \n"
                "6. Al final, ve a **Procesamiento** y sube los 7 archivos de la carpeta `registros/`.")
toma = st.selectbox("¿Qué toma vas a grabar?", TOMAS, key="toma")
def guardar(toma_g, filas):
    if not filas:
        return
    CARPETA.mkdir(exist_ok=True)
    csv = Receptor.a_csv(filas)
    (CARPETA / f"{toma_g}_{datetime.now():%Y%m%d_%H%M%S}.csv").write_text(csv)
    st.session_state["ultima"] = (f"{toma_g}.csv", csv, len(filas))
    i = TOMAS.index(toma_g)
    if i + 1 < len(TOMAS):
        st.session_state["_siguiente"] = TOMAS[i + 1]


ocupado = rx.armado or rx.grabando
b1, b2, b3, b4 = st.columns(4)
if b1.button("Pitido" + (" · iniciar" if rx.armado else ""), icon=":material/notifications_active:", type="primary" if rx.armado else "secondary",
             use_container_width=True, help="La ESP32 suena y guarda la marca (latencia). Si la toma está lista, aquí empieza a grabar."):
    rx.marcar()
if b2.button("Grabar", icon=":material/radio_button_checked:", disabled=ocupado, use_container_width=True,
             help="Deja la toma lista: empieza a grabar con el siguiente pitido y se detiene sola al cumplir su duración."):
    rx.armar(toma, dur[tipo(toma)])
    st.session_state.pop("ultima", None)
    st.rerun()
if b3.button("Cancelar" if rx.armado else "Detener y guardar", icon=":material/close:" if rx.armado else ":material/save:",
             disabled=not ocupado, use_container_width=True, help="Detiene antes de tiempo y guarda lo grabado (o cancela si aún no empieza)."):
    era_armado, toma_g = rx.armado, rx.toma or toma
    filas = rx.detener_grabacion()
    if not era_armado:
        guardar(toma_g, filas)
    st.rerun()
if b4.button("Reiniciar pantalla", icon=":material/restart_alt:", disabled=ocupado, use_container_width=True,
             help="Borra la señal mostrada y el aviso de la última toma. No cierra la conexión."):
    rx.limpiar()
    st.session_state.pop("ultima", None)
    st.rerun()

if "ultima" in st.session_state:
    nombre, csv, n = st.session_state["ultima"]
    st.success(f"Toma guardada en la carpeta `registros/` ({n} muestras). También puedes descargarla:")
    st.download_button(f"Descargar {nombre}", csv, nombre, "text/csv", icon=":material/download:")


# ------------------------------------------------------------------ gráfica en vivo
@st.fragment(run_every=0.5)
def vista():
    if rx.completa:                                   # se cumplió la duración: guardar y pasar a la siguiente toma
        toma_g = rx.toma
        guardar(toma_g, rx.detener_grabacion())
        st.rerun()
    if st.session_state.get("_estado_botones") != (rx.armado, rx.grabando):   # actualizar botones al empezar a grabar
        st.session_state["_estado_botones"] = (rx.armado, rx.grabando)
        st.rerun()
    d = rx.ventana()
    if rx.grabando:
        seg, total = rx.transcurrido(), rx.duracion
        st.progress(min(seg / total, 1.0), text=f":red[:material/fiber_manual_record:] **GRABANDO {rx.toma}** · {seg:4.1f} s de {total} s")
        if tipo(rx.toma) == "contracciones":
            n_pit = int(sum(f[3] for f in rx.grabacion))
            if n_pit < len(PITIDOS_CONTR):
                falta = PITIDOS_CONTR[n_pit] - seg
                st.markdown(f"#### Pitido {n_pit + 1} de 3 " + ("· **¡AHORA!**" if falta <= 0.5 else f"en **{falta:.0f} s**"))
            else:
                st.markdown("#### 3 pitidos dados · esperar a que termine")
    elif rx.armado:
        st.info(f"**{rx.toma} lista.** Presiona **Pitido** para empezar a grabar ({rx.duracion} s).", icon=":material/hourglass_top:")
    estado = ":blue[:material/wifi_tethering: recibiendo]" if rx.activo else ":gray[:material/link_off: desconectado]"
    st.markdown(f"**{estado}** · muestras recibidas: {rx.muestras:,}")
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
    satur = (v.min() < st.session_state.get("lim_min", 160)) or (v.max() > st.session_state.get("lim_adc", 3050))
    c = st.columns(3)
    c[0].metric("RMS TFL (últimos 0.5 s, mV ADC)", f"{rms[0]:.0f}")
    c[1].metric("RMS aductor (últimos 0.5 s, mV ADC)", f"{rms[1]:.0f}")
    c[2].metric("Muestreo", f"{fs:.0f} Hz")
    if satur:
        st.warning("La señal llega al límite del ADC de la ESP32: baja la ganancia o ajusta el offset.", icon=":material/warning:")


vista()
