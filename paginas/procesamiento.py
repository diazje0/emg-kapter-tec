import io
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from emg import Parametros, leer_registro
from emg import graficas as gr
from emg.interpretacion import GLOSARIO, conclusiones
from emg.sesion import CLAVES, analizar_sesion

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = RAIZ / "datos_ejemplo"
NOMBRES = list(CLAVES.values())          # 1_reposo, 1_contracciones, ejercicio, ...
DESCRIPCION = {
    "1_reposo": "Llegada · reposo 30 s", "1_contracciones": "Llegada · 3 contracciones",
    "ejercicio": "Ejercicio · 1 min con polaina",
    "2_reposo": "Post-ejercicio · reposo", "2_contracciones": "Post-ejercicio · 3 contracciones",
    "3_reposo": "Post-enfriamiento · reposo", "3_contracciones": "Post-enfriamiento · 3 contracciones",
}

st.title(":material/analytics: Procesamiento de una sesión")

# ------------------------------------------------------------------ configuración
with st.sidebar:
    st.header(":material/tune: Configuración")
    st.caption("Ganancia total **medida** entre electrodos y el punto donde se registró la señal.")
    g_tfl = st.number_input("Ganancia TFL", min_value=1.0, value=207.87, step=0.01, format="%.2f")
    g_adu = st.number_input("Ganancia aductor largo", min_value=1.0, value=207.87, step=0.01, format="%.2f")
    with st.expander("Parámetros avanzados"):
        p = Parametros(
            ventana=st.number_input("Ventana RMS (s)", 0.1, 2.0, 0.5, 0.05),
            fc_env=st.slider("Envolvente (Hz)", 2.0, 5.0, 4.0, 0.5),
            recorte=st.number_input("Descartar al inicio (s)", 0.0, 3.0, 0.5, 0.1),
            filtrar=st.checkbox("Pasa-banda digital 20–450 Hz", True),
            notch_armonicos=st.checkbox("Quitar 60 Hz y armónicos", True),
            dur_min=st.number_input("Duración mínima de contracción (s)", 0.2, 3.0, 1.0, 0.1),
        )

# ------------------------------------------------------------------ carga de archivos
st.markdown("**1.** Sube los **7 archivos** de la sesión (o prueba con los datos de ejemplo).  \n"
            "**2.** Si un archivo no tiene el nombre de la toma (por ejemplo `scope_12.csv`), elige a cuál corresponde.  \n"
            "**3.** Presiona **Procesar**.")
c1, c2 = st.columns([3, 1])
subidos = c1.file_uploader("Archivos CSV (osciloscopio o ESP32)", type=["csv"], accept_multiple_files=True)
if c2.button("Cargar datos de ejemplo", use_container_width=True, icon=":material/science:"):
    st.session_state["usar_ejemplo"] = True
if subidos:
    st.session_state["usar_ejemplo"] = False

fuentes = {}
if st.session_state.get("usar_ejemplo"):
    fuentes = {f.stem: f for f in sorted(EJEMPLO.glob("*.csv"))}
    st.success("Usando los datos de ejemplo (señales simuladas).")
elif subidos:
    st.subheader("Asignación de archivos")
    cols = st.columns(2)
    for i, f in enumerate(subidos):
        base = Path(f.name).stem
        sugerido = next((n for n in NOMBRES if base.lower().startswith(n)), None)
        opciones = ["— sin usar —"] + NOMBRES
        sel = cols[i % 2].selectbox(f"`{f.name}`", opciones, index=opciones.index(sugerido) if sugerido else 0,
                                    format_func=lambda n: n if n.startswith("—") else f"{n}  ({DESCRIPCION[n]})", key=f"map_{f.name}")
        if sel in NOMBRES:
            if sel in fuentes:
                st.warning(f"La toma `{sel}` está asignada a más de un archivo.")
            fuentes[sel] = f

faltan = [n for n in NOMBRES if n not in fuentes]
if fuentes and faltan:
    st.caption("Sin archivo: " + ", ".join(f"`{n}`" for n in faltan) + " (se analiza lo disponible).")

if not fuentes:
    st.stop()

