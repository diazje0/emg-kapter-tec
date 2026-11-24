"""Gráficas interactivas (Plotly) con estilo claro y consistente."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .procesamiento import MOMENTOS

# Paleta azul: claro = llegada, oscuro = pico post-ejercicio, medio = recuperación
COLOR = {"Llegada": "#8EC3EE", "Post-ejercicio": "#123E7A", "Post-enfriamiento": "#3A8DDE"}
AZUL, ROJO, GRIS = "#0B2545", "#2E86DE", "#BFCCDB"
ACENTO = "#00A6C8"   # cian: tendencias y ΔT
ETIQ = {"Llegada": "Llegada", "Post-ejercicio": "Post-ejercicio", "Post-enfriamiento": "Post-enfriam."}


def _estilo(fig, alto=380, titulo=None):
    fig.update_annotations(font_size=15)
    fig.update_layout(template="plotly_white", height=alto, margin=dict(l=60, r=20, t=85 if titulo else 20, b=50),
                      title=dict(text=titulo, x=0, font=dict(size=18)) if titulo else None,
                      font=dict(family="Arial", size=14, color="#0B2545"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showline=True, linecolor="#8FA6C1", ticks="outside", gridcolor="#E6EEF7")
    fig.update_yaxes(showline=True, linecolor="#8FA6C1", ticks="outside", gridcolor="#E6EEF7")
    return fig


def _diezmar(t, y, max_puntos=6000):
    paso = max(1, len(t) // max_puntos)
    return t[::paso], y[::paso]


def senal_contracciones(g, musculo, momento):
    """Señal rectificada, RMS 500 ms, envolvente, umbral y franjas de activación."""
    fig = go.Figure()
    t, ax = _diezmar(g["t"], np.abs(g["x"]))
    fig.add_scatter(x=t, y=ax, mode="lines", line=dict(color=GRIS, width=0.6), name="Rectificada")
    tr, r = g["rms"]
    fig.add_scatter(x=tr + g["t"][0], y=r, mode="lines", line=dict(color=ROJO, width=2, shape="hvh"), name="RMS 500 ms")
    te, env = _diezmar(g["t"], g["env"])
    fig.add_scatter(x=te, y=env, mode="lines", line=dict(color=AZUL, width=2), name="Envolvente 4 Hz")
    fig.add_hline(y=g["umbral"], line=dict(color="#5A7391", dash="dot", width=1.2), annotation_text="umbral", annotation_position="bottom right")
    ytop = np.percentile(np.abs(g["x"]), 99.9) * 1.1
    for ion, ioff in g["onoff"]:
        t0, t1 = g["t"][ion], g["t"][min(ioff, len(g["t"]) - 1)]
        fig.add_vrect(x0=t0, x1=t1, fillcolor="#2E86DE", opacity=0.12, line_width=0)
        fig.add_annotation(x=(t0 + t1) / 2, y=ytop * 0.95, text=f"<b>{t1 - t0:.2f} s</b>", showarrow=False)
    fig.update_yaxes(title="µV (en electrodos)", range=[0, ytop])
    fig.update_xaxes(title="Tiempo (s)")
    return _estilo(fig, 360, f"{musculo} — {momento}: contracciones detectadas")


def cajas(ventanas, musculo):
    fig = make_subplots(rows=1, cols=2, subplot_titles=("RMS normalizado (%)", "Frecuencia mediana (Hz)"))
    for col, var in ((1, "RMS_pct"), (2, "MDF_Hz")):
        for m in MOMENTOS:
            y = [v[var] for v in ventanas if v["momento"] == m and v["musculo"] == musculo]
            if y:
                fig.add_box(y=y, name=ETIQ[m], marker_color=COLOR[m], boxmean=True, showlegend=False, row=1, col=col)
    return _estilo(fig, 380, f"{musculo}: comparación entre momentos (ventanas de 500 ms)")


def barras(resumen, musculo):
    fig = make_subplots(rows=1, cols=3, subplot_titles=("RMS contracciones (µV)", "MDF (Hz)", "Tiempo de activación (s)"))
    for col, (v, e) in enumerate((("RMS_contr_uV", "RMS_contr_DE"), ("MDF_Hz", "MDF_DE"), ("t_activacion_s", "t_activacion_DE")), 1):
        fig.add_bar(x=[ETIQ[r["momento"]] for r in resumen], y=[r[v] for r in resumen],
                    error_y=dict(type="data", array=[r[e] for r in resumen], color="#0B2545"),
                    marker_color=[COLOR[r["momento"]] for r in resumen], showlegend=False, row=1, col=col)
    return _estilo(fig, 340, f"{musculo}: promedio ± DE de las contracciones")


def ejercicio(g, musculo):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("RMS por ventana (µV)", "Frecuencia mediana por ventana (Hz)"))
    fig.add_scatter(x=g["t"], y=g["rms"], mode="lines+markers", marker=dict(size=3), line=dict(color=ROJO), name="RMS", row=1, col=1)
    fig.add_scatter(x=g["t"], y=g["mdf"], mode="markers", marker=dict(size=4, color=AZUL), name="MDF", row=2, col=1)
    fig.add_scatter(x=g["t"], y=np.polyval(g["pend"], g["t"]), mode="lines", line=dict(color=ACENTO, width=2.5),
                    name=f"Tendencia ({g['pend'][0] * 60:+.1f} Hz/min)", row=2, col=1)
    fig.update_xaxes(title="Tiempo (s)", row=2, col=1)
    return _estilo(fig, 480, f"{musculo} durante el ejercicio (sin pausas ni artefactos)")


def temperatura(df_temp, cols_roi):
    fig = go.Figure()
    paleta = ["#123E7A", "#6FA8DC", "#00838F", "#7FD3DE"]
    for c, color in zip(cols_roi, paleta):
        fig.add_scatter(x=df_temp["Momento"], y=df_temp[c], mode="lines+markers", name=c, line=dict(color=color, width=2.5),
                        marker=dict(size=9))
    fig.update_yaxes(title="Temperatura de la piel (°C)")
    return _estilo(fig, 380, "Temperatura cutánea por región")


def emg_vs_temp(momentos, rms_pct, mdf, dT, etiqueta_dT):
    fig = make_subplots(rows=1, cols=2, specs=[[{"secondary_y": True}, {"secondary_y": True}]],
                        subplot_titles=("RMS normalizado vs. ΔT", "Frecuencia mediana vs. ΔT"),
                        horizontal_spacing=0.16)
    for col, (y, nombre, color) in enumerate(((rms_pct, "RMS (%)", ROJO), (mdf, "MDF (Hz)", AZUL)), 1):
        fig.add_bar(x=momentos, y=y, name=nombre, marker_color=color, opacity=0.75, row=1, col=col, secondary_y=False)
        fig.add_scatter(x=momentos, y=dT, name=etiqueta_dT, mode="lines+markers", line=dict(color=ACENTO, width=3),
                        marker=dict(size=10), row=1, col=col, secondary_y=True, showlegend=(col == 1))
        fig.update_yaxes(title_text=nombre, row=1, col=col, secondary_y=False)
        fig.update_yaxes(title_text="ΔT (°C)", row=1, col=col, secondary_y=True, showgrid=False)
    fig = _estilo(fig, 440, "Relación EMG – temperatura del TFL")
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5), margin=dict(b=80))
    return fig
