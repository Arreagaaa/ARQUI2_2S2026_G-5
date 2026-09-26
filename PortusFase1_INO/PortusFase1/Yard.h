/*
  ============================================================
  Yard.h - PORTUS Fase 1
  Patio lineal apilable (YARD_POS_COUNT posiciones, hasta
  YARD_MAX_NIVELES contenedores por posicion). El inventario
  SOLO se modifica despues de una confirmacion fisica (sensor
  de ocupacion en la base), nunca al emitir el comando de
  movimiento.
  ============================================================
*/
#ifndef YARD_H
#define YARD_H

#include <Arduino.h>

enum EstadoPosicion { POS_LIBRE, POS_RESERVADA, POS_OCUPADA, POS_BLOQUEADA };

void yard_init();

// AGREGADO: reinicia el inventario del patio a su estado de fabrica
// (mismo resultado que yard_init(), pero sin repetir pinMode()), para
// poder repetir pruebas completas desde la consola serial (comando
// REINICIAR) sin recargar el sketch. Debe llamarse DESPUES de
// preloadedData_reset(), ya que reconstruye el patio a partir de
// CONTENEDORES[] (posicionPatio/nivelPatio/estado).
void yard_reset();

// Debe llamarse una vez por loop(); refresca lectura de sensores de base
// y actualiza los LED de estado de cada posicion.
void yard_update();

// Politica de asignacion: primera posicion libre y accesible segun el
// orden fisico (0..YARD_POS_COUNT-1). Devuelve -1 si no hay ninguna.
int8_t yard_buscarPosicionLibre();

// true si la posicion (0-index) esta libre y accesible para depositar
bool yard_esAccesible(int8_t posicion);

uint8_t yard_getNiveles(int8_t posicion);

void yard_reservarPosicion(int8_t posicion);
void yard_ocuparPosicion(int8_t posicion, uint8_t idContenedor);
void yard_liberarPosicion(int8_t posicion);
void yard_marcarBloqueada(int8_t posicion);

// Lee el sensor de ocupacion fisico de la posicion y compara contra lo
// que el inventario espera. Devuelve false si hay inconsistencia
// (en cuyo caso tambien marca la posicion como bloqueada).
bool yard_confirmarFisicamente(int8_t posicion);

// Ubica en que posicion/nivel del patio esta un contenedor. -1 si no esta.
int8_t yard_localizarContenedor(uint8_t idContenedor);

EstadoPosicion yard_getEstado(int8_t posicion);

void yard_imprimirTelemetria();

#endif
