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

  Reparto de sensores (CAMBIADO OTRA VEZ, pedido del usuario):
  - Se detectaron dos problemas de la version anterior:
    1) El horizontal dependia de A0 en tiempo real para saber cuando
       parar (marcasObjetivoMovimiento). Si en el regreso A0 no ve
       alguna marca (el sensor no responde igual en ese sentido, algo
       tapa el rayo, etc.), el motor no se detenia por marca y quedaba
       dando pasos hasta agotar el respaldo de seguridad (pasos por
       posicion * posiciones), que es un numero muy alto -> de ahi los
       ~5 minutos sin detenerse.
    2) El FC del izaje (PIN_FC_CONTACTO) se revisaba con digitalRead()
       desde crane_update() (loop()), no desde el tick del motor. Si
       loop() estaba ocupado en ese instante (ej. leyendo RFID en la
       garita), el stepper seguia dando pasos de mas DESPUES del
       contacto real antes de que el codigo se enterara, y esos pasos
       de mas quedaban grabados en pasosUltimoDescenso -- que es
       justo el numero que despues se usa para subir. De ahi el "sube
       dando un monton de pasos".
  - Solucion (misma filosofia en los dos ejes: pasos precalculados en
    vez de depender de un sensor en tiempo real, salvo donde de
    verdad hace falta "saber" algo que no se puede calcular):
    - A0 (PIN_MARCA_OPTICA) YA NO detiene el horizontal en vivo en los
      trabajos normales (G_MOVER_A_ORIGEN / G_TRASLADAR_DESTINO): esos
      movimientos usan unicamente pasosEntre() (pasos precalculados),
      que es simetrico -- misma distancia = mismos pasos en cualquier
      sentido, ida o vuelta. A0 se sigue leyendo cada tick (no se
      quito el sensor), pero solo cuenta marcas para diagnostico; ya
      no corta el movimiento en esos dos estados.
      A0 SI se sigue usando para detener el motor en vivo (via
      marcasParada=1 en iniciarMovimiento) en los dos lugares donde no
      hay otra forma de saberlo: el referenciado inicial
      (G_REFERENCIANDO_MOVER, la primera vez que no se sabe donde esta
      la grua) y la compuerta de espera (G_ESPERAR_LIBERAR_MARCA).
    - PIN_FC_CONTACTO ahora se revisa DENTRO del tick del motor (cada
      BASE_TICK_US = 100us), igual que A0, en vez de en loop(). Detiene
      el descenso al tocar el contenedor/la pila y, en el mismo tick,
      congela cuantos pasos llevaba dados (stepsRemainingAlContacto)
      para que pasosUltimoDescenso sea exacto. El electroiman se
      energiza/suelta en crane_update() apenas se nota la bandera
      contactoDetectadoFlag (un par de ms de diferencia maximo, no
      afecta al iman). La subida posterior sigue sin usar ningun
      sensor: sube exactamente los mismos pasos que bajo
      (pasosUltimoDescenso).
  - Limitacion conocida (documentada, no es un bug): al quitarle a A0 el
    corte en vivo del horizontal, la posicion de la grua (posicionActual)
    pasa a depender 100% del conteo de pasos, igual que ya pasaba con el
    izaje. Si el motor pierde pasos mecanicamente (por ejemplo por
    friccion o alguna obstruccion), ya no hay una revalidacion contra la
    marca fisica en cada viaje -- solo se corrige volviendo a referenciar
    (crane_forceReReference()). Es el mismo trade-off que el equipo ya
    acepto para el izaje.
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
// AGREGADO (pedido del usuario): cuantas marcas de A0 se esperan antes de
// detener el horizontal EN VIVO (dentro del propio tick), en vez de
// esperar a que se agoten los pasos precalculados. 0 = no aplica (ej.
// movimientos del eje de izaje, que no usan A0).
static volatile uint16_t marcasObjetivoMovimiento = 0;
static volatile bool marcaAnterior = false;
static volatile int8_t indiceSecuencia = 0;
static volatile bool sentidoActualPositivo = true;
// AGREGADO (pedido del usuario): igual que marcasObjetivoMovimiento pero
// para el FC del izaje. Si detenerEnContactoActivo esta encendido, el
// propio tick revisa PIN_FC_CONTACTO en cada BASE_TICK_US (ya no en
// loop()) y corta el descenso apenas detecta el contacto, congelando
// cuantos pasos llevaba dados en ese instante exacto (para que
// pasosUltimoDescenso no quede inflado por pasos de mas dados mientras
// loop() estaba ocupado en otra cosa).
static volatile bool detenerEnContactoActivo = false;
static volatile bool contactoDetectadoFlag = false;
static volatile long stepsRemainingAlContacto = 0;

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

  // CORREGIDO (bug historico, ya no aplica igual): antes la lectura de A0
  // estaba DENTRO del bloque que solo se ejecuta una vez por PASO del
  // motor (cada STEP_PULSE_HALF_PERIOD_US = 2500us), y si la marca fisica
  // del riel era mas angosta que lo que la grua avanza en un solo paso, el
  // pulso de A0 podia "colarse" entre dos lecturas y nunca detectarse. Se
  // sigue muestreando A0 en CADA tick base (cada 100us) por esa misma
  // razon -- ahora esto solo importa de verdad para el referenciado
  // inicial y G_ESPERAR_LIBERAR_MARCA, que son los unicos lugares que
  // dependen de A0 en vivo (ver nota de "Reparto de sensores" arriba, al
  // inicio del archivo). En los trabajos normales (G_MOVER_A_ORIGEN /
  // G_TRASLADAR_DESTINO) marcasObjetivoMovimiento queda en 0, asi que esto
  // solo cuenta marcas para diagnostico, no corta el movimiento.
  if (ejeActivoEsTraslacion) {
    // A0 es un IR digital normal (confirmado por el usuario), no un
    // sensor analogico de umbral. Se lee con digitalRead, misma logica
    // invertida que el resto de los IR del proyecto (LOW=activado).
    bool marcaAhora = (digitalRead(PIN_MARCA_OPTICA) == LOW);
    if (marcaAhora && !marcaAnterior) {
      marcasDetectadasEnMovimiento++;
      // AGREGADO (pedido del usuario): al llegar a la marca esperada, A0
      // apaga el horizontal EN VIVO (no espera a que se agoten los pasos
      // precalculados; esos quedan solo como respaldo de seguridad si la
      // marca fallara -- ver movimientoTerminado() en cada estado).
      if (marcasObjetivoMovimiento > 0 && marcasDetectadasEnMovimiento >= marcasObjetivoMovimiento) {
        movimientoEnCurso = false;
        stepsRemaining = 0;
      }
    }
    marcaAnterior = marcaAhora;
    if (!movimientoEnCurso) return; // ya se corto por la marca: no dar otro paso
  }

  // AGREGADO (pedido del usuario): mismo tratamiento que A0, pero para el
  // FC del izaje. Se revisa aqui, en cada tick base (100us), y NO desde
  // loop(), para que el corte sea exacto en el instante real del contacto
  // -- si se dejara para loop() y loop() estuviera ocupado (ej. leyendo
  // RFID), el motor seguiria dando pasos de mas antes de que el codigo se
  // enterara, y esos pasos de mas quedarian mal contados como parte del
  // descenso (eso inflaba pasosUltimoDescenso y hacia que la subida
  // posterior diera un monton de pasos de mas).
  if (!ejeActivoEsTraslacion && detenerEnContactoActivo) {
    if (digitalRead(PIN_FC_CONTACTO) == LOW) { // INPUT_PULLUP: LOW = contacto
      stepsRemainingAlContacto = stepsRemaining; // pasos que faltaban EN ESTE INSTANTE
      contactoDetectadoFlag = true;
      movimientoEnCurso = false;
      stepsRemaining = 0;
      return; // corta ya mismo, no dar otro paso ni avanzar la secuencia
    }
  }

  craneTickCounter++;
  if (craneTickCounter < craneTicksPorPulso) return;
  craneTickCounter = 0;

  indiceSecuencia += sentidoActualPositivo ? 1 : -1;
  if (indiceSecuencia > 7) indiceSecuencia = 0;
  if (indiceSecuencia < 0) indiceSecuencia = 7;

  if (ejeActivoEsTraslacion) {
    escribirBobinas(PIN_TRANS_IN1, PIN_TRANS_IN2, PIN_TRANS_IN3, PIN_TRANS_IN4, SECUENCIA_PASOS[indiceSecuencia]);
  } else {
    escribirBobinas(PIN_IZAJE_IN1, PIN_IZAJE_IN2, PIN_IZAJE_IN3, PIN_IZAJE_IN4, SECUENCIA_PASOS[indiceSecuencia]);
  }

  stepsRemaining--;
  if (stepsRemaining <= 0) movimientoEnCurso = false;
}