if st.button("Procesar", type="primary", icon=":material/play_arrow:"):
    with st.spinner("Procesando…"):
        try:
            registros = {k: leer_registro(v) for k, v in fuentes.items()}
        except Exception as e:
            st.error(f"No se pudo leer un archivo: {e}")
            st.stop()
        res, avisos = analizar_sesion(registros, {"TFL": g_tfl, "Aductor": g_adu}, p)
        st.session_state["resultados"] = res
        st.session_state["avisos"] = avisos
        st.session_state["info_registros"] = {k: (r.formato, r.fs, r.n / r.fs, list(r.canales)) for k, r in registros.items()}

res = st.session_state.get("resultados")
if not res:
    st.stop()

# ------------------------------------------------------------------ resultados
for a in st.session_state.get("avisos", []):
    st.warning(a, icon=":material/warning:")
with st.expander("Detalles de los archivos leídos"):
    st.dataframe(pd.DataFrame([dict(toma=k, formato=f, fs_Hz=round(fs, 1), duración_s=round(d, 1), canales=", ".join(c))
                               for k, (f, fs, d, c) in st.session_state["info_registros"].items()]), hide_index=True)


def tabla_resumen(R):
    df = pd.DataFrame(R.resumen)
    f = lambda m, s, d=1: f"{m:.{d}f} ± {s:.{d}f}" if np.isfinite(s) else f"{m:.{d}f}"
    return pd.DataFrame({
        "Momento": df["momento"],
        "RMS reposo (µV)": df["RMS_reposo_uV"].round(1),
        "RMS contracciones (µV)": [f(m, s) for m, s in zip(df["RMS_contr_uV"], df["RMS_contr_DE"])],
        "RMS norm. (%)": [f(m, s) for m, s in zip(df["RMS_contr_pct"], df["RMS_contr_DE_pct"])],
        "Amplitud máx. (µV)": df["amplitud_max_uV"].round(1),
        "MDF (Hz)": [f(m, s) for m, s in zip(df["MDF_Hz"], df["MDF_DE"])],
        "T. activación (s)": [f(m, s, 2) for m, s in zip(df["t_activacion_s"], df["t_activacion_DE"])],
        "Latencia (ms)": df["latencia_ms"].map(lambda v: f"{v:.0f}" if np.isfinite(v) else "N/D"),
        "Cambio RMS vs llegada (%)": df["cambio_RMS_vs_llegada_pct"].round(1),
    })


def excel(res):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for m, R in res.items():
            tabla_resumen(R).to_excel(xw, sheet_name=f"{m}_resumen", index=False)
            pd.DataFrame(R.contracciones).round(3).to_excel(xw, sheet_name=f"{m}_contracciones", index=False)
            pd.DataFrame(R.estadistica).round(4).to_excel(xw, sheet_name=f"{m}_estadistica", index=False)
            if R.ejercicio:
                pd.DataFrame([R.ejercicio]).round(3).to_excel(xw, sheet_name=f"{m}_ejercicio", index=False)
            pd.DataFrame(R.ventanas).round(3).to_excel(xw, sheet_name=f"{m}_ventanas", index=False)
    return buf.getvalue()


st.download_button("Descargar todos los resultados (Excel)", excel(res), "resultados_EMG.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:")

with st.expander("¿Qué significa cada valor?", icon=":material/help:"):
    for k, v in GLOSARIO.items():
        st.markdown(f"**{k}:** {v}")


def tabla_sencilla(R):
    df = pd.DataFrame(R.resumen)
    return pd.DataFrame({
        "Momento": df["momento"],
        "Activación (µV)": df["RMS_contr_uV"].round(0),
        "Activación (% del máximo)": df["RMS_contr_pct"].round(1),
        "Frecuencia mediana (Hz)": df["MDF_Hz"].round(1),
        "Duración de la activación (s)": df["t_activacion_s"].round(2),
        "Tiempo de reacción (ms)": df["latencia_ms"].map(lambda v: f"{v:.0f}" if np.isfinite(v) else "—"),
    })


