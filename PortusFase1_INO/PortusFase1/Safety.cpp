/*
  ============================================================
  Safety.cpp - PORTUS Fase 1

  IMPORTANTE: adaptado para boton pulsador NORMAL (momentaneo,
  no se queda trabado como los de hongo). Cada pulsacion ALTERNA
  el estado: la primera detiene todo, la segunda reanuda solo.
  Ya no requiere el comando REARME por consola, aunque se deja
  disponible como respaldo manual.

  El debounce (250ms) evita que el rebote electrico de un solo
  toque fisico se cuente como varias pulsaciones.
  ============================================================
*/
#include "Safety.h"
#include "Config.h"
#include "Crane.h"

static volatile bool estopActivo = false;
static volatile uint32_t ultimoCambioMs = 0;
#define DEBOUNCE_MS 250

static bool justRearmed = false;
static char ultimaCausa[48] = "Ninguna";

// ISR real de interrupcion externa (INT2 / pin 21 en el Mega).
// Alterna el estado en cada pulsacion valida (fuera de la ventana
// de debounce). Solo hace lo minimo indispensable; el resto de
// logica (mensajes, re-referenciar grua) se resuelve en el loop.
void ISR_paroEmergencia() {
  uint32_t ahora = millis();
  if (ahora - ultimoCambioMs < DEBOUNCE_MS) return; // ignorar rebote
  ultimoCambioMs = ahora;

  estopActivo = !estopActivo;
  if (estopActivo) {
    crane_emergencyHalt();
  }
  // Si se desactivo (reanudacion), el resto del rearme (re-referenciar
  // grua, avisar por consola) se procesa en safety_requestRearm(),
  // llamada automaticamente desde loop() cuando detecta el cambio.
}

void safety_init() {
  pinMode(PIN_PARO_EMERGENCIA, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_PARO_EMERGENCIA), ISR_paroEmergencia, FALLING);
}

bool safety_isEstopActive() {
  return estopActivo;
}

// Se llama cada iteracion de loop(). Detecta cuando el boton acaba de
// desactivar el estop (reanudacion automatica) y hace el trabajo de
// rearme: re-referenciar la grua y avisar. Tambien sigue aceptando el
// comando REARME por consola como respaldo manual, por si el boton
// fisico fallara.
void safety_requestRearm() {
  if (estopActivo) {
    safety_reportarCausa("No se puede rearmar: paro sigue activo (vuelva a pulsar el boton)");
    return;
  }
  estopActivo = false;
  justRearmed = true;
  crane_forceReReference(); // tras un E-stop no se asume que el ultimo
                             // movimiento termino correctamente
  safety_reportarCausa("Rearme confirmado");
}

bool safety_wasJustRearmed() {
  bool v = justRearmed;
  justRearmed = false;
  return v;
}

void safety_reportarCausa(const char *causa) {
  strncpy(ultimaCausa, causa, sizeof(ultimaCausa) - 1);
  ultimaCausa[sizeof(ultimaCausa) - 1] = '\0';
}

const char* safety_getUltimaCausa() { return ultimaCausa; }

