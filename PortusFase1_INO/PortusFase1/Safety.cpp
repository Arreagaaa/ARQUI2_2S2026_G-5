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

  CAMBIADO (diagnostico en campo, pedido del usuario): la ISR
  actuaba directo sobre el primer flanco FALLING que veia
  (alternaba estopActivo y llamaba crane_emergencyHalt() ahi
  mismo). El debounce de 250ms solo protege contra VARIOS flancos
  de UNA misma pulsacion real -- no filtra un pulso de ruido
  electrico aislado, y el motor paso a paso (28BYJ-48+ULN2003)
  es candidato tipico a inducir un flanco falso en un pin cercano
  al frenar/arrancar (mas si el cable del boton no esta blindado o
  comparte tierra con el driver). Eso explicaba que la grua
  quedara en E-stop -- electroiman forzado a ENERGIZADO, ver
  crane_emergencyHalt() -- justo al terminar un trabajo, sin que
  nadie tocara el boton.
  Ahora la ISR NO actua sola: solo anota que vio un flanco y CUANDO
  (pendienteConfirmarMs). safety_update(), llamada desde loop() en
  cada iteracion, confirma la pulsacion solo si el pin SIGUE en LOW
  despues de la ventana de debounce -- un pulso de ruido (que no
  sostiene el pin en LOW) se descarta sin llegar a frenar la grua.
  Un boton real, sostenido durante el debounce, se sigue detectando
  con el mismo tiempo de reaccion de antes (~250ms).
  ============================================================
*/
#include "Safety.h"
#include "Config.h"
#include "Crane.h"

static volatile bool estopActivo = false;
static volatile uint32_t ultimoCambioMs = 0;
#define DEBOUNCE_MS 250

// AGREGADO: bandera que pone la ISR cuando ve un flanco FALLING fuera de
// la ventana de debounce -- ya NO decide ahi mismo si es un boton real,
// eso lo confirma safety_update() releyendo el pin.
static volatile bool pendienteConfirmar = false;
static volatile uint32_t pendienteConfirmarMs = 0;

static bool justRearmed = false;
static char ultimaCausa[48] = "Ninguna";

// ISR real de interrupcion externa (INT2 / pin 21 en el Mega).
// Ya NO alterna estopActivo ni llama a crane_emergencyHalt() aqui --
// eso se movio a safety_update(), despues de confirmar que el pin
// sigue en LOW (ver comentario arriba). La ISR se mantiene minima
// a proposito.
void ISR_paroEmergencia() {
  uint32_t ahora = millis();
  if (ahora - ultimoCambioMs < DEBOUNCE_MS) return; // ignorar rebote
  ultimoCambioMs = ahora;
  pendienteConfirmar = true;
  pendienteConfirmarMs = ahora;
}

void safety_init() {
  pinMode(PIN_PARO_EMERGENCIA, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_PARO_EMERGENCIA), ISR_paroEmergencia, FALLING);
}

// AGREGADO: llamar en cada iteracion de loop(), lo antes posible (antes
// de leer safety_isEstopActive() para decidir el resto del ciclo).
void safety_update() {
  if (!pendienteConfirmar) return;
  if (millis() - pendienteConfirmarMs < DEBOUNCE_MS) return; // todavia esperando la ventana

  noInterrupts();
  pendienteConfirmar = false;
  interrupts();

  // Confirmacion real: si el pin ya NO esta en LOW, el flanco que vio la
  // ISR fue ruido (un pulso que no se sostuvo), no un boton real -- se
  // descarta sin frenar nada. INPUT_PULLUP + boton normal: LOW = presionado.
  if (digitalRead(PIN_PARO_EMERGENCIA) != LOW) return;

  estopActivo = !estopActivo;
  if (estopActivo) {
    crane_emergencyHalt();
  }
  // Si se desactivo (reanudacion), el resto del rearme (re-referenciar
  // grua, avisar por consola) se procesa en safety_requestRearm(),
  // llamada automaticamente desde loop() cuando detecta el cambio.
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

