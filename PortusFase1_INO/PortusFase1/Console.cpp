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
#include "PreloadedData.h"
#include <Arduino.h>

static String buffer = "";

// --- Latido periodico para Fase 2 (puente Serial-MQTT de la Raspberry) ---
// El puente reinicia su supervision de enlace con cualquier trama valida y
// dispara AL01 tras 15 s (3 periodos de 5 s) de silencio. Sin latido, una
// maqueta en reposo generaria alarmas falsas, por eso se emite aunque no
// ocurra ningun evento fisico. Formato identico a SerialProtocol.build_frame:
//   [SEQ:HB:LatidoEstado::CRC]   CRC16-CCITT sobre "SEQ:HB:LatidoEstado:"
static uint32_t latidoSeq = 0;
static unsigned long latidoUltimoMs = 0;
static const unsigned long LATIDO_INTERVALO_MS = 5000UL;

static uint16_t crc16Ccitt(const String &s) {
  uint16_t crc = 0xFFFF;
  for (unsigned i = 0; i < s.length(); i++) {
    crc ^= (uint16_t)s[i] << 8;
    for (uint8_t b = 0; b < 8; b++) {
      if (crc & 0x8000) crc = (uint16_t)((crc << 1) ^ 0x1021);
      else               crc = (uint16_t)(crc << 1);
    }
  }
  return crc;
}

static void enviarLatido() {
  String contenido = String(latidoSeq) + ":HB:LatidoEstado:";
  char crcHex[6];
  snprintf(crcHex, sizeof(crcHex), "%04X", crc16Ccitt(contenido));
  Serial.print('[');
  Serial.print(contenido);
  Serial.print(':');
  Serial.print(crcHex);
  Serial.println(']');
  latidoSeq++;
}

static void imprimirAyuda() {
  Serial.println(F("Comandos disponibles:"));
  Serial.println(F("  ESTADO  - resumen de turnos activos"));
  Serial.println(F("  PATIO   - estado de cada posicion del patio"));
  Serial.println(F("  GRUA    - estado general de la grua"));
  Serial.println(F("  REARME  - solicita rearme tras paro de emergencia"));
  Serial.println(F("  CRUDO   - lectura cruda de las celdas (para calibrar)"));
  Serial.println(F("  TARA    - re-zera el offset con la plataforma vacia (sin recompilar)"));
  Serial.println(F("  REINICIAR - reinicia turnos/grua/patio/manifiestos para repetir una prueba SIN recargar el sketch (usar con la maqueta despejada)"));
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
    stations_imprimirTelemetria();
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
    yard_imprimirTelemetria();
  } else if (cmd == "GRUA") {
    crane_imprimirTelemetria();
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
  } else if (cmd == "REINICIAR") {
    // AGREGADO: permite repetir una demostracion/prueba completa desde
    // cero sin tener que recargar el sketch en el Arduino. El orden
    // importa: primero se limpian turnos y grua (para no dejar
    // punteros a un turno que esta a punto de desaparecer), despues se
    // reinician los datos precargados (contenedores/manifiestos) y por
    // ultimo el patio, que se reconstruye a partir de esos datos.
    stations_resetTurnos();
    crane_resetQueue();
    preloadedData_reset();
    yard_reset();
    safety_reportarCausa("Sistema reiniciado por consola (REINICIAR)");
    Serial.println(F("Listo: turnos, grua (cola), patio y manifiestos vueltos al estado inicial."));
    Serial.println(F("La grua conserva su referenciado (no hace falta volver a hacer home)."));
  } else if (cmd.length() > 0) {
    Serial.println(F("Comando no reconocido. Escriba AYUDA."));
  }
}

void console_init() {
  Serial.begin(115200);
  Serial.println(F("=== PORTUS Fase 1 - Consola de supervision local ==="));
  imprimirAyuda();
  latidoUltimoMs = millis(); // primer latido a los 5 s de arrancar
}

void console_update() {
  // Latido de enlace para Fase 2: se emite SIEMPRE (tambien con el paro
  // de emergencia activo), porque el enlace serial sigue estando vivo.
  unsigned long ahora = millis();
  if (ahora - latidoUltimoMs >= LATIDO_INTERVALO_MS) {
    latidoUltimoMs = ahora;
    enviarLatido();
  }

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
