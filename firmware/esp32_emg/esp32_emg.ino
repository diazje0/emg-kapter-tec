/*
  EMG Kapter-TEC — firmware para ESP32 clásica (Adafruit HUZZAH32 Feather)

  - Muestrea 2 canales a 2 kHz con un timer de hardware (ADC1, atenuación 11 dB).
  - Envía por USB serie y por Bluetooth clásico (SPP) líneas:  t_us,tfl_mV,aductor_mV,marca
  - Comandos que recibe (desde la app o un monitor serie):
        S = iniciar envío    P = pausar envío    B = pitido + marca de inicio (para la latencia)

  Conexiones (HUZZAH32):
        Salida canal TFL      -> A2 (GPIO 34)
        Salida canal aductor  -> A3 (GPIO 39)
        Buzzer activo 3.3 V   -> GPIO 21 (y GND)
        GND de la ESP32       -> GND2 (lado de SALIDA del ISO124). Nunca al lado del paciente.
  No usar GPIO 35 (A13): la placa lo usa para medir la batería.

  Probado con el core "esp32 by Espressif Systems" 3.x en Arduino IDE.
*/
#include "BluetoothSerial.h"

const int PIN_TFL     = 34;
const int PIN_ADUCTOR = 39;
const int PIN_BUZZER  = 21;
const uint32_t FS_HZ  = 2000;          // muestras por segundo por canal
const uint32_t PITIDO_MS = 120;

BluetoothSerial BT;
hw_timer_t *timer = nullptr;
volatile bool tocaMuestra = false;
volatile bool enviando = false;
volatile bool marcaPendiente = false;
uint32_t finPitido = 0;

void IRAM_ATTR alTimer() { tocaMuestra = true; }

void procesarComando(char c) {
  if (c == 'S') {
    enviando = true;
    Serial.println("t_us,tfl_mV,aductor_mV,marca");
    BT.println("t_us,tfl_mV,aductor_mV,marca");
  } else if (c == 'P') {
    enviando = false;
  } else if (c == 'B') {
    marcaPendiente = true;
    digitalWrite(PIN_BUZZER, HIGH);
    finPitido = millis() + PITIDO_MS;
  }
}

void setup() {
  Serial.begin(921600);
  BT.begin("EMG_KapterTEC");             // nombre que aparece al emparejar
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_TFL, ADC_11db);
  analogSetPinAttenuation(PIN_ADUCTOR, ADC_11db);

  timer = timerBegin(1000000);           // 1 MHz
  timerAttachInterrupt(timer, &alTimer);
  timerAlarm(timer, 1000000 / FS_HZ, true, 0);
  Serial.println("# EMG Kapter-TEC listo. Envia S para iniciar.");
}

void loop() {
  while (Serial.available()) procesarComando((char)Serial.read());
  while (BT.available())     procesarComando((char)BT.read());

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
      if (BT.hasClient()) BT.write((const uint8_t *)linea, n);
    }
  }
}
