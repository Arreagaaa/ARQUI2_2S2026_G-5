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
  ============================================================
*/
#ifndef CONSOLE_H
#define CONSOLE_H

void console_init();
void console_update(); // llamar una vez por loop()

#endif
