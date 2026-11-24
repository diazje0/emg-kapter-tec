/*
  EMG Kapter-TEC — firmware para ESP32-C3 (DevKitM-1, SuperMini y similares)

  - Muestrea 2 canales a 2 kHz con un timer de hardware (ADC1, atenuación 11 dB).
  - Envía por USB (USB-CDC nativo del C3) líneas:  t_us,tfl_mV,aductor_mV,marca
  - Comandos que recibe (desde la app o el Monitor serie):
        S = iniciar envío    P = pausar envío    B = pitido + marca de inicio (para la latencia)

  Conexiones (ESP32-C3):
        Salida canal TFL      -> GPIO 0  (ADC1_CH0)
        Salida canal aductor  -> GPIO 1  (ADC1_CH1)
        Buzzer activo 3.3 V   -> GPIO 10 (y GND)
        GND de la ESP32       -> GND2 (lado de SALIDA del ISO124). Nunca al lado del paciente.
  Evitar: GPIO 2, 8 y 9 (pines de arranque), 18–19 (USB) y 20–21 (UART0).
  No usar GPIO 5 para señal: es ADC2 y en el C3 no es confiable.

  RANGO DEL ADC: con 11 dB el C3 mide bien de ~0 a ~2.5 V (no hasta 3.3 V).
  Si el offset de la salida está en 1.65 V, solo quedan ~0.85 V hacia arriba:
  conviene bajar el offset a ~1.25 V (divisor de referencia) o limitar la ganancia.

  Arduino IDE, core "esp32 by Espressif Systems" 3.x:
        Placa: "ESP32C3 Dev Module" (o la de tu modelo)
        Tools > USB CDC On Boot: "Enabled"   <- necesario si la placa usa el USB nativo
  Con USB nativo la velocidad (baudios) no importa.
*/

const int PIN_TFL     = 0;
const int PIN_ADUCTOR = 1;
const int PIN_BUZZER  = 10;
const uint32_t FS_HZ  = 2000;          // muestras por segundo por canal
const uint32_t PITIDO_MS = 120;

hw_timer_t *timer = nullptr;
volatile bool tocaMuestra = false;
bool enviando = false;
bool marcaPendiente = false;
uint32_t finPitido = 0;

void IRAM_ATTR alTimer() { tocaMuestra = true; }

void procesarComando(char c) {
  if (c == 'S') {
    enviando = true;
    Serial.println("t_us,tfl_mV,aductor_mV,marca");
  } else if (c == 'P') {
    enviando = false;
  } else if (c == 'B') {
    marcaPendiente = true;
    digitalWrite(PIN_BUZZER, HIGH);
    finPitido = millis() + PITIDO_MS;
  }
}

void setup() {
  Serial.begin(921600);                  // en USB-CDC nativo el valor se ignora
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_TFL, ADC_11db);
  analogSetPinAttenuation(PIN_ADUCTOR, ADC_11db);

  timer = timerBegin(1000000);           // 1 MHz
  timerAttachInterrupt(timer, &alTimer);
  timerAlarm(timer, 1000000 / FS_HZ, true, 0);
  Serial.println("# EMG Kapter-TEC (ESP32-C3) listo. Envia S para iniciar.");
}

void loop() {
  while (Serial.available()) procesarComando((char)Serial.read());

  if (finPitido && millis() >= finPitido) {
    digitalWrite(PIN_BUZZER, LOW);
    finPitido = 0;
  }

  if (tocaMuestra) {
    tocaMuestra = false;
    uint32_t t = micros();
    int tfl = analogReadMilliVolts(PIN_TFL);       // mV ya calibrados
    int adu = analogReadMilliVolts(PIN_ADUCTOR);
    int m = 0;
    if (marcaPendiente) { m = 1; marcaPendiente = false; }
    if (enviando) {
      char linea[40];
      int n = snprintf(linea, sizeof(linea), "%lu,%d,%d,%d\n", (unsigned long)t, tfl, adu, m);
      Serial.write((const uint8_t *)linea, n);
    }
  }
}
