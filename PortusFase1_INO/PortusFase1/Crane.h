#ifndef CRANE_H
#define CRANE_H

#include <Arduino.h>

enum TipoTrabajoGrua { TRABAJO_DEPOSITO, TRABAJO_RETIRO, TRABAJO_REMOCION };
enum EstadoTrabajo   { TRABAJO_PENDIENTE, TRABAJO_EJECUTANDO, TRABAJO_COMPLETADO, TRABAJO_ERROR };

struct TrabajoGrua {
  uint8_t id;
  bool    activo;
  TipoTrabajoGrua tipo;
  uint8_t idTurno;
  int8_t  posicionOrigen;
  int8_t  posicionDestino;
  uint8_t idContenedor;
  EstadoTrabajo estado;
  uint32_t timestampCreacion;
};

void crane_init();
void crane_update();
void crane_timerTick();
int  crane_enqueue(TipoTrabajoGrua tipo, uint8_t idTurno, int8_t origen, int8_t destino, uint8_t idContenedor);
bool crane_isJobDone(uint8_t idTrabajo);
bool crane_isJobError(uint8_t idTrabajo);
bool crane_isIdle();
bool crane_isReferenced();
void crane_forceReReference();
void crane_emergencyHalt();

// AGREGADO: vacia la cola de trabajos y deja la maquina de estados de la
// grua en G_INACTIVA, para el comando REINICIAR de consola (repetir
// pruebas sin recargar el sketch). A proposito NO toca el referenciado
// (posicionActual/referenciada): la grua conserva su "home" fisico y no
// necesita volver a referenciarse entre pruebas. Solo debe invocarse con
// la maqueta despejada (sin un trabajo realmente en curso), igual que un
// paro de emergencia: si se llama a mitad de un movimiento, este se
// corta de golpe.
void crane_resetQueue();

void crane_imprimirTelemetria();

#endif