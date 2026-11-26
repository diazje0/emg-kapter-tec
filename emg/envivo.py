"""Recepción en vivo desde la ESP32 (DevKit o C3, por USB) y simulador.

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
        self.armado = False          # "Grabar" presionado: espera el primer pitido para empezar
        self.completa = False        # la toma llegó a su duración y se detuvo sola
        self.duracion = None         # segundos a grabar desde el pitido (None = sin límite)
        self.pre = 2.0               # segundos que se conservan antes del pitido
        self.t_inicio = None
        self.toma = None
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
            self._agregar_sin_lock(fila)

    def _agregar_varios(self, filas):
        with self._lock:
            for f in filas:
                self._agregar_sin_lock(f)

    def _agregar_sin_lock(self, fila):
        if True:
            self.buf.append(fila)
            self.muestras += 1
            if self.armado and fila[3] == 1:
                # primer pitido: arranca la grabación conservando los segundos previos
                n_pre = int(self.pre * 2000) + 1
                self.grabacion = list(self.buf)[-n_pre:]
                self.t_inicio = fila[0]
                self.armado, self.grabando = False, True
            elif self.grabando:
                self.grabacion.append(fila)
                if self.duracion and (fila[0] - self.t_inicio) >= self.duracion * 1e6:
                    self.grabando, self.completa = False, True

    def limpiar(self):
        """Borra lo que se ve en pantalla (no afecta una grabación en curso)."""
        with self._lock:
            self.buf.clear()
            self.muestras = 0

    def ventana(self):
        with self._lock:
            return np.array(self.buf) if self.buf else np.empty((0, 4))

    def armar(self, toma, duracion, pre=2.0):
        """Deja lista la grabación: empieza sola con el siguiente pitido y se detiene a los `duracion` s."""
        with self._lock:
            self.grabacion, self.toma, self.duracion, self.pre = [], toma, duracion, pre
            self.t_inicio, self.completa, self.grabando, self.armado = None, False, False, True

    def iniciar_grabacion(self):
        """Grabación inmediata, sin esperar pitido ni límite de tiempo."""
        with self._lock:
            self.grabacion, self.duracion, self.completa, self.armado = [], None, False, False
            self.t_inicio = self.buf[-1][0] if self.buf else 0
            self.grabando = True

    def transcurrido(self):
        with self._lock:
            if not (self.grabando or self.completa) or not self.grabacion or self.t_inicio is None:
                return 0.0
            return (self.grabacion[-1][0] - self.t_inicio) / 1e6

    def detener_grabacion(self):
        with self._lock:
            self.grabando = self.armado = self.completa = False
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
            # Abrir sin mover DTR/RTS para no reiniciar la ESP32 DevKit; si aun así se reinicia,
            # se espera a que arranque y se repite la orden de inicio hasta recibir datos.
            self.ser = serial.Serial()
            self.ser.port, self.ser.baudrate, self.ser.timeout = self.puerto, self.baudios, 0.5
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.open()
            time.sleep(1.5)
            self.ser.reset_input_buffer()
            self.ser.write(b"S")
            ultimo_s = time.time()
            resto = b""
            while self.activo:
                if self.muestras == 0 and time.time() - ultimo_s > 2:
                    self.ser.write(b"S")
                    ultimo_s = time.time()
                # Leer en bloques (todo lo que haya llegado) en lugar de línea por línea:
                # evita que se acumule retraso cuando la computadora está ocupada dibujando.
                n = self.ser.in_waiting
                datos = self.ser.read(n if n else 1)
                if not datos:
                    continue
                lineas = (resto + datos).split(b"\n")
                resto = lineas.pop()
                filas = []
                for linea in lineas:
                    partes = linea.strip().split(b",")
                    if len(partes) != 4 or partes[0][:1] in (b"t", b"#"):
                        continue
                    try:
                        filas.append(tuple(float(v) for v in partes))
                    except ValueError:
                        continue
                if filas:
                    self._agregar_varios(filas)
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
