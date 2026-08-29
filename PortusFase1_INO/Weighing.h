/*
  ============================================================
  Weighing.h - PORTUS Fase 1
  Pesaje dinamico con 2 x HX711 sincronizados (reloj compartido,
  datos separados). El muestreo se dispara por interrupcion de
  Timer1 (no bloqueante): el resto del sistema sigue corriendo
  mientras se arma la meseta de lectura.
  ============================================================
*/
#ifndef WEIGHING_H
#define WEIGHING_H

#include <Arduino.h>

void weighing_init();

// Debe llamarse una vez por ciclo de loop(); es liviano, solo revisa
// banderas dejadas por la ISR y actualiza la deteccion de meseta.
void weighing_update();

// Inicia una nueva captura (se llama cuando el IR de la plataforma
// detecta el frente del camion). Reinicia buffer y bandera de listo.
void weighing_startCapture();

// true cuando ya se detecto una meseta estable de duracion >= MESETA_MIN_MS
bool weighing_resultReady();

// Peso resultante en kg (valido solo si weighing_resultReady() es true)
float weighing_getResultKg();

// Peso "en vivo" (mediana de las ultimas 5 muestras, sin confirmar
// estabilidad de meseta aun). Util para monitoreo en consola.
float weighing_getLiveKg();

// Lectura cruda sin calibrar (para el proceso de calibracion)
long weighing_getLiveRaw();

// Lectura directa bajo demanda de las celdas, sin depender del ciclo
// de captura de un camion. Usar solo desde el proceso de calibracion.
// sumaCruda = celdaA + celdaB (lo que usa el sistema normalmente)
bool weighing_readRawNow(long &sumaCruda, long &celdaA, long &celdaB);

// TARA: re-establece OFFSET_CAL con la lectura actual (plataforma
// vacia), sin recompilar/resubir. El valor solo dura mientras la
// placa este encendida; si se apaga, se pierde y hay que tarar de
// nuevo. Devuelve el nuevo offset por referencia.
bool weighing_tare(long &nuevoOffset);

// Limpia el resultado para la proxima captura (pesaje inicial vs final)
void weighing_reset();

#endif
