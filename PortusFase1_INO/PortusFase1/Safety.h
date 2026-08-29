/*
  ============================================================
  Safety.h - PORTUS Fase 1
  Paro de emergencia atendido por interrupcion externa real
  (no por revision periodica de una variable). Requiere rearme
  explicito tras liberar el pulsador.
  ============================================================
*/
#ifndef SAFETY_H
#define SAFETY_H

#include <Arduino.h>

void safety_init();

// true mientras el sistema esta detenido por E-stop (pulsador presionado
// o pendiente de rearme explicito)
bool safety_isEstopActive();

// Debe llamarse desde loop() para procesar el rearme (por ejemplo, cuando
// el operador confirma por consola serial "REARME").
void safety_requestRearm();

// true una sola vez, el ciclo en que efectivamente se completo el rearme
bool safety_wasJustRearmed();

// Registro de la ultima causa de error/retencion, para mostrar en pantallas
// y consola. Los distintos modulos llaman a esto para reportar la causa
// concreta exigida por el documento (nunca dejar un rechazo sin explicar).
void safety_reportarCausa(const char *causa);
const char* safety_getUltimaCausa();

#endif
