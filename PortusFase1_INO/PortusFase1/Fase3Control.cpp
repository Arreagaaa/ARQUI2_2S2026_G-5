#include "Fase3Control.h"
#include "Config.h"
#include "Crane.h"

// Solo se energizan pines nuevos. Las rutas de Fase 1 no se modifican.
static bool lighting = false;
static bool capture = false;
static unsigned long lastCommand = 0;
static bool gateEnabled = false;
static int gateDecision = 0;
static unsigned long gateWaitMs = 10000UL;
static uint8_t gateRetention = 0;
static String gatePlate = "";
static String gateLabel = "";

bool fase3_gate_enabled() { return gateEnabled; }
void fase3_gate_begin() { gateDecision = 0; gateRetention = 0; gatePlate = ""; gateLabel = ""; }
int fase3_gate_decision() { return gateDecision; }
unsigned long fase3_gate_wait_ms() { return gateWaitMs; }
uint8_t fase3_gate_retention() { return gateRetention; }
String fase3_gate_plate() { return gatePlate; }
String fase3_gate_label() { return gateLabel; }

void fase3_init() {
  pinMode(PIN_F3_ILUMINACION, OUTPUT);
  pinMode(PIN_F3_BALIZA, OUTPUT);
  digitalWrite(PIN_F3_ILUMINACION, LOW);
  digitalWrite(PIN_F3_BALIZA, LOW);
  lastCommand = 0;
}

bool fase3_command(const String &command) {
  if (!command.startsWith("F3 ")) return false;
  String cmd = command.substring(3);
  cmd.trim(); cmd.toUpperCase();
  lastCommand = millis();
  if (cmd == "ILUMINACIONENCENDER") {
    lighting = true;
    Serial.println(F("@PORTUS Iluminacion;encendida=1"));
  } else if (cmd == "ILUMINACIONAPAGAR") {
    if (capture) { Serial.println(F("@PORTUS Iluminacion;rechazo=captura")); return true; }
    lighting = false;
    Serial.println(F("@PORTUS Iluminacion;encendida=0"));
  } else if (cmd == "GRUASUSPENDER CLIMA") {
    crane_setClimateSuspended(true);
    Serial.println(F("@PORTUS GruaSuspendida;motivo=Clima"));
  } else if (cmd == "GRUAREANUDAR CLIMA") {
    crane_setClimateSuspended(false);
    Serial.println(F("@PORTUS GruaReanudada;motivo=Clima"));
  } else if (cmd == "PING") {
    // Mantiene vivo el enlace sin cambiar salidas.
  } else if (cmd == "CAPTURAINICIO") {
    capture = true; lighting = true;
  } else if (cmd == "CAPTURAFIN") {
    capture = false;
  } else if (cmd == "GARITAMODO ON") {
    gateEnabled = true; gateDecision = 0;
    Serial.println(F("@PORTUS GaritaModo;activo=1"));
  } else if (cmd == "GARITAMODO OFF") {
    gateEnabled = false; gateDecision = 0;
    Serial.println(F("@PORTUS GaritaModo;activo=0"));
  } else if (cmd.startsWith("GARITARESULTADO ")) {
    String value = cmd.substring(16);
    int space = value.indexOf(' ');
    String result = space < 0 ? value : value.substring(0, space);
    gatePlate = space < 0 ? "" : value.substring(space + 1);
    if (result == "AUTORIZAR") {
      gateDecision = 1; gateRetention = 0; gateLabel = "PLACA VERIFICADA";
    } else if (result == "RETENER07") {
      gateDecision = 1; gateRetention = 7; gateLabel = "PLACA NO COINCIDE";
    } else if (result == "RETENER08") {
      gateDecision = 1; gateRetention = 8; gateLabel = "PLACA RESTRINGIDA";
    } else if (result == "RECHAZAR") {
      gateDecision = -1; gateLabel = "ACCESO DENEGADO";
    }
  } else if (cmd.startsWith("GARITAESPERA ")) {
    long seconds = cmd.substring(13).toInt();
    if (seconds >= 5 && seconds <= 30) gateWaitMs = (unsigned long)seconds * 1000UL;
  } else {
    Serial.println(F("@PORTUS Fase3;rechazo=comando_desconocido"));
  }
  digitalWrite(PIN_F3_ILUMINACION, lighting ? HIGH : LOW);
  return true;
}

void fase3_update() {
  // Si se corta el enlace, la iluminacion queda encendida. millis() evita
  // bloquear los pasos de la grua, el pesaje y el paro de emergencia.
  if (millis() - lastCommand > 15000UL && !lighting) {
    lighting = true;
    digitalWrite(PIN_F3_ILUMINACION, HIGH);
    Serial.println(F("@PORTUS Iluminacion;encendida=1;modo=SinEnlace"));
  }
  bool beacon = crane_isClimateSuspended() && ((millis() / 500UL) % 2 == 0);
  digitalWrite(PIN_F3_BALIZA, beacon ? HIGH : LOW);
}
