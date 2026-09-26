/*
  ============================================================
  Yard.cpp - PORTUS Fase 1

  Patio de 2 posiciones x 2 niveles. Cada nivel tiene su propio
  sensor LDR (YARD_OCC_PIN[posicion][nivel]), leido con analogRead()
  (los LDR son sensores analogicos, no digitales), lo que permite
  distinguir 0, 1 o 2 contenedores apilados en cada posicion.
  ============================================================
*/
#include "Yard.h"
#include "Config.h"
#include "PreloadedData.h"

struct PosicionPatio {
  EstadoPosicion estado;
  uint8_t nivelesOcupados;          // 0, 1 o 2
  uint8_t idContenedor[YARD_MAX_NIVELES]; // id por nivel (255 = vacio)
};

static PosicionPatio patio[YARD_POS_COUNT];

void yard_init() {
  for (uint8_t i = 0; i < YARD_POS_COUNT; i++) {
    // Los LDR se leen con analogRead(): no necesitan pinMode ni pull-up,
    // el propio divisor de voltaje (LDR + resistencia externa a GND)
    // ya fija el nivel de voltaje que el ADC del Mega lee directamente.
    pinMode(YARD_LED_PIN[i], OUTPUT);
    patio[i].estado = POS_LIBRE;
    patio[i].nivelesOcupados = 0;
    for (uint8_t n = 0; n < YARD_MAX_NIVELES; n++) patio[i].idContenedor[n] = 255;
  }
  // Sincroniza con los contenedores precargados que ya vienen ubicados en patio
  for (uint8_t c = 0; c < MAX_CONTENEDORES; c++) {
    if (CONTENEDORES[c].existe && CONTENEDORES[c].estado == CONT_EN_PATIO) {
      int8_t p = CONTENEDORES[c].posicionPatio;
      uint8_t n = CONTENEDORES[c].nivelPatio;
      if (p >= 0 && p < YARD_POS_COUNT && n < YARD_MAX_NIVELES) {
        patio[p].idContenedor[n] = CONTENEDORES[c].id;
        patio[p].nivelesOcupados = max(patio[p].nivelesOcupados, (uint8_t)(n + 1));
        patio[p].estado = POS_OCUPADA;
      }
    }
  }
}

// AGREGADO: mismo cuerpo que la parte de yard_init() que reconstruye el
// patio (sin repetir pinMode(), que ya quedo hecho desde el arranque).
// Pensado para el comando REINICIAR de consola: hay que llamarla DESPUES
// de preloadedData_reset(), porque lee CONTENEDORES[] para saber que
// quedo dentro del patio (igual que hace yard_init() al arrancar).
void yard_reset() {
  for (uint8_t i = 0; i < YARD_POS_COUNT; i++) {
    patio[i].estado = POS_LIBRE;
    patio[i].nivelesOcupados = 0;
    for (uint8_t n = 0; n < YARD_MAX_NIVELES; n++) patio[i].idContenedor[n] = 255;
  }
  for (uint8_t c = 0; c < MAX_CONTENEDORES; c++) {
    if (CONTENEDORES[c].existe && CONTENEDORES[c].estado == CONT_EN_PATIO) {
      int8_t p = CONTENEDORES[c].posicionPatio;
      uint8_t n = CONTENEDORES[c].nivelPatio;
      if (p >= 0 && p < YARD_POS_COUNT && n < YARD_MAX_NIVELES) {
        patio[p].idContenedor[n] = CONTENEDORES[c].id;
        patio[p].nivelesOcupados = max(patio[p].nivelesOcupados, (uint8_t)(n + 1));
        patio[p].estado = POS_OCUPADA;
      }
    }
  }
}

// LED simple: se aprovecha software-blink para representar los 4 estados
// con un solo pin (libre=apagado, reservada=parpadeo lento, ocupada=fijo,
// bloqueada=parpadeo rapido).
static void actualizarLed(uint8_t idx) {
  uint32_t t = millis();
  bool on = false;
  switch (patio[idx].estado) {
    case POS_LIBRE:     on = false; break;
    case POS_OCUPADA:   on = true;  break;
    case POS_RESERVADA: on = ((t / 400) % 2 == 0); break;
    case POS_BLOQUEADA: on = ((t / 120) % 2 == 0); break;
  }
  digitalWrite(YARD_LED_PIN[idx], on ? HIGH : LOW);
}

