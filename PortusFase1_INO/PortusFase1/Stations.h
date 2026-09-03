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

// AGREGADO: libera todos los turnos y regresa las 4 maquinas de estado
// locales (garita/pesaje/transferencia/salida) a su condicion de reposo,
// sin repetir la inicializacion de hardware (pines/LCD/RFID quedan
// como estaban). Pensado para el comando REINICIAR de consola, que
// permite repetir una prueba/demostracion completa sin recargar el
// sketch. Debe usarse solo con la maqueta despejada (ningun camion bajo
// una talanquera ni en la zona de transferencia).
void stations_resetTurnos();

// Utilidades de consulta para la consola serial
uint8_t stations_contarTurnosActivos();
void stations_imprimirEstadoTurno(uint8_t indice);

#endif
