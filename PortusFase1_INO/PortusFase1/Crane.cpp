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
static volatile bool marcaAnterior = false;
static volatile int8_t indiceSecuencia = 0;
static volatile bool sentidoActualPositivo = true;

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
    // CORREGIDO: A0 es un IR digital normal (confirmado por el usuario),
    // no un sensor analogico de umbral. Se lee con digitalRead, misma
    // logica invertida que el resto de los IR del proyecto (LOW=activado).
    bool marcaAhora = (digitalRead(PIN_MARCA_OPTICA) == LOW);
    if (marcaAhora && !marcaAnterior) marcasDetectadasEnMovimiento++;
    marcaAnterior = marcaAhora;
  } else {
    escribirBobinas(PIN_IZAJE_IN1, PIN_IZAJE_IN2, PIN_IZAJE_IN3, PIN_IZAJE_IN4, SECUENCIA_PASOS[indiceSecuencia]);
  }

  stepsRemaining--;
  if (stepsRemaining <= 0) movimientoEnCurso = false;
}

// mueve `pasos` pasos en el eje indicado, sin bloquear (el llamador debe
// esperar a que movimientoEnCurso vuelva a false consultando movimientoTerminado())
static void iniciarMovimiento(bool traslacion, bool sentidoPositivo, long pasos) {
  noInterrupts();
  ejeActivoEsTraslacion = traslacion;
  sentidoActualPositivo = sentidoPositivo;
  stepsRemaining = pasos;
  marcasDetectadasEnMovimiento = 0;
  craneTickCounter = 0;
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
  digitalWrite(PIN_ELECTROIMAN, LOW);

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
  G_ENERGIZAR_IMAN,
  G_CONFIRMAR_AGARRE,
  G_ELEVAR_SEGURO,
  G_TRASLADAR_DESTINO,
  G_DESCENDER_DEPOSITO,
  G_LIBERAR_IMAN,
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
  digitalWrite(PIN_ELECTROIMAN, LOW); // por seguridad NO se libera automaticamente en produccion
  // (dejar el electroiman energizado durante un E-stop es una decision de diseno;
  //  aqui se prioriza no soltar la carga en el aire. Ajustar segun analisis de riesgo del equipo.)
  digitalWrite(PIN_ELECTROIMAN, HIGH);
  estado = G_ERROR;
}

static long pasosEntre(int8_t origenPos, int8_t destinoPos) {
  return (long)abs(destinoPos - origenPos) * PASOS_POR_POSICION_DEFECTO;
}

