/*
  ============================================================
  DataModels.h - PORTUS Fase 1
  Modelos de datos locales: Camion, Contenedor, Manifiesto, Turno.
  Todo vive en RAM/PROGMEM del Mega, no hay base de datos externa.
  ============================================================
*/
#ifndef DATA_MODELS_H
#define DATA_MODELS_H

#include <Arduino.h>

#define MAX_CAMIONES     6
#define MAX_CONTENEDORES 10
#define MAX_MANIFIESTOS  8
#define MAX_TURNOS       6   // turnos concurrentes activos

// ---------------- Camion ----------------
struct Camion {
  uint8_t id;
  byte    rfidUID[4];      // UID de 4 bytes del tag (ajustar si el tag usa 7)
  char    placa[9];
  float   taraKg;
  bool    autorizadoLocal;
  bool    registrado;
};

// ---------------- Contenedor ----------------
enum EstadoContenedor { CONT_EN_CAMION, CONT_EN_PATIO, CONT_EN_TRANSITO, CONT_DESCONOCIDO };

struct Contenedor {
  uint8_t id;
  char    codigo[7];        // identificador visible/legible
  float   pesoDeclaradoKg;
  int8_t  posicionPatio;     // -1 si no esta en patio
  uint8_t nivelPatio;        // 0 = piso, 1 = segundo nivel
  EstadoContenedor estado;
  bool    existe;
};

// ---------------- Manifiesto ----------------
enum TipoOperacion { OP_DEPOSITO, OP_RETIRO, OP_NINGUNA };
enum EstadoManifiesto { MANIF_PENDIENTE, MANIF_EN_PROCESO, MANIF_COMPLETADO, MANIF_RECHAZADO };

struct Manifiesto {
  uint8_t id;
  uint8_t idCamion;
  uint8_t idContenedor;
  TipoOperacion tipo;
  float   pesoDeclaradoKg;
  float   toleranciaKg;
  EstadoManifiesto estado;
  bool    existe;
};

// ---------------- Turno ----------------
// Representa la ejecucion en curso de UNA operacion dentro de la terminal.
// Cada camion presente en la terminal tiene, a lo sumo, un turno activo.
enum Estacion {
  EST_NINGUNA,
  EST_ESPERA,
  EST_GARITA,
  EST_PESAJE,
  EST_RAMAL_RETENIDO,
  EST_TRANSFERENCIA,
  EST_SALIDA,
  EST_FINALIZADO
};

struct Turno {
  uint8_t   id;
  bool      activo;
  uint8_t   idCamion;
  uint8_t   idManifiesto;
  Estacion  estacionActual;
  Estacion  siguienteEstacion;
  float     pesajeInicialKg;
  float     pesajeFinalKg;
  bool      pesajeInicialValido;
  bool      pesajeFinalValido;
  int8_t    posicionPatioAsignada;   // para deposito/retiro
  bool      retenido;                // true si fue desviado al ramal
  bool      esperandoGrua;
  uint8_t   idsTrabajoGrua[3];       // trabajos de grua asociados (deposito/remociones/retiro)
  uint8_t   cantidadTrabajosGrua;
  uint32_t  timestampInicioMs;
};

#endif
