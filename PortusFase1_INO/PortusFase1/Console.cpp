/*
  ============================================================
  Console.cpp - PORTUS Fase 1
  Lectura no bloqueante de Serial: acumula caracteres hasta '\n'
  y despacha el comando. No usa Serial.readStringUntil() porque
  esa llamada es bloqueante.
  ============================================================
*/
#include "Console.h"
#include "Config.h"
#include "Stations.h"
#include "Yard.h"
#include "Crane.h"
#include "Weighing.h"
#include "Safety.h"
#include <Arduino.h>

static String buffer = "";

static void imprimirAyuda() {
  Serial.println(F("Comandos disponibles:"));
  Serial.println(F("  ESTADO  - resumen de turnos activos"));
  Serial.println(F("  PATIO   - estado de cada posicion del patio"));
  Serial.println(F("  GRUA    - estado general de la grua"));
  Serial.println(F("  REARME  - solicita rearme tras paro de emergencia"));
  Serial.println(F("  CRUDO   - lectura cruda de las celdas (para calibrar)"));
  Serial.println(F("  TARA    - re-zera el offset con la plataforma vacia (sin recompilar)"));
  Serial.println(F("  AYUDA   - esta lista"));
}

static void procesarComando(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "AYUDA") {
    imprimirAyuda();
  } else if (cmd == "ESTADO") {
    uint8_t n = stations_contarTurnosActivos();
    Serial.print(F("Turnos activos: ")); Serial.println(n);
    for (uint8_t i = 0; i < 6; i++) stations_imprimirEstadoTurno(i);
    if (safety_isEstopActive()) {
      Serial.println(F(">>> PARO DE EMERGENCIA ACTIVO <<<"));
    }
    Serial.print(F("Ultima causa registrada: ")); Serial.println(safety_getUltimaCausa());
  } else if (cmd == "PATIO") {
    for (uint8_t i = 0; i < YARD_POS_COUNT; i++) {
      Serial.print(F("Posicion ")); Serial.print(i);
      Serial.print(F(": estado="));
      switch (yard_getEstado(i)) {
        case POS_LIBRE:     Serial.print(F("LIBRE")); break;
        case POS_RESERVADA: Serial.print(F("RESERVADA")); break;
        case POS_OCUPADA:   Serial.print(F("OCUPADA")); break;
        case POS_BLOQUEADA: Serial.print(F("BLOQUEADA")); break;
      }
      Serial.print(F(" niveles=")); Serial.println(yard_getNiveles(i));
    }
  } else if (cmd == "GRUA") {
    Serial.print(F("Referenciada: ")); Serial.println(crane_isReferenced() ? "SI" : "NO");
    Serial.print(F("Libre (idle): ")); Serial.println(crane_isIdle() ? "SI" : "NO");
  } else if (cmd == "REARME") {
    safety_requestRearm();
    if (safety_wasJustRearmed()) Serial.println(F("Rearme completado."));
    else Serial.println(F("No se pudo rearmar (revisar boton de paro)."));
  } else if (cmd == "CRUDO") {
    long suma, a, b;
    if (weighing_readRawNow(suma, a, b)) {
      Serial.print(F("Celda A: "));
      Serial.print(a);
      Serial.print(F("  |  Celda B: "));
      Serial.print(b);
      Serial.print(F("  |  Suma (usada por el sistema): "));
      Serial.println(suma);
    } else {
      Serial.println(F("Timeout leyendo HX711, revisar cableado (SCK/DOUT)."));
    }
  } else if (cmd == "TARA") {
    Serial.println(F("Tarando... asegurate de que la plataforma este VACIA."));
    long nuevoOffset;
    if (weighing_tare(nuevoOffset)) {
      Serial.print(F("Listo. Nuevo offset (temporal, solo dura hasta apagar): "));
      Serial.println(nuevoOffset);
    } else {
      Serial.println(F("No se pudo tarar (timeout HX711), revisar cableado."));
    }
  } else if (cmd.length() > 0) {
    Serial.println(F("Comando no reconocido. Escriba AYUDA."));
  }
}

void console_init() {
  Serial.begin(115200);
  Serial.println(F("=== PORTUS Fase 1 - Consola de supervision local ==="));
  imprimirAyuda();
}

void console_update() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buffer.length() > 0) { procesarComando(buffer); buffer = ""; }
    } else {
      buffer += c;
      if (buffer.length() > 40) buffer = ""; // proteccion contra basura
    }
  }
}
