/*
  EMG Kapter-TEC — firmware para ESP32 (DevKit "convencional", WROOM-32) y ESP32-C3

  Muestrea 2 canales a 2 kHz con un timer de hardware y envía por USB líneas:
        t_us,tfl_mV,aductor_mV,marca
  Comandos que recibe (desde la app o el Monitor serie):
        S = iniciar envío    P = pausar envío    B = pitido + marca de inicio (para la latencia)

  El mismo archivo sirve para las dos placas: elige la placa correcta en el Arduino IDE
  y los pines se ajustan solos.

  ---------------- ESP32 DevKit (ESP32-WROOM-32) ----------------
        Salida canal TFL      -> GPIO 34  (D34, ADC1)
        Salida canal aductor  -> GPIO 35  (D35, ADC1)
        Buzzer activo 3.3 V   -> GPIO 25  (D25)  y GND
        GND de la ESP32       -> GND2 (lado de SALIDA del ISO124). Nunca al lado del paciente.
     Rango útil del ADC: ~0.15 a ~3.1 V. Centrar la salida en ~1.65 V está bien.
     Usar solo pines ADC1 (32–39): los ADC2 no funcionan bien junto con el Bluetooth/WiFi.
     Arduino IDE: placa "ESP32 Dev Module", Upload Speed 921600.

  ---------------- ESP32-C3 (SuperMini, DevKitM) ----------------
        TFL -> GPIO 0 · aductor -> GPIO 1 · buzzer -> GPIO 10
     Rango útil del ADC: ~0 a ~2.5 V (centrar la salida en ~1.25 V).
     Arduino IDE: placa "ESP32C3 Dev Module", USB CDC On Boot: "Enabled".

  Core requerido: "esp32 by Espressif Systems" versión 3.x.
*/

#if defined(CONFIG_IDF_TARGET_ESP32C3)
  const int PIN_TFL = 0, PIN_ADUCTOR = 1, PIN_BUZZER = 10;
  const char *PLACA = "ESP32-C3";
#else
  const int PIN_TFL = 34, PIN_ADUCTOR = 35, PIN_BUZZER = 25;
  const char *PLACA = "ESP32";
#endif

const uint32_t BAUDIOS  = 921600;      // debe coincidir con la app (en el C3 con USB nativo se ignora)
const uint32_t FS_HZ    = 2000;        // muestras por segundo por canal
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
  Serial.setTxBufferSize(4096);
  Serial.begin(BAUDIOS);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_TFL, ADC_11db);
  analogSetPinAttenuation(PIN_ADUCTOR, ADC_11db);

  timer = timerBegin(1000000);                     // 1 MHz
  timerAttachInterrupt(timer, &alTimer);
  timerAlarm(timer, 1000000 / FS_HZ, true, 0);     // interrupción cada 500 us

  delay(300);
  Serial.printf("# EMG Kapter-TEC listo (%s). Envia S para iniciar.\n", PLACA);
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
    int tfl = analogReadMilliVolts(PIN_TFL);       // mV ya calibrados de fábrica
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
