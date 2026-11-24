"""Traduce los resultados numéricos a frases sencillas para el equipo y el reporte."""
from __future__ import annotations

import numpy as np

ALFA = 0.05

GLOSARIO = {
    "Activación (RMS)": "Qué tan fuerte se activó el músculo. Es el 'volumen' de la señal EMG, en microvoltios (µV). "
                        "Más alto = más fibras musculares trabajando.",
    "Activación normalizada (%)": "La misma activación, pero como porcentaje del valor más alto de la sesión. "
                                  "Sirve para comparar momentos sin depender de la colocación de los electrodos.",
    "Frecuencia mediana (MDF)": "Indicador de fatiga. Cuando el músculo se cansa, la señal se vuelve más 'lenta' "
                                "y la MDF **baja**. Si regresa a su valor inicial, el músculo se recuperó.",
    "Duración de la activación": "Cuánto tiempo, en segundos, estuvo activo el músculo en cada contracción de ~3 s.",
    "Tiempo de reacción (latencia)": "Tiempo entre el pitido y el inicio de la contracción, en milisegundos. "
                                     "Solo se calcula en tomas grabadas con la ESP32 (que tienen la marca del pitido).",
    "Valor p": "Indica si una diferencia es real o podría ser casualidad. Si p < 0.05 la diferencia es "
               "**estadísticamente significativa**.",
}


def _p(est, variable, col):
    for fila in est:
        if fila["variable"] == variable:
            return fila.get(col, np.nan)
    return np.nan


def _sig(p):
    if not np.isfinite(p):
        return ""
    return " (diferencia significativa)" if p < ALFA else " (la diferencia no es significativa)"


def conclusiones(R, musculo):
    """Devuelve una lista de frases en lenguaje sencillo."""
    rs = {r["momento"]: r for r in R.resumen}
    est = R.estadistica
    out = []
    lleg, post, enf = rs.get("Llegada"), rs.get("Post-ejercicio"), rs.get("Post-enfriamiento")

    if lleg and post:
        cambio = post["cambio_RMS_vs_llegada_pct"]
        p = _p(est, "RMS normalizado (%)", "p_post_ejercicio_vs_llegada")
        verbo = "aumentó" if cambio > 0 else "disminuyó"
        out.append(f"**Activación:** después del ejercicio la activación del {musculo} {verbo} "
                   f"**{abs(cambio):.0f} %** respecto a la llegada{_sig(p)}.")

        d = post["MDF_Hz"] - lleg["MDF_Hz"]
        p = _p(est, "MDF (Hz)", "p_post_ejercicio_vs_llegada")
        if d < 0 and np.isfinite(p) and p < ALFA:
            out.append(f"**Fatiga:** la frecuencia mediana bajó {abs(d):.1f} Hz (de {lleg['MDF_Hz']:.1f} a {post['MDF_Hz']:.1f} Hz) "
                       f"y la diferencia es significativa. Esto indica **fatiga muscular** después del ejercicio.")
        elif d < 0:
            out.append(f"**Fatiga:** la frecuencia mediana bajó un poco ({lleg['MDF_Hz']:.1f} → {post['MDF_Hz']:.1f} Hz)"
                       f"{_sig(p)}, así que no se puede afirmar que hubo fatiga.")
        else:
            out.append(f"**Fatiga:** la frecuencia mediana no bajó ({lleg['MDF_Hz']:.1f} → {post['MDF_Hz']:.1f} Hz); "
                       "no se observan signos de fatiga.")

    if lleg and enf:
        p_mdf = _p(est, "MDF (Hz)", "p_post_enfriamiento_vs_llegada")
        p_rms = _p(est, "RMS normalizado (%)", "p_post_enfriamiento_vs_llegada")
        if np.isfinite(p_mdf) and p_mdf >= ALFA:
            txt = (f"**Recuperación:** tras el enfriamiento la frecuencia mediana regresó a {enf['MDF_Hz']:.1f} Hz, "
                   "similar a la llegada: el músculo **se recuperó** de la fatiga")
        else:
            txt = (f"**Recuperación:** tras el enfriamiento la frecuencia mediana quedó en {enf['MDF_Hz']:.1f} Hz, "
                   "todavía diferente a la llegada: la recuperación **no fue completa**")
        if np.isfinite(p_rms) and p_rms < ALFA:
            c = enf["cambio_RMS_vs_llegada_pct"]
            txt += f", aunque la activación sigue {abs(c):.0f} % {'por encima' if c > 0 else 'por debajo'} de la llegada."
        else:
            txt += " y la activación volvió a niveles similares a la llegada."
        out.append(txt)

    if R.ejercicio:
        pend = R.ejercicio["mdf_pendiente_hz_min"]
        if abs(pend) < 0.5:
            out.append(f"**Durante el minuto de ejercicio** la frecuencia mediana se mantuvo prácticamente estable "
                       f"({pend:+.2f} Hz/min): no se vio una caída progresiva dentro del minuto; la fatiga se aprecia al "
                       "comparar antes y después del ejercicio.")
        elif pend < 0:
            out.append(f"**Durante el minuto de ejercicio** la frecuencia mediana fue bajando ({pend:+.2f} Hz/min): "
                       "la fatiga se fue acumulando conforme avanzaba el ejercicio.")
        else:
            out.append(f"**Durante el minuto de ejercicio** la frecuencia mediana no bajó ({pend:+.2f} Hz/min).")

    lat = [r["latencia_ms"] for r in R.resumen if np.isfinite(r["latencia_ms"])]
    if lat:
        out.append(f"**Tiempo de reacción:** el músculo empezó a activarse en promedio **{np.mean(lat):.0f} ms** "
                   "después del pitido.")
    return out


def conclusion_termica(calc, roi="TFL der."):
    """Frase sencilla sobre el cambio de temperatura de una región."""
    col = f"Δ {roi} (°C)"
    if col not in calc or calc[col].isna().any():
        return None
    t1, t2 = calc[col].iloc[1], calc[col].iloc[2]
    verbo = "se calentó" if t1 > 0 else "se enfrió"
    txt = f"El **{roi.replace('der.', 'derecho').replace('izq.', 'izquierdo')}** {verbo} **{abs(t1):.1f} °C** después del ejercicio"
    if abs(t2) < abs(t1):
        txt += f" y tras el enfriamiento bajó a {t2:+.1f} °C respecto a la llegada."
    else:
        txt += f" y tras el enfriamiento siguió en {t2:+.1f} °C respecto a la llegada."
    return txt
