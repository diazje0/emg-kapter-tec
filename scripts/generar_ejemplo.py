"""Genera una sesión SIMULADA (formato ESP32, 2 canales, 2 kHz) en datos_ejemplo/.

La fatiga se simula como mayor amplitud y menor frecuencia mediana después del ejercicio.
Uso:  python scripts/generar_ejemplo.py
"""
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt

FS, G = 2000, 207.87
SALIDA = Path(__file__).resolve().parent.parent / "datos_ejemplo"
rng = np.random.default_rng(42)


def ruido_emg(n, fc):
    b, a = butter(4, [20 / (FS / 2), fc / (FS / 2)], btype="band")
    x = filtfilt(b, a, rng.standard_normal(n))
    return x / x.std()


def guardar(nombre, tfl_uV, adu_uV, marcas_s=()):
    n = len(tfl_uV)
    t_us = (np.arange(n) / FS * 1e6).astype(int)
    tfl = np.clip(1650 + tfl_uV / 1000 * G + rng.normal(0, 1.5, n), 0, 3300)
    adu = np.clip(1650 + adu_uV / 1000 * G + rng.normal(0, 1.5, n), 0, 3300)
    marca = np.zeros(n, int)
    for m in marcas_s:
        marca[int(m * FS)] = 1
    with open(SALIDA / f"{nombre}.csv", "w") as f:
        f.write("t_us,tfl_mV,aductor_mV,marca\n")
        for row in zip(t_us, tfl, adu, marca):
            f.write(f"{row[0]},{row[1]:.1f},{row[2]:.1f},{row[3]}\n")


def main():
    SALIDA.mkdir(exist_ok=True)
    # momento: (fc TFL, amplitud TFL µV, amplitud aductor µV, latencia s)
    cfg = {"1": (230, 620, 90, 0.20), "2": (175, 1350, 140, 0.26), "3": (220, 1050, 100, 0.22)}
    n30 = 30 * FS
    for k, (fc, aT, aA, lat) in cfg.items():
        guardar(f"{k}_reposo", 70 * ruido_emg(n30, 400), 55 * ruido_emg(n30, 400))
        t = np.arange(n30) / FS
        act = np.zeros(n30)
        marcas = [5.0, 14.0, 23.0]
        for m in marcas:
            act[(t >= m + lat) & (t < m + lat + 3.0)] = 1
        guardar(f"{k}_contracciones", (70 + aT * act) * ruido_emg(n30, fc), (55 + aA * act) * ruido_emg(n30, fc + 30), marcas)
    n = 60 * FS
    t = np.arange(n) / FS
    act = 0.5 * (1 - np.cos(2 * np.pi * t / 6))                       # 3 s arriba, 3 s abajo
    tfl = np.concatenate([ruido_emg(n // 6 + 1, fc) for fc in np.linspace(235, 180, 6)])[:n]
    guardar("ejercicio", (80 + (1500 + 8 * t) * act) * tfl, (60 + 150 * act) * ruido_emg(n, 250))
    print(f"Datos de ejemplo en {SALIDA}")


if __name__ == "__main__":
    main()
