import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import spearmanr

from emg import graficas as gr

st.title(":material/thermostat: Termografía")
st.caption("Captura la temperatura promedio de cada región de interés (ROI) medida en el software de FOTRIC "
           "y compárala con los indicadores EMG de la página de Procesamiento.")

MOMENTOS = ["T0 · Llegada", "T1 · Post-ejercicio", "T2 · Post-enfriamiento"]
ROIS = ["TFL der. (°C)", "TFL izq. (°C)", "Aductor der. (°C)", "Aductor izq. (°C)"]

if "temp" not in st.session_state:
    st.session_state["temp"] = pd.DataFrame({"Momento": MOMENTOS, **{r: [np.nan] * 3 for r in ROIS}, "Borg (0-10)": [np.nan] * 3})

c1, c2 = st.columns([3, 1])
with c2:
    subido = st.file_uploader("…o carga un CSV con la misma tabla", type=["csv"])
    if subido is not None:
        try:
            df_sub = pd.read_csv(subido)
            st.session_state["temp"] = df_sub[["Momento", *ROIS, "Borg (0-10)"]]
        except Exception as e:
            st.error(f"El CSV debe tener las columnas: Momento, {', '.join(ROIS)}, Borg (0-10). ({e})")
    st.download_button("Descargar tabla", st.session_state["temp"].to_csv(index=False), "termografia.csv", "text/csv", icon=":material/download:")
with c1:
    df = st.data_editor(st.session_state["temp"], hide_index=True, use_container_width=True, disabled=["Momento"],
                        column_config={r: st.column_config.NumberColumn(r, format="%.2f", min_value=20.0, max_value=42.0) for r in ROIS})
    st.session_state["temp"] = df

if df[ROIS].isna().all().all():
    st.info("Escribe las temperaturas de cada región para ver las gráficas.")
    st.stop()

# ------------------------------------------------------------------ cálculos
d = df.copy()
d["Momento"] = [m.split(" · ")[1] for m in d["Momento"]]
calc = pd.DataFrame({"Momento": d["Momento"]})
for r in ROIS:
    calc[f"Δ {r.replace(' (°C)', '')} (°C)"] = d[r] - d[r].iloc[0]
calc["Asimetría TFL der.−izq. (°C)"] = d["TFL der. (°C)"] - d["TFL izq. (°C)"]
calc["Asimetría aductor der.−izq. (°C)"] = d["Aductor der. (°C)"] - d["Aductor izq. (°C)"]

st.plotly_chart(gr.temperatura(d, ROIS), use_container_width=True)
st.markdown("**Cambios respecto a la llegada (ΔT) y asimetría entre piernas**")
st.dataframe(calc.round(2), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ relación con la EMG
res = st.session_state.get("resultados")
st.subheader("Relación con la EMG")
if not res or "TFL" not in res:
    st.info("Procesa primero una sesión en la página **Procesamiento** para comparar con los indicadores EMG.")
    st.stop()

R = res["TFL"]
rs = pd.DataFrame(R.resumen).set_index("momento")
emg = pd.DataFrame({"Momento": ["Llegada", "Post-ejercicio", "Post-enfriamiento"]})
emg["RMS (%)"] = [rs["RMS_contr_pct"].get(m, np.nan) for m in emg["Momento"]]
emg["MDF (Hz)"] = [rs["MDF_Hz"].get(m, np.nan) for m in emg["Momento"]]
dT = calc["Δ TFL der. (°C)"].to_numpy()
asim = calc["Asimetría TFL der.−izq. (°C)"].to_numpy()
opcion = st.radio("Variable térmica", ["ΔT del TFL derecho", "Asimetría TFL der.−izq."], horizontal=True)
y = dT if opcion.startswith("ΔT") else asim
st.plotly_chart(gr.emg_vs_temp(emg["Momento"], emg["RMS (%)"], emg["MDF (Hz)"], y, opcion), use_container_width=True)

ok = np.isfinite(y) & np.isfinite(emg["RMS (%)"])
if ok.sum() == 3:
    r1 = spearmanr(y, emg["RMS (%)"]).statistic
    r2 = spearmanr(y, emg["MDF (Hz)"]).statistic
    a, b = st.columns(2)
    a.metric("Spearman ρ (temperatura vs. RMS)", f"{r1:+.2f}")
    b.metric("Spearman ρ (temperatura vs. MDF)", f"{r2:+.2f}")
    st.caption("Con solo 3 momentos la correlación es **exploratoria**: indica la dirección de la relación, no su significancia.")
