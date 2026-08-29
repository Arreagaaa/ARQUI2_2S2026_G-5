/*
  ============================================================
  Crane.cpp - PORTUS Fase 1

  Motores reales: 28BYJ-48 (5V) con driver ULN2003 (IN1-IN4),
  NO A4988/STEP-DIR. El control es por secuencia de bobinas
  (half-step, 8 pasos), no por pulsos STEP simples.

  Este modulo NO tiene timer de hardware propio. En el Arduino
  Mega, Servo.h ocupa internamente Timer1/3/4/5 completos,
  dejando SOLO Timer2 (8 bits) libre, que ya es usado por
  Weighing.cpp como "tick base" compartido (ver Weighing.cpp).
  Crane.cpp expone crane_timerTick(), que Weighing.cpp llama en
  cada tick de Timer2; aqui se cuenta cuantos ticks han pasado y,
  al llegar a la cantidad equivalente a STEP_PULSE_HALF_PERIOD_US,
  se avanza un paso de la secuencia en el eje activo (traslacion
  o izaje, nunca ambos a la vez, ya que el ciclo de la grua es
  secuencial). stepsRemaining se decrementa dentro de este tick;
  el loop() solo consulta banderas.

  Referenciado: YA NO hay fin de carrera fisico de home (se quito
  PIN_FC_IZQ/PIN_FC_DER). La posicion de transferencia (posicion 0)
  esta en el extremo del riel, asi que la PRIMERA marca optica que
  se detecta moviendose hacia ese extremo ES la marca de home. El
  unico fin de carrera fisico que queda es PIN_FC_CONTACTO, en el
  cabezal, para detectar cuando toca el contenedor/la pila.

  Arranque (CAMBIADO, pedido del usuario): el horizontal ya NO se mueve
  solo al encender. Se queda quieto en G_INACTIVA hasta que el pin 25
  (PIN_IR_TRANSFERENCIA) se activa; ahi arranca el referenciado inicial
  (primer movimiento horizontal real, ver G_INACTIVA / G_REFERENCIANDO_MOVER).

  Reparto de sensores (CAMBIADO, pedido del usuario):
  - A0 (PIN_MARCA_OPTICA) es EXCLUSIVO del eje horizontal: detecta las
    marcas del riel y detiene la traslacion en vivo (dentro del tick,
    ver crane_timerTick) apenas se ve la marca esperada, en vez de
    esperar a que se agoten los pasos precalculados. Tambien se usa
    como compuerta: despues de subir con el contenedor, el horizontal
    NO retoma el movimiento hasta que A0 deja de sensar (ver
    G_ESPERAR_LIBERAR_MARCA).
  - PIN_FC_CONTACTO es EXCLUSIVO del eje de izaje: detiene el descenso
    al tocar el contenedor/la pila y, en el mismo instante, energiza o
    suelta el electroiman (agarre en G_DESCENDER_CONTACTO, suelta en
    G_DESCENDER_DEPOSITO). La subida posterior no usa ningun sensor:
    sube exactamente los mismos pasos que bajo (pasosUltimoDescenso).
  ============================================================
*/
#include "Crane.h"
#include "Config.h"
#include "Yard.h"

// ---------------- secuencia de pasos para 28BYJ-48 (half-step, 8 pasos) ----------------
// Cada fila activa las bobinas IN1-IN4 en ese orden. Half-step da
// movimiento mas suave y algo mas de torque que full-step (4 pasos).
static const uint8_t SECUENCIA_PASOS[8][4] = {
  {1,0,0,0},
  {1,1,0,0},
  {0,1,0,0},
  {0,1,1,0},
  {0,0,1,0},
  {0,0,1,1},
  {0,0,0,1},
  {1,0,0,1}
};

static volatile long stepsRemaining = 0;
static volatile bool ejeActivoEsTraslacion = true; // false = izaje
static volatile bool movimientoEnCurso = false;
static volatile uint16_t marcasDetectadasEnMovimiento = 0;
static volatile uint16_t marcasObjetivoMovimiento = 0;
static volatile bool marcaAnterior = false;
static volatile int8_t indiceSecuencia = 0;
static volatile bool sentidoActualPositivo = true;

