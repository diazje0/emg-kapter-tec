"""Procesamiento de sEMG (mismo algoritmo validado en MATLAB para el Reto Kapter-TEC).

Pasos (actividad BI2005B):
  1) Quitar offset y rectificar          2) RMS en ventanas de 500 ms
  3) Normalizar al RMS máximo            4) Envolvente (pasa-bajas 4 Hz)
  5) Parámetros: amplitud máxima, RMS medio, frecuencia mediana (MDF),
     tiempo de activación y latencia (si hay marcas de inicio)
  6) Comparación entre momentos (Kruskal-Wallis y Mann-Whitney vs. llegada)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import butter, filtfilt, lfilter, welch
from scipy.signal.windows import hamming
from scipy.stats import kruskal, mannwhitneyu

MOMENTOS = ["Llegada", "Post-ejercicio", "Post-enfriamiento"]


def rnd(v):
    """Redondeo como MATLAB (0.5 hacia arriba), no el redondeo bancario de Python."""
    return int(np.floor(v + 0.5))


@dataclass
class Parametros:
    ventana: float = 0.5        # s, ventana del RMS
    traslape: float = 0.5       # fracción de traslape entre ventanas
    fc_env: float = 4.0         # Hz, envolvente (entre 2 y 5 Hz)
    filtrar: bool = True        # pasa-banda digital 20–450 Hz
    notch_armonicos: bool = True  # quita 60 Hz y armónicos
    recorte: float = 0.5        # s descartados al inicio (pico de arranque)
    dur_min: float = 1.0        # s, duración mínima de una contracción
    fc_onset: float = 15.0      # Hz, envolvente para inicio y fin
    sost_on: float = 0.025      # s arriba del umbral para el inicio (Hodges y Bui, 1996)
    sost_off: float = 0.2       # s abajo del umbral para el fin
    ventana_latencia: float = 0.02  # s, promedio móvil causal del rectificado para la latencia
    sost_latencia: float = 0.025  # s arriba del umbral para contar el inicio de la latencia
    n_contracciones: int = 3


# ----------------------------------------------------------------------------- filtros
def _filtfilt(b, a, x):
    """filtfilt con el mismo relleno que MATLAB."""
    return filtfilt(b, a, x, padlen=3 * (max(len(a), len(b)) - 1))


def acondicionar(v_volts: np.ndarray, fs: float, ganancia: float, p: Parametros, causal: bool = False) -> np.ndarray:
    """Quita offset, refiere a los electrodos (µV) y filtra. Recibe la señal en volts.
    causal=True filtra solo hacia adelante (lfilter): no adelanta el inicio de la activación (para la latencia)."""
    filtro = (lambda b, a, x: lfilter(b, a, x)) if causal else _filtfilt
    v = np.array(v_volts, float)   # copia: no modifica el registro original
    malo = ~np.isfinite(v)
    if malo.any():                                    # muestras vacías -> interpolación
        idx = np.arange(len(v))
        v[malo] = np.interp(idx[malo], idx[~malo], v[~malo])
    v = v[rnd((p.recorte * fs)):]
    x = (v - np.median(v)) / ganancia * 1e6           # 1) offset fuera, µV en electrodos
    if p.filtrar:
        fh = min(450.0, 0.45 * fs)
        b, a = butter(4, [20 / (fs / 2), fh / (fs / 2)], btype="bandpass")
        x = filtro(b, a, x)
    if p.notch_armonicos:
        for f0 in np.arange(60, min(420, 0.45 * fs) + 1e-9, 60):
            b, a = butter(2, [(f0 - 2) / (fs / 2), (f0 + 2) / (fs / 2)], btype="bandstop")
            x = filtro(b, a, x)
    return x


def envolvente(x: np.ndarray, fs: float, fc: float) -> np.ndarray:
    """4) Pasa-bajas Butterworth de 4.º orden, fase cero, sobre la señal rectificada."""
    b, a = butter(4, fc / (fs / 2), btype="low")
    return _filtfilt(b, a, np.abs(x))


# ----------------------------------------------------------------------------- parámetros
def rms_ventanas(x, fs, ventana=0.5, traslape=0.5, i0=0, i1=None):
    """2) RMS en ventanas. Devuelve centro de cada ventana (s), RMS (µV) e índice inicial."""
    i1 = len(x) if i1 is None else i1
    n = rnd((ventana * fs))
    paso = max(1, rnd((n * (1 - traslape))))
    ini = np.arange(i0, i1 - n + 1, paso)
    if len(ini) == 0:
        return np.array([]), np.array([]), ini
    r = np.array([np.sqrt(np.mean(x[i:i + n] ** 2)) for i in ini])
    return (ini + n / 2) / fs, r, ini


def frecuencia_mediana(seg, fs):
    """Frecuencia que divide la potencia (20–450 Hz) en dos mitades iguales."""
    nper = min(256, len(seg))
    f, pxx = welch(seg, fs, window=hamming(nper, sym=True), nperseg=nper, noverlap=nper // 2,
                   nfft=max(256, nper), detrend=False)
    k = (f >= 20) & (f <= min(450, 0.45 * fs))
    acum = np.cumsum(pxx[k])
    return float(f[k][np.argmax(acum >= acum[-1] / 2)])


def detectar_contracciones(env, umbral, fs, dur_min=1.0, n=3):
    """Tramos donde la envolvente supera el umbral; se quedan los n más largos."""
    activo = (env > umbral).astype(int)
    d = np.diff(np.r_[0, activo, 0])
    ini, fin = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    dur = (fin - ini + 1) / fs
    ok = dur >= dur_min
    ini, fin, dur = ini[ok], fin[ok], dur[ok]
    orden = np.sort(np.argsort(-dur, kind="stable")[:n])
    return [(int(ini[i]), int(fin[i])) for i in orden]


def inicio_fin(env, umbral, seg, fs, sost_on=0.025, sost_off=0.2):
    """Inicio y fin de la activación partiendo del centro de la contracción."""
    n_on, n_off = max(1, rnd(sost_on * fs)), max(1, rnd(sost_off * fs))
    a = max(0, seg[0] - rnd(0.5 * fs))
    b = min(len(env) - 1, seg[1] + rnd(0.5 * fs))
    arriba = env[a:b + 1] > umbral
    m = rnd((seg[0] + seg[1]) / 2) - a
    ion = 0
    for i in range(m, n_off - 2, -1):                 # último tramo ≥ sost_off abajo antes del centro
        if not arriba[i - n_off + 1:i + 1].any():
            ion = i + 1
            break
    for i in range(ion, m + 1):                       # primer punto sostenido arriba ≥ sost_on
        if arriba[i:i + n_on].all():
            ion = i
            break
    ioff = len(arriba) - 1
    for i in range(m, len(arriba) - n_off + 1):       # primer tramo ≥ sost_off abajo después del centro
        if not arriba[i:i + n_off].any():
            ioff = i - 1
            break
    return a + ion, a + ioff


def envolvente_causal(x, fs, ventana=0.02):
    """Promedio móvil del rectificado usando solo muestras pasadas: no adelanta el inicio de la activación."""
    n = max(1, rnd(ventana * fs))
    c = np.cumsum(np.r_[0.0, np.abs(x)])
    out = np.empty(len(x))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    out[:n - 1] = c[1:n] / np.arange(1, n)
    return out


def primer_sostenido(env, umbral, i0, i1, n):
    """Primer índice en [i0, i1) desde el cual la envolvente queda arriba del umbral n muestras seguidas."""
    arriba = env[i0:i1] > umbral
    for i in range(0, len(arriba) - n + 1):
        if arriba[i:i + n].all():
            return i0 + i
    return None


# ----------------------------------------------------------------------------- análisis de una sesión
@dataclass
class ResultadoMusculo:
    musculo: str
    resumen: list = field(default_factory=list)       # una fila por momento
    contracciones: list = field(default_factory=list)  # una fila por contracción
    ventanas: list = field(default_factory=list)       # ventanas de 500 ms (estadística)
    estadistica: list = field(default_factory=list)
    ejercicio: dict = field(default_factory=dict)
    graficas: dict = field(default_factory=dict)       # datos para graficar
    rms_max: float = np.nan
    avisos: list = field(default_factory=list)


def analizar_musculo(musculo, rep, con, ej, p: Parametros = Parametros()):
    """rep, con: listas de 3 tuplas (x_µV, fs, marcas_s) por momento; ej: (x_µV, fs, marcas) o None."""
    R = ResultadoMusculo(musculo)

    # Ejercicio: ventanas útiles (activas y sin artefactos)
    rE = np.array([]); okE = np.array([], bool)
    if ej is not None:
        xE, fsE, _ = ej[:3]
        tcE, rE, iniE = rms_ventanas(xE, fsE, p.ventana, p.traslape)
        med = np.median(rE); mad = 1.4826 * np.median(np.abs(rE - med))
        activa = rE > 0.4 * np.percentile(rE, 90, method="hazen")
        limpia = rE < med + 6 * mad
        okE = activa & limpia
        n = rnd((p.ventana * fsE))
        tc, r, ini = tcE[okE], rE[okE], iniE[okE]
        f = np.array([frecuencia_mediana(xE[i:i + n], fsE) for i in ini])
        prim, ult = tc < 30, tc >= tc[-1] - 30
        pend = np.polyfit(tc / 60, f, 1)[0]
        R.ejercicio = dict(
            rms_primeros=r[prim].mean(), rms_ultimos=r[ult].mean(),
            rms_cambio_pct=(r[ult].mean() - r[prim].mean()) / r[prim].mean() * 100,
            mdf_primeros=f[prim].mean(), mdf_ultimos=f[ult].mean(),
            mdf_cambio_pct=(f[ult].mean() - f[prim].mean()) / f[prim].mean() * 100,
            mdf_pendiente_hz_min=pend, ventanas_utiles=int(okE.sum()), ventanas_total=len(rE),
            pausas=int((~activa).sum()), artefactos=int((activa & ~limpia).sum()))
        R.graficas["ejercicio"] = dict(t=tc, rms=r, mdf=f, pend=np.polyfit(tc, f, 1))

    for k, mom in enumerate(MOMENTOS):
        if con[k] is None or rep[k] is None:
            continue
        x, fs, marcas = con[k][:3]
        xr, fsr, _ = rep[k][:3]
        x_lat = con[k][3] if len(con[k]) > 3 else x          # versión filtrada de forma causal
        xr_lat = rep[k][3] if len(rep[k]) > 3 else xr
        env = envolvente(x, fs, p.fc_env)
        env_rep = envolvente(xr, fsr, p.fc_env)
        umbral = env_rep.mean() + 3 * env_rep.std(ddof=1)
        segs = detectar_contracciones(env, umbral, fs, p.dur_min, p.n_contracciones)
        envR = envolvente(x, fs, p.fc_onset)
        envRr = envolvente(xr, fsr, p.fc_onset)
        umbralR = envRr.mean() + 3 * envRr.std(ddof=1)
        env50 = envolvente_causal(x_lat, fs, p.ventana_latencia)
        env50r = envolvente_causal(xr_lat, fsr, p.ventana_latencia)
        umbral50 = env50r.mean() + 3 * env50r.std(ddof=1)
        if len(segs) < p.n_contracciones:
            R.avisos.append(f"{musculo} — {mom}: solo se detectaron {len(segs)} contracciones.")
        _, rRep, _ = rms_ventanas(xr, fsr, p.ventana, p.traslape)
        filas, onoff = [], []
        n = rnd((p.ventana * fs))
        for c, seg in enumerate(segs, 1):
            ion, ioff = inicio_fin(envR, umbralR, seg, fs, p.sost_on, p.sost_off)
            onoff.append((ion, ioff))
            _, r, ini = rms_ventanas(x, fs, p.ventana, p.traslape, ion, ioff + 1)
            f = np.array([frecuencia_mediana(x[i:i + n], fs) for i in ini])
            for rr, ff in zip(r, f):
                R.ventanas.append(dict(momento=mom, musculo=musculo, contraccion=c, RMS_uV=rr, MDF_Hz=ff))
            lat = np.nan
            if marcas is not None and len(marcas):
                # Latencia: del pitido al primer punto con envolvente de 50 Hz > reposo + 3 DE durante ≥ 25 ms
                t_mid = (ion + ioff) / 2 / fs + p.recorte
                previas = marcas[(marcas <= t_mid) & (marcas >= t_mid - 5.0)]
                if len(previas):
                    i_m = max(0, rnd((previas[-1] - p.recorte) * fs))
                    i_on = primer_sostenido(env50, umbral50, i_m, min(len(env50), i_m + rnd(2.0 * fs)), rnd(p.sost_latencia * fs))
                    if i_on is not None:
                        lat = (i_on - i_m) / fs * 1000
            fila = dict(momento=mom, musculo=musculo, contraccion=c,
                        inicio_s=ion / fs + p.recorte, fin_s=ioff / fs + p.recorte,
                        t_activacion_s=(ioff - ion) / fs, RMS_uV=r.mean(), RMS_max_uV=r.max(),
                        MDF_Hz=f.mean(), latencia_ms=lat)
            filas.append(fila)
        R.contracciones += filas
        F = {kk: np.array([f[kk] for f in filas]) for kk in ("RMS_uV", "RMS_max_uV", "MDF_Hz", "t_activacion_s", "latencia_ms")}
        sd = lambda v: float(np.std(v, ddof=1)) if len(v) > 1 else np.nan
        R.resumen.append(dict(
            momento=mom, RMS_reposo_uV=rRep.mean(),
            RMS_contr_uV=F["RMS_uV"].mean(), RMS_contr_DE=sd(F["RMS_uV"]),
            amplitud_max_uV=F["RMS_max_uV"].max(),
            MDF_Hz=F["MDF_Hz"].mean(), MDF_DE=sd(F["MDF_Hz"]),
            t_activacion_s=F["t_activacion_s"].mean(), t_activacion_DE=sd(F["t_activacion_s"]),
            latencia_ms=np.nanmean(F["latencia_ms"]) if np.isfinite(F["latencia_ms"]).any() else np.nan))
        R.graficas[mom] = dict(t=np.arange(len(x)) / fs + p.recorte, x=x, env=env, umbral=umbral,
                               rms=rms_ventanas(x, fs, p.ventana, p.traslape)[:2], onoff=onoff, fs=fs)

    # 3) Normalización al RMS máximo (contracciones + ventanas útiles del ejercicio)
    todos = [v["RMS_uV"] for v in R.ventanas] + list(rE[okE])
    R.rms_max = max(todos) if todos else np.nan
    for v in R.ventanas:
        v["RMS_pct"] = v["RMS_uV"] / R.rms_max * 100
    base = next((r for r in R.resumen if r["momento"] == "Llegada"), None)
    for r in R.resumen:
        r["RMS_contr_pct"] = r["RMS_contr_uV"] / R.rms_max * 100
        r["RMS_contr_DE_pct"] = r["RMS_contr_DE"] / R.rms_max * 100
        r["cambio_RMS_vs_llegada_pct"] = ((r["RMS_contr_pct"] - base["RMS_contr_pct"]) / base["RMS_contr_pct"] * 100) if base else np.nan

    # 6) Estadística
    R.estadistica = estadistica(R.ventanas, R.contracciones)
    return R


def _p(a, b):
    try:
        return min(1.0, 2 * mannwhitneyu(a, b, alternative="two-sided").pvalue)   # Bonferroni (2 comparaciones)
    except ValueError:
        return np.nan


def estadistica(ventanas, contracciones):
    out = []
    pruebas = [("RMS normalizado (%)", ventanas, "RMS_pct"), ("MDF (Hz)", ventanas, "MDF_Hz"),
               ("Tiempo de activación (s)", contracciones, "t_activacion_s")]
    for nombre, filas, col in pruebas:
        g = [np.array([f[col] for f in filas if f["momento"] == m]) for m in MOMENTOS]
        g = [x for x in g if len(x)]
        if len(g) < 2:
            continue
        try:
            pkw = kruskal(*g).pvalue
        except ValueError:
            pkw = np.nan
        out.append(dict(variable=nombre, p_kruskal_wallis=pkw,
                        p_post_ejercicio_vs_llegada=_p(g[0], g[1]) if len(g) > 1 else np.nan,
                        p_post_enfriamiento_vs_llegada=_p(g[0], g[2]) if len(g) > 2 else np.nan))
    return out