// mueve `pasos` pasos en el eje indicado, sin bloquear (el llamador debe
// esperar a que movimientoEnCurso vuelva a false consultando movimientoTerminado())
// marcasParada: cantidad de marcas de A0 que deben verse antes de que el
// tick corte el horizontal solo (0 = no usar A0 para parar; es el caso
// normal ahora para G_MOVER_A_ORIGEN/G_TRASLADAR_DESTINO, que usan solo
// pasos precalculados -- A0 con corte en vivo queda solo para el
// referenciado inicial).
// pararEnContactoFC: true solo para los descensos del izaje que deben
// detenerse al tocar el contenedor/la pila (el tick revisa el FC).
static void iniciarMovimiento(bool traslacion, bool sentidoPositivo, long pasos, uint16_t marcasParada = 0, bool pararEnContactoFC = false) {
  noInterrupts();
  ejeActivoEsTraslacion = traslacion;
  sentidoActualPositivo = sentidoPositivo;
  stepsRemaining = pasos;
  marcasDetectadasEnMovimiento = 0;
  marcasObjetivoMovimiento = marcasParada;
  detenerEnContactoActivo = pararEnContactoFC;
  contactoDetectadoFlag = false;
  stepsRemainingAlContacto = 0;
  craneTickCounter = 0;
  if (traslacion) {
    // CORREGIDO: marcaAnterior no se reseteaba aqui y quedaba con el
    // valor de la ULTIMA vez que se uso el eje horizontal (que puede ser
    // de varios estados atras, ej. justo antes de subir con el
    // contenedor, con el eje de izaje activo mientras tanto). Se vuelve
    // a leer el estado REAL de A0 al arrancar cada movimiento horizontal
    // para que la deteccion de flanco arranque desde la verdad fisica
    // actual, no de un valor viejo.
    marcaAnterior = (digitalRead(PIN_MARCA_OPTICA) == LOW);
  }
  movimientoEnCurso = true;
  interrupts();
}
static bool movimientoTerminado() { return !movimientoEnCurso; }
static void detenerMovimientoInmediato() {
  noInterrupts();
  movimientoEnCurso = false;
  stepsRemaining = 0;
  detenerEnContactoActivo = false; // por seguridad, que no quede "armado" para el proximo tick
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
        // CAMBIADO OTRA VEZ (pedido del usuario): ya NO se usa A0 para
        // cortar en vivo (eso era lo que se quedaba pegado 5 min si en el
        // regreso A0 no detectaba alguna marca). Ahora, mismo criterio que
        // el izaje: se confia en pasosEntre(), que es simetrico (misma
        // distancia = mismos pasos en cualquier sentido).
        iniciarMovimiento(true, haciaAdelante, pasos);
      } else if (movimientoTerminado()) {
        // NOTA: ya no se valida marcasDetectadasEnMovimiento contra lo
        // esperado aqui -- esa validacion dependia de que A0 viera todas
        // las marcas en cualquier sentido, que es justo lo que fallaba.
        // La posicion ahora se confia al conteo de pasos (ver limitacion
        // conocida documentada arriba, al inicio del archivo).
        posicionActual = trabajoActual->posicionOrigen;
        irA(G_DESCENDER_CONTACTO);
      }
      break;
    }

    // ---------- descenso hasta contacto ----------
    case G_DESCENDER_CONTACTO: {
      // CAMBIADO OTRA VEZ (pedido del usuario): ahora es el FC
      // (PIN_FC_CONTACTO), el fin de carrera fisico del cabezal, el que
      // detiene el descenso al tocar el contenedor/la pila -- A0 ya NO
      // participa aqui, queda dedicado exclusivamente al eje horizontal
      // (ver G_MOVER_A_ORIGEN / G_TRASLADAR_DESTINO). En el mismo
      // instante en que el FC confirma contacto se energiza el
      // electroiman (agarre); ya no hace falta un estado aparte
      // (G_ENERGIZAR_IMAN) que esperara al FC por separado.
      static bool yaIniciado = false;
      static long pasosSolicitados = 0;

      // CAMBIADO OTRA VEZ (pedido del usuario): ya no se lee el FC aqui
      // con digitalRead() -- eso pasaba en loop() y si loop() estaba
      // ocupado (ej. RFID en la garita) el motor seguia dando pasos de
      // mas antes de que este codigo se enterara del contacto, e
      // inflaba pasosUltimoDescenso (la subida despues daba un monton
      // de pasos de mas). Ahora contactoDetectadoFlag lo pone
      // crane_timerTick() en el instante exacto del contacto (revisa el
      // FC cada 100us), junto con stepsRemainingAlContacto ya congelado.
      if (contactoDetectadoFlag) {
        pasosUltimoDescenso = pasosSolicitados - stepsRemainingAlContacto;
        alturaDetectadaPasos = (uint8_t)(pasosUltimoDescenso / 100); // ajustar escala real
        digitalWrite(PIN_ELECTROIMAN, HIGH); // agarre, apenas se nota la bandera del contacto
        detenerEnContactoActivo = false;
        contactoDetectadoFlag = false;
        yaIniciado = false;
        irA(G_VERIFICAR_ALTURA);
        return;
      }
      if (!yaIniciado) {
        // CORREGIDO (pedido del usuario): antes pasosSolicitados =
        // IZAJE_PASOS_SEGURO*3 (900) se quedaba corto para el recorrido
        // real y el motor se quedaba sin pasos antes de que el FC
        // llegara a activarse. Ahora se le da un presupuesto de pasos
        // generoso (IZAJE_PASOS_MAX_DESCENSO) y el respaldo de seguridad
        // real es el timeout por tiempo de abajo (else if), no la
        // cantidad de pasos.
        pasosSolicitados = IZAJE_PASOS_MAX_DESCENSO;
        // pararEnContactoFC=true: el propio tick corta el descenso al
        // detectar el FC, ya no hace falta revisarlo aqui en loop().
        iniciarMovimiento(false, false, pasosSolicitados, 0, true);
        yaIniciado = true;
      } else if (millis() - estadoDesdeMs > IZAJE_TIMEOUT_MS) {
        // se agoto el TIEMPO de seguridad sin que el FC detectara contacto: error
        detenerMovimientoInmediato();
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
      // CAMBIADO (pedido del usuario): en vez de un numero fijo de pasos,
      // sube exactamente lo mismo que bajo en G_DESCENDER_CONTACTO
      // (pasosUltimoDescenso), contando pasos, sin sensor para la subida.
      static bool yaIniciado = false;
      if (!yaIniciado) {
        iniciarMovimiento(false, true, pasosUltimoDescenso);
        yaIniciado = true;
      } else if (movimientoTerminado()) {
        yaIniciado = false;
        // CAMBIADO (pedido del usuario): al terminar de subir, se queda
        // ahi -- no retoma el horizontal de inmediato, primero se espera
        // a que A0 deje de sensar (ver G_ESPERAR_LIBERAR_MARCA).
        irA(G_ESPERAR_LIBERAR_MARCA);
      }
      break;
    }

    // ---------- NUEVO (pedido del usuario): espera a que A0 deje de
    // detectar la marca antes de que el horizontal retome el movimiento.
    // Si se queda pegado aqui, revisar fisicamente el sensor A0 (sucio,
    // desalineado, o la marca fisica en mal estado). ----------
    case G_ESPERAR_LIBERAR_MARCA: {
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
        // CAMBIADO OTRA VEZ: mismo criterio que en G_MOVER_A_ORIGEN, ya no
        // se usa A0 para cortar en vivo (ver comentario ahi) -- este es
        // justo el tramo de regreso donde se quedaba 5 min sin parar.
        iniciarMovimiento(true, haciaAdelante, pasos);
      } else if (movimientoTerminado()) {
        posicionActual = trabajoActual->posicionDestino;
        irA(G_DESCENDER_DEPOSITO);
      }
      break;
    }

    case G_DESCENDER_DEPOSITO: {
      // CAMBIADO (mismo criterio que G_DESCENDER_CONTACTO): el FC detiene
      // el descenso y, en el mismo instante del contacto, suelta el
      // electroiman -- ya no hace falta un estado aparte (G_LIBERAR_IMAN,
      // eliminado) que esperara al FC por separado. A0 queda dedicado
      // exclusivamente al eje horizontal.
      static bool yaIniciado = false;
      static long pasosSolicitados = 0;

      // mismo cambio que en G_DESCENDER_CONTACTO: se lee la bandera que
      // pone crane_timerTick() en vivo, ya no digitalRead() en loop().
      if (contactoDetectadoFlag) {
        pasosUltimoDescenso = pasosSolicitados - stepsRemainingAlContacto;
        digitalWrite(PIN_ELECTROIMAN, LOW); // suelta el contenedor, apenas se nota la bandera del contacto
        detenerEnContactoActivo = false;
        contactoDetectadoFlag = false;
        yaIniciado = false;
        irA(G_CONFIRMAR_COLOCACION);
        return;
      }
      if (!yaIniciado) {
        // mismo criterio que G_DESCENDER_CONTACTO (ver comentario ahi)
        pasosSolicitados = IZAJE_PASOS_MAX_DESCENSO;
        iniciarMovimiento(false, false, pasosSolicitados, 0, true);
        yaIniciado = true;
      } else if (millis() - estadoDesdeMs > IZAJE_TIMEOUT_MS) {
        detenerMovimientoInmediato();
        yaIniciado = false;
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