// DEBOUNCE POR PASOS: despues de detectar una marca de A0, ignorar las
// siguientes hasta que el motor haya recorrido esta cantidad minima de
// pasos REALES (no transiciones del sensor). Evita que rebotes
// electricos/mecanicos del sensor cuenten como marcas falsas.
#define PASOS_DEBOUNCE_MARCA 100
static volatile uint16_t pasosMotorDesdeUltimaDeteccion = 0;

// ---------------- contador de ticks para el pulso del motor ----------------
static volatile uint16_t craneTickCounter = 0;
static uint16_t craneTicksPorPulso = 0;

static void escribirBobinas(uint8_t in1, uint8_t in2, uint8_t in3, uint8_t in4, const uint8_t fila[4]) {
  digitalWrite(in1, fila[0]);
  digitalWrite(in2, fila[1]);
  digitalWrite(in3, fila[2]);
  digitalWrite(in4, fila[3]);
}

// Ya NO es una ISR propia: la llama Weighing.cpp desde su ISR de Timer2
// (unico timer de 8 bits libre en el Mega, ya que Servo.h ocupa el resto).
void crane_timerTick() {
  if (!movimientoEnCurso || stepsRemaining <= 0) return;

  craneTickCounter++;
  if (craneTickCounter < craneTicksPorPulso) return;
  craneTickCounter = 0;

  indiceSecuencia += sentidoActualPositivo ? 1 : -1;
  if (indiceSecuencia > 7) indiceSecuencia = 0;
  if (indiceSecuencia < 0) indiceSecuencia = 7;

  if (ejeActivoEsTraslacion) {
    escribirBobinas(PIN_TRANS_IN1, PIN_TRANS_IN2, PIN_TRANS_IN3, PIN_TRANS_IN4, SECUENCIA_PASOS[indiceSecuencia]);
    // Contar pasos reales del motor para el debounce (se incrementa SIEMPRE
    // que el motor da un paso, no solo cuando el sensor cambia de estado).
    if (pasosMotorDesdeUltimaDeteccion < PASOS_DEBOUNCE_MARCA) {
      pasosMotorDesdeUltimaDeteccion++;
    }
    bool marcaAhora = (digitalRead(PIN_MARCA_OPTICA) == LOW);
    if (marcaAhora && !marcaAnterior) {
      // DEBOUNCE: solo contar la marca si el motor ya recorrio la distancia
      // minima desde la ultima deteccion. Si no, es un rebote y se ignora.
      if (pasosMotorDesdeUltimaDeteccion >= PASOS_DEBOUNCE_MARCA) {
        marcasDetectadasEnMovimiento++;
        pasosMotorDesdeUltimaDeteccion = 0;
        if (marcasObjetivoMovimiento > 0 && marcasDetectadasEnMovimiento >= marcasObjetivoMovimiento) {
          Serial.print(F("[GRUA] A0 marco parada: marcas="));
          Serial.print(marcasDetectadasEnMovimiento);
          Serial.print(F("/"));
          Serial.println(marcasObjetivoMovimiento);
          movimientoEnCurso = false;
        }
      }
    }
    marcaAnterior = marcaAhora;
  } else {
    escribirBobinas(PIN_IZAJE_IN1, PIN_IZAJE_IN2, PIN_IZAJE_IN3, PIN_IZAJE_IN4, SECUENCIA_PASOS[indiceSecuencia]);
  }

  stepsRemaining--;
  if (stepsRemaining <= 0) movimientoEnCurso = false;
}

