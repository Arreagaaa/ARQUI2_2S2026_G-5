/*
  ============================================================
  Console.h - PORTUS Fase 1
  Consola serial de supervision local (sustituye cualquier
  interfaz grafica en esta fase). Comandos disponibles:

    ESTADO      -> resumen general de turnos activos
    PATIO       -> estado de cada posicion del patio
    GRUA        -> estado de la grua (referenciada / idle / trabajo actual)
    PESAJE      -> ultima lectura registrada
    REARME      -> intenta rearmar tras un paro de emergencia
    AYUDA       -> lista de comandos

  Ademas emite automaticamente un latido estructurado cada 5 segundos
  ([SEQ:HB:LatidoEstado::CRC]) para que el puente Serial-MQTT de
  Fase 2 supervise el enlace y genere AL01 solo con corte real.
  ============================================================
*/
#ifndef CONSOLE_H
#define CONSOLE_H

void console_init();
void console_update(); // llamar una vez por loop(); incluye el latido de 5s

#endif