for musculo, R in res.items():
    st.header(f":material/accessibility_new: {musculo}")
    df = pd.DataFrame(R.resumen).set_index("momento")
    cols = st.columns(len(df))
    for c, (mom, fila) in zip(cols, df.iterrows()):
        delta = None if mom == "Llegada" else f"{fila['cambio_RMS_vs_llegada_pct']:+.0f} % vs. llegada"
        c.metric(f"Activación · {mom}", f"{fila['RMS_contr_uV']:.0f} µV", delta, delta_color="off")
        c.caption(f"Frecuencia mediana: **{fila['MDF_Hz']:.1f} Hz**")

    with st.container(border=True):
        st.markdown("##### :material/lightbulb: ¿Qué nos dicen los resultados?")
        for frase in conclusiones(R, musculo):
            st.markdown(f"- {frase}")

    t1, t2, t3, t4 = st.tabs([":material/bar_chart: Comparación", ":material/show_chart: Señales",
                              ":material/directions_run: Ejercicio", ":material/table_chart: Tablas y estadística"])
    with t1:
        st.caption("Cada barra es el promedio de las 3 contracciones; la línea negra es la desviación estándar.")
        st.plotly_chart(gr.barras(R.resumen, musculo), use_container_width=True)
        with st.expander("Ver la distribución por ventanas (diagramas de caja)"):
            st.plotly_chart(gr.cajas(R.ventanas, musculo), use_container_width=True)
    with t2:
        st.caption("Gris: señal rectificada · azul: RMS · azul marino: envolvente · franjas: contracciones detectadas "
                   "con su duración.")
        for mom in [m for m in ("Llegada", "Post-ejercicio", "Post-enfriamiento") if m in R.graficas]:
            st.plotly_chart(gr.senal_contracciones(R.graficas[mom], musculo, mom), use_container_width=True)
    with t3:
        if R.ejercicio:
            e = R.ejercicio
            a, b, c = st.columns(3)
            a.metric("Activación al final del minuto", f"{e['rms_ultimos']:.0f} µV", f"{e['rms_cambio_pct']:+.1f} % vs. inicio", delta_color="off")
            b.metric("Frecuencia mediana al final", f"{e['mdf_ultimos']:.1f} Hz", f"{e['mdf_cambio_pct']:+.1f} % vs. inicio", delta_color="off")
            c.metric("Tendencia de la frecuencia", f"{e['mdf_pendiente_hz_min']:+.2f} Hz/min", "si es negativa = fatiga", delta_color="off")
            st.caption(f"Se compararon los primeros y los últimos 30 s. Se usaron {e['ventanas_utiles']} de {e['ventanas_total']} "
                       f"ventanas ({e['pausas']} pausas y {e['artefactos']} con artefacto se excluyeron).")
            st.plotly_chart(gr.ejercicio(R.graficas["ejercicio"], musculo), use_container_width=True)
        else:
            st.info("No se cargó el archivo del ejercicio.")
    with t4:
        st.markdown("**Resumen**")
        st.dataframe(tabla_sencilla(R), hide_index=True, use_container_width=True)
        st.markdown("**¿Las diferencias son significativas?** (p < 0.05 = sí)")
        est = pd.DataFrame(R.estadistica)
        if not est.empty:
            fmt = lambda v: "—" if not np.isfinite(v) else (("< 0.001" if v < 0.001 else f"{v:.3f}") + (" ✔" if v < 0.05 else ""))
            for c in est.columns[1:]:
                est[c] = est[c].map(fmt)
            est["variable"] = est["variable"].replace({"RMS normalizado (%)": "Activación (%)", "MDF (Hz)": "Frecuencia mediana (Hz)",
                                                       "Tiempo de activación (s)": "Duración de la activación (s)"})
            est.columns = ["Variable", "Entre los 3 momentos", "Post-ejercicio vs. llegada", "Post-enfriamiento vs. llegada"]
            st.dataframe(est, hide_index=True, use_container_width=True)
            st.caption("Pruebas: Kruskal-Wallis entre los 3 momentos y Mann-Whitney contra la llegada (corrección de Bonferroni).")
        with st.expander("Todos los valores (con desviación estándar)"):
            st.dataframe(tabla_resumen(R), hide_index=True, use_container_width=True)
        with st.expander("Detalle de cada contracción"):
            det = pd.DataFrame(R.contracciones).drop(columns="musculo").round(2)
            st.dataframe(det.astype(object).where(det.notna(), "N/D"), hide_index=True, use_container_width=True)
