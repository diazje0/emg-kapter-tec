"""Lectura de registros: CSV del osciloscopio (Keysight) y CSV de la ESP32.

Osciloscopio:  x-axis,1[,2]        <- nombres
               second,Volt[,Volt]  <- unidades
               -5.05E+00,+1.88E+00 ...
ESP32:         t_us,tfl_mV,aductor_mV,marca
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Registro:
    fs: float
    canales: dict          # nombre -> señal en VOLTS (tal como salió del circuito)
    marcas: np.ndarray     # tiempos (s) de las marcas de inicio, si existen
    formato: str
    n: int


def _texto(archivo) -> str:
    if hasattr(archivo, "getvalue"):
        crudo = archivo.getvalue()
    elif hasattr(archivo, "read"):
        crudo = archivo.read()
    else:
        with open(archivo, "rb") as f:
            crudo = f.read()
    return crudo.decode("utf-8", errors="replace") if isinstance(crudo, bytes) else crudo


def leer_registro(archivo, nombres_osc=("TFL", "Aductor")) -> Registro:
    """Detecta el formato y devuelve un Registro con las señales en volts."""
    txt = _texto(archivo)
    primera = txt.splitlines()[0].strip().lower()
    if primera.startswith("x-axis"):
        return _osciloscopio(txt, nombres_osc)
    if primera.startswith("t_us"):
        return _esp32(txt)
    raise ValueError("Formato no reconocido: se esperaba un CSV del osciloscopio (x-axis,...) o de la ESP32 (t_us,...).")


def _osciloscopio(txt, nombres):
    df = pd.read_csv(io.StringIO(txt), skiprows=[1], dtype=str)
    df = df.apply(pd.to_numeric, errors="coerce")
    t = df.iloc[:, 0].to_numpy()
    n = len(df)
    tv = t[np.isfinite(t)]
    fs = (n - 1) / (tv.max() - tv.min())          # robusto aunque Excel haya redondeado el tiempo
    canales = {}
    for j, col in enumerate(df.columns[1:]):
        nombre = nombres[j] if j < len(nombres) else f"Canal {col}"
        canales[nombre] = df[col].to_numpy(float)
    return Registro(fs=fs, canales=canales, marcas=np.array([]), formato="osciloscopio", n=n)


def _esp32(txt):
    df = pd.read_csv(io.StringIO(txt)).apply(pd.to_numeric, errors="coerce").dropna(subset=["t_us"])
    t = (df["t_us"].to_numpy() - df["t_us"].iloc[0]) / 1e6
    fs = 1 / np.median(np.diff(t))
    canales = {}
    for col, nombre in (("tfl_mV", "TFL"), ("aductor_mV", "Aductor")):
        if col in df:
            canales[nombre] = df[col].to_numpy(float) / 1000.0     # mV -> V
    marcas = t[df["marca"].to_numpy() == 1] if "marca" in df else np.array([])
    return Registro(fs=fs, canales=canales, marcas=marcas, formato="esp32", n=len(df))


def identicos(a: Registro, b: Registro) -> bool:
    """True si dos registros tienen exactamente los mismos datos (archivo duplicado)."""
    if a.n != b.n or a.canales.keys() != b.canales.keys():
        return False
    return all(np.array_equal(a.canales[k], b.canales[k], equal_nan=True) for k in a.canales)