void yard_update() {
  for (uint8_t i = 0; i < YARD_POS_COUNT; i++) actualizarLed(i);

  // Impresion de diagnostico de los LDR del patio APAGADA por ahora
  // (estorbaba otras mediciones en el Serial). Para volver a activarla,
  // cambia este 0 por un 1.
#define YARD_LDR_DEBUG_PRINT 0
#if YARD_LDR_DEBUG_PRINT
  static uint32_t ultimoPrintMs = 0;
  if (millis() - ultimoPrintMs > 5000) {
    ultimoPrintMs = millis();
    Serial.print(F("[PATIO LDR] "));
    for (uint8_t i = 0; i < YARD_POS_COUNT; i++) {
      for (uint8_t n = 0; n < YARD_MAX_NIVELES; n++) {
        Serial.print(F("P")); Serial.print(i);
        Serial.print(F("N")); Serial.print(n);
        Serial.print(F("="));
        if (i == 1 && n == 0) {
          // ELIMINADO: este sensor ya no se lee, ver yard_confirmarFisicamente()
          Serial.print(F("N/D(software) "));
        } else {
          int lectura = analogRead(YARD_OCC_PIN[i][n]);
          bool ocupado = lectura < UMBRAL_LDR_OSCURO[i][n];
          Serial.print(lectura);
          Serial.print(ocupado ? F("(OCUPADO) ") : F("(vacio) "));
        }
      }
    }
    Serial.println();
  }
#endif
}

bool yard_esAccesible(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return false;
  if (patio[posicion].estado == POS_BLOQUEADA) return false;
  return patio[posicion].nivelesOcupados < YARD_MAX_NIVELES;
}

// CORREGIDO (bug real de concurrencia/capacidad, reportado por el usuario):
// esta funcion comparaba contra "estado == POS_LIBRE", es decir, SOLO
// consideraba disponible una posicion completamente vacia. Eso ignoraba
// por completo el apilamiento de 2 niveles que exige el documento: en
// cuanto una posicion recibia su PRIMER contenedor, su estado pasaba a
// POS_OCUPADA y quedaba descartada para siempre por esta funcion, aunque
// todavia tuviera un segundo nivel libre (yard_esAccesible() -- ya
// definida arriba, pero nunca se usaba aqui -- si contempla esto
// correctamente).
//
// Efecto observado en la maqueta: CT-003 ya viene precargado en la
// posicion 0 desde el arranque (ver PreloadedData.h), asi que la
// posicion 0 NUNCA aparecia como POS_LIBRE. En cuanto el primer camion
// depositaba en la posicion 1 (la unica que si arrancaba POS_LIBRE),
// yard_buscarPosicionLibre() ya no encontraba NINGUNA posicion "libre"
// en todo el patio (ambas quedaban POS_OCUPADA con 1 nivel, aunque las
// dos tenian espacio de sobra para un segundo contenedor) y la garita
// rechazaba a cualquier siguiente camion con deposito por "Sin posicion
// accesible en patio" -- esto es lo que se percibia como "no soporta
// concurrencia" / "ya no me deja meter otro camion", porque coincidia
// en el tiempo con que el primer camion seguia siendo atendido por la
// grua.
//
// Ahora reutiliza yard_esAccesible(), que ya calculaba correctamente
// la disponibilidad real (no bloqueada + con nivel libre).
int8_t yard_buscarPosicionLibre() {
  for (uint8_t i = 0; i < YARD_POS_COUNT; i++) {
    if (yard_esAccesible(i)) return i;
  }
  return -1;
}

uint8_t yard_getNiveles(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return 0;
  return patio[posicion].nivelesOcupados;
}

// CORREGIDO: yard_buscarPosicionLibre() ahora puede devolver posiciones
// que estan POS_OCUPADA (con un nivel ocupado pero con espacio para otro
// contenedor en el nivel 2). Si yard_reservarPosicion() solo aceptaba
// POS_LIBRE, la reserva fallaba silenciosamente y la garita rechazaba
// al camion despues ("Sin posicion accesible en patio") a pesar de que
// SI habia espacio. Ahora acepta cualquier posicion que yard_esAccesible()
// devuelve true (no bloqueada + con nivel libre).
void yard_reservarPosicion(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return;
  if (yard_esAccesible(posicion)) patio[posicion].estado = POS_RESERVADA;
}