// mueve `pasos` pasos en el eje indicado, sin bloquear (el llamador debe
// esperar a que movimientoEnCurso vuelva a false consultando movimientoTerminado())
// marcasParada: cantidad de marcas de A0 que deben verse antes de que el
// tick corte el horizontal solo (0 = no usar A0 para parar, ej. izaje).
static void iniciarMovimiento(bool traslacion, bool sentidoPositivo, long pasos, uint16_t marcasParada = 0) {
  noInterrupts();
  ejeActivoEsTraslacion = traslacion;
  sentidoActualPositivo = sentidoPositivo;
  stepsRemaining = pasos;
  marcasDetectadasEnMovimiento = 0;
  marcasObjetivoMovimiento = marcasParada;
  craneTickCounter = 0;
  // FIX: si es movimiento horizontal, inicializar marcaAnterior con el
  // estado actual del sensor A0 para no contar una transicion falsa en el
  // primer tick (el cabezal puede estar ya sobre la marca al arrancar).
  if (traslacion) {
    marcaAnterior = (digitalRead(PIN_MARCA_OPTICA) == LOW);
    // Inicializar al maximo para que la primera deteccion sea inmediata
    // (no hay rebote previo que filtrar en el arranque).
    pasosMotorDesdeUltimaDeteccion = PASOS_DEBOUNCE_MARCA;
  }
  movimientoEnCurso = true;
  interrupts();
}
static bool movimientoTerminado() { return !movimientoEnCurso; }
static void detenerMovimientoInmediato() {
  noInterrupts();
  movimientoEnCurso = false;
  stepsRemaining = 0;
  interrupts();
}

// ---------------- posicion actual conocida de la grua ----------------
static int8_t posicionActual = -1;   // -1 = desconocida (aun no referenciada)
static bool   referenciada = false;
static bool   perdidaDeReferencia = false;

// ---------------- cola de trabajos ----------------
#define MAX_TRABAJOS 8
static TrabajoGrua cola[MAX_TRABAJOS];
static uint8_t siguienteIdTrabajo = 0;

void crane_init() {
  pinMode(PIN_TRANS_IN1, OUTPUT);
  pinMode(PIN_TRANS_IN2, OUTPUT);
  pinMode(PIN_TRANS_IN3, OUTPUT);
  pinMode(PIN_TRANS_IN4, OUTPUT);
  pinMode(PIN_IZAJE_IN1, OUTPUT);
  pinMode(PIN_IZAJE_IN2, OUTPUT);
  pinMode(PIN_IZAJE_IN3, OUTPUT);
  pinMode(PIN_IZAJE_IN4, OUTPUT);

  pinMode(PIN_FC_CONTACTO, INPUT_PULLUP);
  pinMode(PIN_ELECTROIMAN, OUTPUT);
  digitalWrite(PIN_ELECTROIMAN, HIGH); // rele activo-bajo: HIGH = electroiman OFF (apagado al arrancar)

  for (uint8_t i = 0; i < MAX_TRABAJOS; i++) cola[i].activo = false;

  craneTicksPorPulso = STEP_PULSE_HALF_PERIOD_US / BASE_TICK_US;
  if (craneTicksPorPulso == 0) craneTicksPorPulso = 1;
  // NOTA: Timer2 lo inicializa y controla exclusivamente Weighing.cpp
  // (weighing_init()). Asegurate de llamar weighing_init() en el setup(),
  // el orden respecto a crane_init() no importa, pero ambos deben llamarse.

  // ELIMINADO: el diagnostico de analogRead(PIN_MARCA_OPTICA) ya no
  // aplica -- se confirmo que A0 es un IR digital normal, se lee con
  // digitalRead (LOW=activado), no con un umbral analogico.
  pinMode(PIN_MARCA_OPTICA, INPUT);
}

int crane_enqueue(TipoTrabajoGrua tipo, uint8_t idTurno, int8_t origen, int8_t destino, uint8_t idContenedor) {
  for (uint8_t i = 0; i < MAX_TRABAJOS; i++) {
    if (!cola[i].activo) {
      cola[i].id = siguienteIdTrabajo++;
      cola[i].activo = true;
      cola[i].tipo = tipo;
      cola[i].idTurno = idTurno;
      cola[i].posicionOrigen = origen;
      cola[i].posicionDestino = destino;
      cola[i].idContenedor = idContenedor;
      cola[i].estado = TRABAJO_PENDIENTE;
      cola[i].timestampCreacion = millis();
      return cola[i].id;
    }
  }
  return -1; // cola llena
}

