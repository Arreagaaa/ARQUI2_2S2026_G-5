/*
  ============================================================
  Stations.h - PORTUS Fase 1
  Maquinas de estado no bloqueantes de: garita, pesaje/aguja,
  zona de transferencia y salida. Administra el arreglo de
  Turnos (una entrada por camion activo dentro de la terminal).
  ============================================================
*/
#ifndef STATIONS_H
#define STATIONS_H

#include <Arduino.h>
#include "DataModels.h"

void stations_init();

// Llamar una vez por loop(). Internamente recorre todos los turnos
// activos y avanza cada maquina de estados de forma independiente,
// tal como exige el documento (una estacion nunca debe tocar el
// turno de otro vehiculo).
void stations_update();

// Utilidades de consulta para la consola serial
uint8_t stations_contarTurnosActivos();
void stations_imprimirEstadoTurno(uint8_t indice);

#endif
