/*
  ============================================================
  PreloadedData.h - PORTUS Fase 1
  Aqui se precargan los registros de camiones, contenedores y
  manifiestos que exige el documento (6 a 8 operaciones, minimo
  3 camiones con RFID). EDITAR los UID de RFID con los reales
  de sus tags (usar el sketch de ejemplo de MFRC522 -> DumpInfo
  para leer el UID de cada tarjeta).
  ============================================================
*/
#ifndef PRELOADED_DATA_H
#define PRELOADED_DATA_H

#include "DataModels.h"

// ---------------- Camiones ----------------
static Camion CAMIONES[MAX_CAMIONES] = {
  // id, UID(4 bytes),          placa,      tara(kg), autorizado, registrado
  // AJUSTADO: taras reales medidas en la maqueta (antes 0.135 los 3, un
  // placeholder de una version anterior con camiones mucho mas livianos).
  {0, {0x39,0xBB,0x16,0xB3}, "P001AAA",  0.12,  true,  true},
  {1, {0xD9,0xD8,0x7B,0xD3}, "P002BBB",  2.24,  true,  true},
  {2, {0x55,0x66,0x77,0x88}, "P003CCC",  2.34,  true,  true},
  {3, {0,0,0,0}, "", 0, false, false},
  {4, {0,0,0,0}, "", 0, false, false},
  {5, {0,0,0,0}, "", 0, false, false}
};

// ---------------- Contenedores ----------------
// posicionPatio = -1 => todavia no esta en el patio (viene en un camion)
static Contenedor CONTENEDORES[MAX_CONTENEDORES] = {
  {0, "CT-001", 300.0, -1, 0, CONT_EN_CAMION,  true},
  {1, "CT-002", 280.0, -1, 0, CONT_EN_CAMION,  true},
  {2, "CT-003", 310.0,  0, 0, CONT_EN_PATIO,   true},  // ya en patio, posicion 0, nivel 0
  {3, "CT-004", 295.0, -1, 0, CONT_EN_CAMION,  true},
  {4, "CT-005", 305.0, -1, 0, CONT_EN_CAMION,  true},
  {5, "CT-006",   0.0, -1, 0, CONT_DESCONOCIDO, false},
  {6, "CT-007",   0.0, -1, 0, CONT_DESCONOCIDO, false},
  {7, "CT-008",   0.0, -1, 0, CONT_DESCONOCIDO, false},
  {8, "CT-009",   0.0, -1, 0, CONT_DESCONOCIDO, false},
  {9, "CT-010",   0.0, -1, 0, CONT_DESCONOCIDO, false}
};

// ---------------- Manifiestos ----------------
// Combinar depositos y retiros (documento pide 6-8 operaciones totales).
// Uno de ellos debe estar pensado para fallar el pesaje (escenario de rechazo),
// por ejemplo declarando un peso distinto al real fisico del contenedor de prueba.
static Manifiesto MANIFIESTOS[MAX_MANIFIESTOS] = {
  // AJUSTADO: toleranciaKg puesta enorme a pedido -- el pesaje ya NO
  // rechaza a nadie por peso, cualquier lectura entra "dentro de
  // tolerancia". pesoDeclaradoKg queda de los valores anteriores pero
  // ya no importa para la validacion (ver Stations.cpp: se compara
  // fabs(pesoLeido - pesoDeclaradoKg) <= toleranciaKg, y con una
  // tolerancia de 9999 eso siempre da true). Si en algun momento
  // quieren que la bascula vuelva a validar de verdad, hay que bajar
  // estos 9999.0 a un numero real otra vez.
  {0, 0, 0, OP_DEPOSITO, 2.67,  9999.0, MANIF_PENDIENTE, true},
  {1, 1, 1, OP_DEPOSITO, 0.47,  9999.0, MANIF_PENDIENTE, true},
  {2, 2, 2, OP_RETIRO,   0.065, 9999.0, MANIF_PENDIENTE, true},
  {3, 4, 3, OP_DEPOSITO, 999.0, 9999.0, MANIF_PENDIENTE, true}, // demo (camion no probado): provoca desvio
  {4, 3, 4, OP_DEPOSITO, 305.0, 9999.0, MANIF_PENDIENTE, true}, // demo (camion no probado)
  {5, 2, 2, OP_NINGUNA,    0.0, 0, MANIF_COMPLETADO, false}, // placeholder, no usar
  {6, 0, 0, OP_NINGUNA,    0.0, 0, MANIF_COMPLETADO, false},
  {7, 0, 0, OP_NINGUNA,    0.0, 0, MANIF_COMPLETADO, false}
};

// Busca el UNICO manifiesto pendiente para un camion. Devuelve -1 si no hay
// ninguno, o -2 si hay mas de uno (condicion de rechazo segun el documento).
inline int buscarManifiestoPendiente(uint8_t idCamion) {
  int encontrado = -1;
  int cuenta = 0;
  for (uint8_t i = 0; i < MAX_MANIFIESTOS; i++) {
    if (MANIFIESTOS[i].existe &&
        MANIFIESTOS[i].idCamion == idCamion &&
        MANIFIESTOS[i].estado == MANIF_PENDIENTE) {
      encontrado = i;
      cuenta++;
    }
  }
  if (cuenta == 0) return -1;
  if (cuenta > 1)  return -2;
  return encontrado;
}

inline int buscarCamionPorUID(byte *uid, byte uidSize) {
  for (uint8_t i = 0; i < MAX_CAMIONES; i++) {
    if (!CAMIONES[i].registrado) continue;
    bool coincide = true;
    for (byte b = 0; b < uidSize && b < 4; b++) {
      if (CAMIONES[i].rfidUID[b] != uid[b]) { coincide = false; break; }
    }
    if (coincide) return i;
  }
  return -1;
}

#endif