void yard_ocuparPosicion(int8_t posicion, uint8_t idContenedor) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return;
  uint8_t nivel = patio[posicion].nivelesOcupados;
  if (nivel >= YARD_MAX_NIVELES) return;
  patio[posicion].idContenedor[nivel] = idContenedor;
  patio[posicion].nivelesOcupados = nivel + 1;
  patio[posicion].estado = POS_OCUPADA;

  for (uint8_t c = 0; c < MAX_CONTENEDORES; c++) {
    if (CONTENEDORES[c].id == idContenedor) {
      CONTENEDORES[c].estado = CONT_EN_PATIO;
      CONTENEDORES[c].posicionPatio = posicion;
      CONTENEDORES[c].nivelPatio = nivel;
    }
  }
}

void yard_liberarPosicion(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return;
  if (patio[posicion].nivelesOcupados > 0) {
    patio[posicion].nivelesOcupados--;
    patio[posicion].idContenedor[patio[posicion].nivelesOcupados] = 255;
  }
  patio[posicion].estado = (patio[posicion].nivelesOcupados == 0) ? POS_LIBRE : POS_OCUPADA;
}

void yard_marcarBloqueada(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return;
  patio[posicion].estado = POS_BLOQUEADA;
}

// Lee AMBOS niveles de la posicion via analogRead() y cuenta cuantos
// estan tapados (contenedor encima), de abajo hacia arriba. Si el nivel
// 0 esta libre, se asume que no puede haber nada en el nivel 1 y se
// corta el conteo ahi. Compara ese conteo fisico contra lo que dice el
// inventario; si no coincide, bloquea la posicion.
bool yard_confirmarFisicamente(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return true; // no aplica (p.ej. zona de transferencia)

  uint8_t nivelesDetectados = 0;
  for (uint8_t n = 0; n < YARD_MAX_NIVELES; n++) {
    bool detectado;
    if (posicion == 1 && n == 0) {
      // ELIMINADO: el LDR de esta posicion/nivel (P1N0) resulto poco
      // confiable en la maqueta (con contenedor encima leia igual o
      // mas alto que en vacio -- ver pruebas). En vez de arriesgar
      // falsos bloqueos de la posicion, para este nivel puntual se
      // confia en el registro por software (que contenedor se puso
      // ahi via yard_ocuparPosicion/yard_liberarPosicion) en lugar
      // del sensor fisico.
      detectado = (patio[posicion].idContenedor[n] != 255);
    } else {
      int lectura = analogRead(YARD_OCC_PIN[posicion][n]);
      // por debajo del umbral = poca luz = tapado por un contenedor
      detectado = (lectura < UMBRAL_LDR_OSCURO[posicion][n]);
    }
    if (detectado) nivelesDetectados++;
    else break;
  }

  bool inconsistente = (nivelesDetectados != patio[posicion].nivelesOcupados);
  if (inconsistente) {
    yard_marcarBloqueada(posicion);
    return false;
  }
  return true;
}

int8_t yard_localizarContenedor(uint8_t idContenedor) {
  for (uint8_t i = 0; i < YARD_POS_COUNT; i++) {
    for (uint8_t n = 0; n < patio[i].nivelesOcupados; n++) {
      if (patio[i].idContenedor[n] == idContenedor) return i;
    }
  }
  return -1;
}

EstadoPosicion yard_getEstado(int8_t posicion) {
  if (posicion < 0 || posicion >= YARD_POS_COUNT) return POS_BLOQUEADA;
  return patio[posicion].estado;
}
void yard_imprimirTelemetria() {
  for (uint8_t p=0; p<YARD_POS_COUNT; p++) {
    for (uint8_t n=0; n<YARD_MAX_NIVELES; n++) {
      Serial.print(F("@PORTUS PatioCelda;posicion=")); Serial.print(p);
      Serial.print(F(";nivel=")); Serial.print(n);
      Serial.print(F(";contenedor="));
      uint8_t id = patio[p].idContenedor[n];
      if (id < MAX_CONTENEDORES) Serial.print(CONTENEDORES[id].codigo);
      Serial.print(F(";ocupada=")); Serial.println(n < patio[p].nivelesOcupados ? 1 : 0);
    }
  }
}
