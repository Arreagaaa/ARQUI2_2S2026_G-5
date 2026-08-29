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

#endif