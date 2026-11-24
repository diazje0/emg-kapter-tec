"""Pruebas básicas: lectura de ambos formatos y análisis con señales simuladas de parámetros conocidos."""
import io

import numpy as np
import pytest
from scipy.signal import butter, filtfilt

from emg import Parametros, leer_registro
from emg.procesamiento import detectar_contracciones, envolvente, frecuencia_mediana, rms_ventanas
from emg.sesion import analizar_sesion

FS = 2000
rng = np.random.default_rng(0)


def emg(n, fc=200):
    b, a = butter(4, [20 / (FS / 2), fc / (FS / 2)], btype="band")
    x = filtfilt(b, a, rng.standard_normal(n))
    return x / x.std()


def csv_esp32(tfl_uV, adu_uV, marcas=(), G=200.0):
    n = len(tfl_uV)
    m = np.zeros(n, int)
    for t in marcas:
        m[int(t * FS)] = 1
    filas = ["t_us,tfl_mV,aductor_mV,marca"] + [
        f"{int(i / FS * 1e6)},{1650 + a / 1000 * G:.2f},{1650 + b / 1000 * G:.2f},{k}" for i, (a, b, k) in enumerate(zip(tfl_uV, adu_uV, m))]
    return io.StringIO("\n".join(filas))


def test_rms_de_senoidal():
    t = np.arange(FS) / FS
    x = 100 * np.sin(2 * np.pi * 50 * t)
    _, r, _ = rms_ventanas(x, FS)
    assert np.allclose(r, 100 / np.sqrt(2), rtol=0.01)


def test_frecuencia_mediana_baja_con_fatiga():
    assert frecuencia_mediana(emg(1000, 120), FS) < frecuencia_mediana(emg(1000, 300), FS)


def test_detecta_tres_contracciones():
    t = np.arange(30 * FS) / FS
    act = ((t > 5) & (t < 8)) | ((t > 14) & (t < 17)) | ((t > 23) & (t < 26))
    x = (20 + 500 * act) * emg(len(t))
    env = envolvente(x, FS, 4)
    rep = envolvente(20 * emg(len(t)), FS, 4)
    segs = detectar_contracciones(env, rep.mean() + 3 * rep.std(ddof=1), FS)
    assert len(segs) == 3


def test_lectura_osciloscopio():
    txt = "x-axis,1\nsecond,Volt\n" + "\n".join(f"{-5 + i * 0.0006:+.7E},{1.65:+.7E}" for i in range(1000))
    r = leer_registro(io.StringIO(txt))
    assert r.formato == "osciloscopio" and abs(r.fs - 1666.67) < 1 and "TFL" in r.canales


def test_sesion_completa_con_latencia():
    n = 30 * FS
    t = np.arange(n) / FS
    marcas = [5.0, 14.0, 23.0]
    regs = {}
    for k, amp in (("1", 600), ("2", 1200), ("3", 900)):
        act = np.zeros(n)
        for m in marcas:
            act[(t >= m + 0.2) & (t < m + 3.2)] = 1
        regs[f"{k}_reposo"] = leer_registro(csv_esp32(40 * emg(n), 40 * emg(n)))
        regs[f"{k}_contracciones"] = leer_registro(csv_esp32((40 + amp * act) * emg(n), (40 + 100 * act) * emg(n), marcas))
    res, avisos = analizar_sesion(regs, {"TFL": 200.0, "Aductor": 200.0}, Parametros())
    R = res["TFL"]
    rms = [r["RMS_contr_uV"] for r in R.resumen]
    assert rms[1] > rms[2] > rms[0]                                  # fatiga y recuperación simuladas
    assert all(abs(r["t_activacion_s"] - 3.0) < 0.5 for r in R.resumen)
    assert all(100 < r["latencia_ms"] < 300 for r in R.resumen)      # latencia simulada: 200 ms
    assert R.estadistica[0]["p_kruskal_wallis"] < 0.05
