# EMG Kapter-TEC 💪

Aplicación para **procesar y visualizar señales de electromiografía de superficie (sEMG)** del sistema wearable
desarrollado en el Reto Kapter-TEC (BI2005B *Aplicación de bioinstrumentación y tecnologías biomédicas*,
Tecnológico de Monterrey). Registra la abducción de cadera midiendo el **tensor de la fascia lata (TFL)** y el
**aductor largo**, y relaciona la fatiga muscular con la **temperatura cutánea** medida por termografía en Kapter.

**Equipo:** Fernanda Rivadeneyra Maya · Carlo Leonardo Medrano Sánchez · Emmanuel Díaz Juárez

## ¿Qué hace?

| Página | Función |
|---|---|
| 📂 **Procesamiento** | Lee los 7 CSV de una sesión (osciloscopio o ESP32) y calcula RMS, frecuencia mediana (MDF), tiempo de activación, latencia y estadística. Muestra gráficas interactivas y exporta todo a Excel. |
| 📡 **En vivo (ESP32)** | Recibe la señal de la ESP32 por USB o Bluetooth, la grafica en tiempo real, envía el pitido de inicio y graba cada toma ya con el nombre que usa la app. Incluye un **simulador** para probar sin hardware. |
| 🌡️ **Termografía** | Captura las temperaturas por región (T0–T2) y las compara con el RMS y la MDF del TFL. |

## Instalación

Requiere Python 3.10 o más reciente.

```bash
git clone <url-del-repositorio>
cd emg-kapter-tec
pip install -r requirements.txt
streamlit run app.py
```

Se abre en el navegador (`http://localhost:8501`). Para probar sin datos reales: **Procesamiento → Cargar datos de ejemplo**.

> La página **En vivo** necesita que la app corra en la computadora conectada a la ESP32 (no funciona en la nube).

## Protocolo de medición

| Momento | Tomas (nombre del archivo) |
|---|---|
| 1 · Llegada (inicio) | Termograma T0 · `1_reposo` (30 s) · `1_contracciones` (3 × 3 s, 6 s de descanso) |
| Ejercicio | `ejercicio` (1 min de abducción con polaina) |
| 2 · Post-ejercicio (pico) | Termograma T1 · `2_reposo` · `2_contracciones` |
| Enfriamiento | 2 min caminando + 1 min quieto |
| 3 · Post-enfriamiento (recuperación) | Termograma T2 · `3_reposo` · `3_contracciones` |

## Formatos de archivo

**Osciloscopio (Keysight):** CSV tal como sale de la USB, sin abrirlo ni guardarlo en Excel
(Excel redondea a 3 cifras y se pierde precisión).

```
x-axis,1
second,Volt
-5.0500000E+00,+1.8894472E+00
```

El canal 1 se interpreta como TFL y el canal 2 (si existe) como aductor largo.

**ESP32** (lo genera el firmware y la página En vivo):

```
t_us,tfl_mV,aductor_mV,marca
0,1648,1652,0
```

`marca = 1` en la muestra en que sonó el pitido de inicio; con ella se calcula la latencia.

## Procesamiento

Mismo algoritmo validado en MATLAB (los resultados coinciden con `procesamiento_EMG_TFL.m`):

1. Se descartan los primeros 0.5 s, se quita el offset y se divide entre la ganancia medida → µV en los electrodos.
2. Pasa-banda digital 20–450 Hz y eliminación de 60 Hz y sus armónicos.
3. Rectificación, **RMS en ventanas de 500 ms** (50 % de traslape) y **normalización** al RMS máximo de la sesión.
4. **Envolvente**: pasa-bajas Butterworth de 4.º orden a 4 Hz, fase cero.
5. **Contracciones**: tramos con envolvente > reposo + 3 DE; inicio y fin con criterio de Hodges y Bui (1996).
6. **Frecuencia mediana** por ventana (método de Welch), **tiempo de activación** y **latencia**
   (del pitido al inicio de la activación, con filtrado causal para no adelantar el inicio).
7. **Estadística**: Kruskal-Wallis entre momentos y U de Mann-Whitney contra la llegada (Bonferroni).
8. **Ejercicio**: primeros vs. últimos 30 s y pendiente de la MDF (negativa = fatiga), excluyendo pausas y artefactos.

## Hardware

Firmware en [`firmware/esp32_emg/esp32_emg.ino`](firmware/esp32_emg/esp32_emg.ino) para la **Adafruit HUZZAH32**
(Arduino IDE, core *esp32 by Espressif* 3.x):

| Señal | Pin |
|---|---|
| Salida canal TFL | A2 (GPIO 34) |
| Salida canal aductor | A3 (GPIO 39) |
| Buzzer activo 3.3 V | GPIO 21 |
| GND | GND2 (lado de salida del ISO124) |

Muestrea 2 canales a 2 kHz y envía por USB (921 600 baudios) y Bluetooth (`EMG_KapterTEC`).
Comandos: `S` iniciar, `P` pausar, `B` pitido + marca.

⚠️ **Seguridad:** el circuito del lado del paciente funciona solo con baterías. Nunca conecten la ESP32, una
computadora enchufada a la pared, el osciloscopio o el generador al lado del paciente (GND1) mientras alguien
tenga electrodos colocados.

## Estructura

```
app.py                  # punto de entrada de Streamlit
paginas/                # Inicio, Procesamiento, En vivo, Termografía
emg/                    # lectura, procesamiento, sesión, gráficas, recepción en vivo
firmware/esp32_emg/     # sketch de Arduino para la ESP32
datos_ejemplo/          # sesión SIMULADA para probar la app
scripts/                # generador de los datos de ejemplo
tests/                  # pruebas (pytest)
```

## Privacidad

Los registros de participantes **no se suben al repositorio** (`registros/`, `Datos/` y los `.xlsx` están en
`.gitignore`). Los datos de `datos_ejemplo/` son simulados.

## Referencias

- De Luca, C. J. (1997). The use of surface electromyography in biomechanics. *J. Appl. Biomech., 13*(2), 135–163.
- Hermens, H. J. et al. (2000). Development of recommendations for SEMG sensors and sensor placement procedures. *J. Electromyogr. Kinesiol., 10*(5), 361–374.
- Hodges, P. W., & Bui, B. H. (1996). A comparison of computer-based methods for the determination of onset of muscle contraction using electromyography. *Electroencephalogr. Clin. Neurophysiol., 101*(6), 511–519.
- Cifrek, M. et al. (2009). Surface EMG based muscle fatigue evaluation in biomechanics. *Clin. Biomech., 24*(4), 327–340.
- Moreira, D. G. et al. (2017). Thermographic imaging in sports and exercise medicine: A Delphi study and consensus statement on the measurement of human skin temperature. *J. Therm. Biol., 69*, 155–162.
