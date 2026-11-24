"""Recepción en vivo desde la ESP32 (puerto serie USB o Bluetooth SPP) y simulador.

Protocolo (ver firmware/esp32_emg/esp32_emg.ino):
  ESP32 -> PC : líneas "t_us,tfl_mV,aductor_mV,marca"
  PC -> ESP32 : 'S' iniciar envío, 'P' pausar, 'B' pitido + marca de inicio
"""
from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np

ENCABEZADO = "t_us,tfl_mV,aductor_mV,marca"


class Receptor:
    """Lee muestras en un hilo aparte y las guarda en un búfer circular y, si se graba, en una lista."""

    def __init__(self, segundos_buffer=10, fs_esperada=2000):
        self.buf = deque(maxlen=int(segundos_buffer * fs_esperada))
        self.grabacion = []
        self.grabando = False
        self.activo = False
        self.error = None
        self.muestras = 0
        self._lock = threading.Lock()
        self._hilo = None

    # --- interfaz común
    def iniciar(self):
        self.activo = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def detener(self):
        self.activo = False

    def marcar(self):
        """Pide un pitido + marca de inicio."""

    def _agregar(self, fila):
        with self._lock:
            self.buf.append(fila)
            self.muestras += 1
            if self.grabando:
                self.grabacion.append(fila)

    def ventana(self):
        with self._lock:
            return np.array(self.buf) if self.buf else np.empty((0, 4))

    def iniciar_grabacion(self):
        with self._lock:
            self.grabacion = []
            self.grabando = True

    def detener_grabacion(self):
        with self._lock:
            self.grabando = False
            return list(self.grabacion)

    @staticmethod
    def a_csv(filas):
        lineas = [ENCABEZADO] + [f"{int(t)},{a:.1f},{b:.1f},{int(m)}" for t, a, b, m in filas]
        return "\n".join(lineas) + "\n"


class ReceptorSerie(Receptor):
    def __init__(self, puerto, baudios=921600, **kw):
        super().__init__(**kw)
        self.puerto, self.baudios, self.ser = puerto, baudios, None

    def _bucle(self):
        import serial
        try:
            self.ser = serial.Serial(self.puerto, self.baudios, timeout=1)
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            self.ser.write(b"S")
            while self.activo:
                linea = self.ser.readline().decode("ascii", errors="ignore").strip()
                if not linea or linea.startswith("t_us") or linea.startswith("#"):
                    continue
                partes = linea.split(",")
                if len(partes) != 4:
                    continue
                try:
                    self._agregar(tuple(float(v) for v in partes))
                except ValueError:
                    continue
        except Exception as e:  # puerto ocupado, desconectado, etc.
            self.error = str(e)
            self.activo = False
        finally:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(b"P")
                except Exception:
                    pass
                self.ser.close()

    def marcar(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b"B")


class Simulador(Receptor):
    """Genera EMG sintética (2 canales, 2 kHz) para probar la app sin hardware."""

    def __init__(self, fs=2000, **kw):
        super().__init__(fs_esperada=fs, **kw)
        self.fs = fs
        self._contraer_hasta = -1.0
        self._marca = False

    def marcar(self):
        self._marca = True

    def _bucle(self):
        rng = np.random.default_rng()
        t0 = time.perf_counter()
        n = 0
        bloque = self.fs // 50                       # 20 ms por iteración
        while self.activo:
            ahora = time.perf_counter() - t0
            objetivo = int(ahora * self.fs)
            while n < objetivo:
                t = n / self.fs
                marca = 0
                if self._marca:
                    marca, self._marca = 1, False
                    self._contraer_hasta = t + 3.2
                activo = 0.18 < (t - (self._contraer_hasta - 3.2)) and t < self._contraer_hasta
                amp_tfl = 0.75 if activo else 0.04            # mV en la entrada
                amp_adu = 0.12 if activo else 0.03
                tfl = 1650 + 207.87 * amp_tfl * rng.standard_normal()
                adu = 1650 + 207.87 * amp_adu * rng.standard_normal()
                self._agregar((t * 1e6, float(np.clip(tfl, 0, 3300)), float(np.clip(adu, 0, 3300)), marca))
                n += 1
            time.sleep(bloque / self.fs)