void crane_update() {
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

  switch (estado) {

    case G_INACTIVA: {
      if (!referenciada) { irA(G_REFERENCIANDO_MOVER); return; }
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
      static uint32_t ultimoPrintMarcaMs = 0;
      if (millis() - ultimoPrintMarcaMs > 200) {
        ultimoPrintMarcaMs = millis();
        Serial.print(F("[GRUA] IR marca (A0) en vivo: "));
        Serial.println(digitalRead(PIN_MARCA_OPTICA) == LOW ? F("LOW (activado)") : F("HIGH (libre)"));
      }

      if (marcasDetectadasEnMovimiento >= 1) {
        irA(G_REFERENCIANDO_CONFIRMAR);
        return;
      }
      if (!movimientoEnCurso) {
        // limite de pasos de seguridad: si no detecta ninguna marca en todo
        // el recorrido del riel, algo esta mal (sensor sucio/desalineado)
        iniciarMovimiento(true, false, PASOS_POR_POSICION_DEFECTO * TOTAL_POSICIONES_RIEL);
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
        iniciarMovimiento(true, haciaAdelante, pasos);
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
      // CAMBIADO (pedido del usuario): antes solo se usaba el FC para
      // saber cuando parar. Ahora el sensor IR de A0 (PIN_MARCA_OPTICA,
      // reusado como IR digital normal, no analogico) es el que PARA
      // el motor vertical; el FC solo se revisa DESPUES para confirmar
      // contacto real y disparar el electroiman. Se guarda cuantos
      // pasos bajo de verdad para que la subida use el mismo numero.
      static bool yaIniciado = false;
      static long pasosSolicitados = 0;

      if (digitalRead(PIN_MARCA_OPTICA) == LOW) { // IR activado (misma logica invertida que el resto de IR del proyecto)
        detenerMovimientoInmediato();
        pasosUltimoDescenso = pasosSolicitados - stepsRemaining;
        alturaDetectadaPasos = (uint8_t)(pasosUltimoDescenso / 100); // ajustar escala real
        yaIniciado = false;
        irA(G_VERIFICAR_ALTURA);
        return;
      }
      if (!yaIniciado) {
        pasosSolicitados = IZAJE_PASOS_SEGURO * 3; // baja hasta que A0 detecte o se agote el recorrido
        iniciarMovimiento(false, false, pasosSolicitados);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        // se agoto el recorrido sin que A0 detectara nada: error
        yaIniciado = false;
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
      irA(G_ENERGIZAR_IMAN);
      break;
    }

    case G_ENERGIZAR_IMAN: {
      // CAMBIADO: el motor ya lo detuvo A0 en G_DESCENDER_CONTACTO. Aqui
      // se espera a que el FC confirme el contacto real antes de
      // energizar el electroiman (pedido del usuario: "el fc active el
      // electroiman"). Si el FC nunca confirma, se declara error en vez
      // de quedarse esperando para siempre.
      if (digitalRead(PIN_FC_CONTACTO) == LOW) {
        digitalWrite(PIN_ELECTROIMAN, HIGH);
        irA(G_CONFIRMAR_AGARRE);
      } else if (millis() - estadoDesdeMs > 2000) {
        irA(G_ERROR); // A0 detecto pero el FC nunca confirmo contacto real
      }
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
      // CAMBIADO (pedido del usuario): en vez de un numero fijo de pasos,
      // sube exactamente lo mismo que bajo en G_DESCENDER_CONTACTO
      // (pasosUltimoDescenso), contando pasos, sin sensor para la subida.
      static bool yaIniciado = false;
      if (!yaIniciado) {
        iniciarMovimiento(false, true, pasosUltimoDescenso);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        irA(G_TRASLADAR_DESTINO);
      }
      break;
    }

    case G_TRASLADAR_DESTINO: {
      if (posicionActual == trabajoActual->posicionDestino) { irA(G_DESCENDER_DEPOSITO); return; }
      if (!movimientoEnCurso) {
        bool haciaAdelante = trabajoActual->posicionDestino > posicionActual;
        long pasos = pasosEntre(posicionActual, trabajoActual->posicionDestino);
        iniciarMovimiento(true, haciaAdelante, pasos);
      } else if (movimientoTerminado()) {
        posicionActual = trabajoActual->posicionDestino;
        irA(G_DESCENDER_DEPOSITO);
      }
      break;
    }

    case G_DESCENDER_DEPOSITO: {
      // CAMBIADO (mismo patron que G_DESCENDER_CONTACTO): A0 para el
      // motor vertical y guarda cuantos pasos bajo; el FC se revisa
      // despues, en G_LIBERAR_IMAN, para confirmar contacto antes de
      // soltar el electroiman.
      static bool yaIniciado = false;
      static long pasosSolicitados = 0;

      if (digitalRead(PIN_MARCA_OPTICA) == LOW) {
        detenerMovimientoInmediato();
        pasosUltimoDescenso = pasosSolicitados - stepsRemaining;
        yaIniciado = false;
        irA(G_LIBERAR_IMAN);
        return;
      }
      if (!yaIniciado) {
        pasosSolicitados = IZAJE_PASOS_SEGURO * 3;
        iniciarMovimiento(false, false, pasosSolicitados);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        irA(G_ERROR);
      }
      break;
    }

    case G_LIBERAR_IMAN: {
      // CAMBIADO: espera a que el FC confirme el contacto real antes de
      // soltar el electroiman (mismo criterio que G_ENERGIZAR_IMAN, pero
      // al reves: aqui se APAGA en vez de encender). Si el FC nunca
      // confirma, error en vez de esperar para siempre.
      if (digitalRead(PIN_FC_CONTACTO) == LOW) {
        digitalWrite(PIN_ELECTROIMAN, LOW);
        irA(G_CONFIRMAR_COLOCACION);
      } else if (millis() - estadoDesdeMs > 2000) {
        irA(G_ERROR); // A0 detecto pero el FC nunca confirmo contacto real
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
      // CAMBIADO: sube exactamente lo mismo que bajo en
      // G_DESCENDER_DEPOSITO (pasosUltimoDescenso), en vez de un numero
      // fijo, contando pasos sin sensor para la subida.
      static bool yaIniciado = false;
      if (!yaIniciado) {
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