// Politica de atencion: FIFO por orden de creacion (timestampCreacion),
// documentada y determinista, como exige el enunciado.
static int8_t indiceSiguienteTrabajo() {
  int8_t mejor = -1;
  for (uint8_t i = 0; i < MAX_TRABAJOS; i++) {
    if (cola[i].activo && cola[i].estado == TRABAJO_PENDIENTE) {
      if (mejor == -1 || cola[i].timestampCreacion < cola[mejor].timestampCreacion) mejor = i;
    }
  }
  return mejor;
}

bool crane_isJobDone(uint8_t idTrabajo) {
  for (uint8_t i = 0; i < MAX_TRABAJOS; i++)
    if (cola[i].activo && cola[i].id == idTrabajo) return cola[i].estado == TRABAJO_COMPLETADO;
  return false;
}
bool crane_isJobError(uint8_t idTrabajo) {
  for (uint8_t i = 0; i < MAX_TRABAJOS; i++)
    if (cola[i].activo && cola[i].id == idTrabajo) return cola[i].estado == TRABAJO_ERROR;
  return false;
}

// ---------------- maquina de estados del ciclo de la grua ----------------
enum EstadoGrua {
  G_INACTIVA,
  G_REFERENCIANDO_MOVER,
  G_REFERENCIANDO_CONFIRMAR,
  G_MOVER_A_ORIGEN,
  G_DESCENDER_CONTACTO,
  G_VERIFICAR_ALTURA,
  G_CONFIRMAR_AGARRE,
  G_ELEVAR_SEGURO,
  G_ESPERAR_LIBERAR_MARCA,
  G_TRASLADAR_DESTINO,
  G_DESCENDER_DEPOSITO,
  G_CONFIRMAR_COLOCACION,
  G_RETRAER,
  G_ACTUALIZAR_INVENTARIO,
  G_TRABAJO_COMPLETADO,
  G_ERROR
};

static EstadoGrua estado = G_INACTIVA;
static TrabajoGrua *trabajoActual = nullptr;
static uint32_t estadoDesdeMs = 0;
static uint8_t alturaDetectadaPasos = 0;
// AGREGADO: pasos reales que bajo el cabezal en el ultimo descenso (lo
// detecta el sensor IR de A0, ya no un valor fijo). Se usa para que la
// subida posterior recorra exactamente lo mismo, sin sensor, solo
// contando pasos -- pedido explicito del usuario para simplificar el
// eje vertical.
static long pasosUltimoDescenso = 0;

static void irA(EstadoGrua e) {
  estado = e;
  estadoDesdeMs = millis();
  // AGREGADO: diagnostico de la maquina de estados de la grua. Si esto
  // se imprime (sobre todo G_REFERENCIANDO_MOVER al arrancar) significa
  // que el firmware SI esta intentando mover motores -- si aun asi no
  // hay movimiento fisico, el problema es electrico (GND no compartido
  // entre la fuente externa y el Mega, driver ULN2003 sin su propio VCC,
  // o cableado de bobinas), no de codigo.
  Serial.print(F("[GRUA] estado -> "));
  Serial.println((int)e);
}

bool crane_isIdle() { return estado == G_INACTIVA; }
bool crane_isReferenced() { return referenciada; }
void crane_forceReReference() { referenciada = false; posicionActual = -1; }

void crane_emergencyHalt() {
  detenerMovimientoInmediato();
  // rele activo-bajo: HIGH = electroiman OFF. En E-stop se suelta la
  // carga (decision de diseno: priorizar no tener algo colgado sin
  // control). Ajustar segun analisis de riesgo del equipo.
  digitalWrite(PIN_ELECTROIMAN, HIGH);
  estado = G_ERROR;
}

static long pasosEntre(int8_t origenPos, int8_t destinoPos) {
  return (long)abs(destinoPos - origenPos) * PASOS_POR_POSICION_DEFECTO;
}

void crane_update() {
  // CAMBIADO (pedido del usuario): este print periodico se apaga por
  // defecto -- salia cada 500ms y tapaba otras cosas en el Serial,
  // molesta sobre todo para la entrega. Los prints de CAMBIO de estado
  // (dentro de irA()) siguen activos, esos no son periodicos. Para
  // volver a activar este diagnostico, cambia el 0 por un 1.
#define GRUA_DEBUG_PRINT_PERIODICO 0
#if GRUA_DEBUG_PRINT_PERIODICO
  static uint32_t ultimoPrintMs = 0;
  static EstadoGrua estadoAnteriorDebug = (EstadoGrua)255;
  if (millis() - ultimoPrintMs > 500 || estado != estadoAnteriorDebug) {
    Serial.print(F("[GRUA] estado="));
    Serial.print((int)estado);
    Serial.print(F(" movimientoEnCurso="));
    Serial.print(movimientoEnCurso ? F("SI") : F("NO"));
    Serial.print(F(" stepsRemaining="));
    Serial.println(stepsRemaining);
    ultimoPrintMs = millis();
    estadoAnteriorDebug = estado;
  }
#endif

  switch (estado) {

    case G_INACTIVA: {
      // CAMBIADO (pedido del usuario): el referenciado inicial YA NO
      // arranca solo al encender el Mega. El horizontal se queda quieto
      // hasta que el pin 25 (PIN_IR_TRANSFERENCIA) se activa; recien ahi
      // arranca el referenciado (primer movimiento horizontal real).
      if (!referenciada) {
        if (digitalRead(PIN_IR_TRANSFERENCIA) == LOW) { // sensor con logica invertida: LOW = presencia
          irA(G_REFERENCIANDO_MOVER);
        }
        return;
      }
      if (trabajoActual == nullptr) {
        int8_t idx = indiceSiguienteTrabajo();
        if (idx >= 0) {
          trabajoActual = &cola[idx];
          trabajoActual->estado = TRABAJO_EJECUTANDO;
          irA(G_MOVER_A_ORIGEN);
        }
      }
      break;
    }

    // ---------- referenciado inicial obligatorio ----------
    case G_REFERENCIANDO_MOVER: {
      // Ya no hay fin de carrera fisico de home: la posicion de transferencia
      // (posicion 0) esta en el extremo del riel, asi que la PRIMERA marca
      // optica detectada moviendose hacia ese extremo ES la marca de home.

      // CAMBIADO: ya no hace falta calibrar umbral analogico (A0 es IR
      // digital normal). Se deja un print en vivo del estado digital,
      // util para confirmar visualmente que detecta al pasar por la
      // marca real.
      // CAMBIADO: este print en vivo tambien se apaga por defecto (cada
      // 200ms era demasiado seguido). Cambia el 0 por un 1 para volver a
      // activarlo si necesitan confirmar visualmente que A0 detecta la
      // marca real.
#define GRUA_DEBUG_PRINT_MARCA 0
#if GRUA_DEBUG_PRINT_MARCA
      static uint32_t ultimoPrintMarcaMs = 0;
      if (millis() - ultimoPrintMarcaMs > 200) {
        ultimoPrintMarcaMs = millis();
        Serial.print(F("[GRUA] IR marca (A0) en vivo: "));
        Serial.println(digitalRead(PIN_MARCA_OPTICA) == LOW ? F("LOW (activado)") : F("HIGH (libre)"));
      }
#endif

      if (marcasDetectadasEnMovimiento >= 1) {
        irA(G_REFERENCIANDO_CONFIRMAR);
        return;
      }
      if (!movimientoEnCurso) {
        // limite de pasos de seguridad: si no detecta ninguna marca en todo
        // el recorrido del riel, algo esta mal (sensor sucio/desalineado).
        // CAMBIADO: se pasa marcasParada=1 para que el propio tick corte
        // el motor apenas A0 vea la primera marca, en tiempo real.
        iniciarMovimiento(true, false, PASOS_POR_POSICION_DEFECTO * TOTAL_POSICIONES_RIEL, 1);
      } else if (movimientoTerminado()) {
        // se agoto el recorrido de seguridad sin detectar ninguna marca
        irA(G_ERROR);
      }
      break;
    }
    case G_REFERENCIANDO_CONFIRMAR: {
      detenerMovimientoInmediato();
      posicionActual = 0;
      referenciada = true;
      perdidaDeReferencia = false;
      irA(G_INACTIVA);
      break;
    }

    // ---------- traslado hacia el origen del trabajo ----------
    case G_MOVER_A_ORIGEN: {
      if (posicionActual == trabajoActual->posicionOrigen) { irA(G_DESCENDER_CONTACTO); return; }
      if (!movimientoEnCurso) {
        bool haciaAdelante = trabajoActual->posicionOrigen > posicionActual;
        long pasos = pasosEntre(posicionActual, trabajoActual->posicionOrigen);
        // CAMBIADO (pedido del usuario): A0 detiene el horizontal en vivo
        // apenas se detecta la marca esperada, en vez de esperar a que se
        // agoten los pasos precalculados (que quedan solo de respaldo).
        uint16_t marcasEsperadas = (uint16_t)abs(trabajoActual->posicionOrigen - posicionActual);
        iniciarMovimiento(true, haciaAdelante, pasos, marcasEsperadas);
      } else if (movimientoTerminado()) {
        // valida que se haya detectado exactamente la cantidad de marcas esperada
        int esperado = abs(trabajoActual->posicionOrigen - posicionActual);
        if (marcasDetectadasEnMovimiento < esperado) {
          perdidaDeReferencia = true;
          referenciada = false;
          irA(G_ERROR);
          return;
        }
        posicionActual = trabajoActual->posicionOrigen;
        irA(G_DESCENDER_CONTACTO);
      }
      break;
    }

    // ---------- descenso hasta contacto ----------
    case G_DESCENDER_CONTACTO: {
      static bool yaIniciado = false;
      static long pasosSolicitados = 0;

      // DEBUG: imprimir estado del FC cada 500ms para diagnosticar
      static uint32_t ultimoPrintFcMs = 0;
      if (millis() - ultimoPrintFcMs > 500) {
        ultimoPrintFcMs = millis();
        Serial.print(F("[GRUA] FC="));
        Serial.print(digitalRead(PIN_FC_CONTACTO) == LOW ? F("LOW(contacto)") : F("HIGH(libre)"));
        Serial.print(F(" stepsRem="));
        Serial.println(stepsRemaining);
      }

      if (digitalRead(PIN_FC_CONTACTO) == LOW) {
        detenerMovimientoInmediato();
        // Si no se inicio el descenso aun, usar IZAJE_PASOS_SEGURO como
        // estimacion de la distancia recorrida (caso: FC ya activo al entrar).
        if (!yaIniciado) {
          pasosUltimoDescenso = IZAJE_PASOS_SEGURO;
        } else {
          pasosUltimoDescenso = pasosSolicitados - stepsRemaining;
        }
        alturaDetectadaPasos = (uint8_t)(pasosUltimoDescenso / 100);
        digitalWrite(PIN_ELECTROIMAN, LOW); // rele activo-bajo: LOW = electroiman ON (agarre)
        Serial.println(F("[GRUA] FC detectado -> electroiman ON (agarre)"));
        yaIniciado = false;
        irA(G_VERIFICAR_ALTURA);
        return;
      }
      if (!yaIniciado) {
        pasosSolicitados = IZAJE_PASOS_SEGURO * 3;
        Serial.print(F("[GRUA] DESCENDIENDO (agarre): pasos="));
        Serial.println(pasosSolicitados);
        iniciarMovimiento(false, false, pasosSolicitados);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        Serial.println(F("[GRUA] ERROR: descenso sin FC - revisar sensor CONTACTO pin 38"));
        irA(G_ERROR);
      }
      break;
    }

    // ---------- verificar que la altura fisica coincide con el inventario ----------
    case G_VERIFICAR_ALTURA: {
      uint8_t nivelesEsperados = yard_getNiveles(trabajoActual->posicionOrigen - 1); // -1: patio 0-index
      // tolerancia simple: se acepta diferencia de 1 "escalon" por variabilidad mecanica
      if (trabajoActual->tipo != TRABAJO_DEPOSITO &&
          abs((int)alturaDetectadaPasos - (int)nivelesEsperados) > 1) {
        yard_marcarBloqueada(trabajoActual->posicionOrigen - 1);
        irA(G_ERROR);
        return;
      }
      // CAMBIADO: ya no pasa por G_ENERGIZAR_IMAN (eliminado) -- el
      // electroiman se energiza en el mismo instante del contacto, dentro
      // de G_DESCENDER_CONTACTO.
      irA(G_CONFIRMAR_AGARRE);
      break;
    }

    // ---------- confirmar que la carga quedo adherida ----------
    case G_CONFIRMAR_AGARRE: {
      // Verificacion simplificada por tiempo; el equipo puede reforzar esto
      // leyendo corriente del electroiman o un sensor de proximidad extra.
      if (millis() - estadoDesdeMs > 300) {
        irA(G_ELEVAR_SEGURO);
      }
      break;
    }

    case G_ELEVAR_SEGURO: {
      static bool yaIniciado = false;
      if (!yaIniciado) {
        Serial.print(F("[GRUA] ELEVANDO: pasosUltimoDescenso="));
        Serial.println(pasosUltimoDescenso);
        iniciarMovimiento(false, true, pasosUltimoDescenso);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        irA(G_ESPERAR_LIBERAR_MARCA);
      }
      break;
    }

    // ---------- NUEVO (pedido del usuario): espera a que A0 deje de
    // detectar la marca antes de que el horizontal retome el movimiento.
    // Si se queda pegado aqui, revisar fisicamente el sensor A0 (sucio,
    // desalineado, o la marca fisica en mal estado). ----------
    case G_ESPERAR_LIBERAR_MARCA: {
      // Timeout: si A0 no cambia en 10 segundos, algo esta mal (sensor
      // sucio, desalineado, o marca fisica permanentemente visible).
      if (millis() - estadoDesdeMs > 10000) {
        Serial.println(F("[GRUA] TIMEOUT: A0 no se libero en 10s"));
        irA(G_ERROR);
        return;
      }
      if (digitalRead(PIN_MARCA_OPTICA) == HIGH) { // HIGH = ya no detecta (logica invertida)
        irA(G_TRASLADAR_DESTINO);
      }
      break;
    }

    case G_TRASLADAR_DESTINO: {
      if (posicionActual == trabajoActual->posicionDestino) { irA(G_DESCENDER_DEPOSITO); return; }
      if (!movimientoEnCurso) {
        bool haciaAdelante = trabajoActual->posicionDestino > posicionActual;
        long pasos = pasosEntre(posicionActual, trabajoActual->posicionDestino);
        // FIX: mismo criterio que G_MOVER_A_ORIGEN, A0 detiene el
        // horizontal en vivo al llegar a la marca esperada.
        uint16_t marcasEsperadas = (uint16_t)abs(trabajoActual->posicionDestino - posicionActual);
        iniciarMovimiento(true, haciaAdelante, pasos, marcasEsperadas);
      } else if (movimientoTerminado()) {
        posicionActual = trabajoActual->posicionDestino;
        irA(G_DESCENDER_DEPOSITO);
      }
      break;
    }

    case G_DESCENDER_DEPOSITO: {
      static bool yaIniciado = false;
      static long pasosSolicitados = 0;

      // DEBUG: imprimir estado del FC cada 500ms
      static uint32_t ultimoPrintFcMs = 0;
      if (millis() - ultimoPrintFcMs > 500) {
        ultimoPrintFcMs = millis();
        Serial.print(F("[GRUA] FC deposito="));
        Serial.print(digitalRead(PIN_FC_CONTACTO) == LOW ? F("LOW(contacto)") : F("HIGH(libre)"));
        Serial.print(F(" stepsRem="));
        Serial.println(stepsRemaining);
      }

      if (digitalRead(PIN_FC_CONTACTO) == LOW) {
        detenerMovimientoInmediato();
        if (!yaIniciado) {
          pasosUltimoDescenso = IZAJE_PASOS_SEGURO;
        } else {
          pasosUltimoDescenso = pasosSolicitados - stepsRemaining;
        }
        digitalWrite(PIN_ELECTROIMAN, HIGH); // rele activo-bajo: HIGH = electroiman OFF (suelta)
        Serial.println(F("[GRUA] FC detectado -> electroiman OFF (suelta)"));
        yaIniciado = false;
        irA(G_CONFIRMAR_COLOCACION);
        return;
      }
      if (!yaIniciado) {
        pasosSolicitados = IZAJE_PASOS_SEGURO * 3;
        iniciarMovimiento(false, false, pasosSolicitados);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        Serial.println(F("[GRUA] ERROR: descenso deposito sin FC - revisar sensor CONTACTO pin 38"));
        irA(G_ERROR);
      }
      break;
    }

    case G_CONFIRMAR_COLOCACION: {
      if (millis() - estadoDesdeMs > 300) {
        // Confirmacion fisica minima: aqui deberia leerse el sensor de ocupacion
        // de la posicion de destino (si es del patio). Se hace en Yard antes de
        // marcar el trabajo como completado, para no actualizar el inventario
        // "a ciegas" solo porque se emitio el comando.
        irA(G_RETRAER);
      }
      break;
    }

    case G_RETRAER: {
      static bool yaIniciado = false;
      if (!yaIniciado) {
        Serial.print(F("[GRUA] RETRAER: pasosUltimoDescenso="));
        Serial.println(pasosUltimoDescenso);
        iniciarMovimiento(false, true, pasosUltimoDescenso);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        irA(G_ACTUALIZAR_INVENTARIO);
      }
      break;
    }

    case G_ACTUALIZAR_INVENTARIO: {
      bool confirmado = true;
      if (trabajoActual->posicionDestino > POS_TRANSFERENCIA) {
        confirmado = yard_confirmarFisicamente(trabajoActual->posicionDestino - 1);
      }
      if (!confirmado) { irA(G_ERROR); return; }

      if (trabajoActual->tipo == TRABAJO_DEPOSITO || trabajoActual->tipo == TRABAJO_REMOCION) {
        yard_ocuparPosicion(trabajoActual->posicionDestino - 1, trabajoActual->idContenedor);
      }
      if (trabajoActual->posicionOrigen > POS_TRANSFERENCIA) {
        yard_liberarPosicion(trabajoActual->posicionOrigen - 1);
      }
      trabajoActual->estado = TRABAJO_COMPLETADO;
      irA(G_TRABAJO_COMPLETADO);
      break;
    }

    case G_TRABAJO_COMPLETADO: {
      trabajoActual = nullptr;
      irA(G_INACTIVA);
      break;
    }

    case G_ERROR: {
      if (trabajoActual != nullptr) trabajoActual->estado = TRABAJO_ERROR;
      trabajoActual = nullptr;
      // CORREGIDO: antes este estado no tenia ninguna salida. El rearme
      // (Safety -> crane_forceReReference()) apaga "referenciada", pero
      // como el switch de arriba se queda atascado en este mismo case,
      // esa bandera nunca se llegaba a revisar -- el REARME no tenia
      // ningun efecto visible. Ahora, si ya se detecto un rearme
      // (referenciada==false), se vuelve a G_INACTIVA, que dispara un
      // nuevo referenciado automaticamente.
      if (!referenciada) {
        irA(G_INACTIVA);
      }
      break;
    }
  }
}