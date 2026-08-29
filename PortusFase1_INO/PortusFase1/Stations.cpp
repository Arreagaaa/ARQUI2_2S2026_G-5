/*
  ============================================================
  Stations.cpp - PORTUS Fase 1

  Administra el arreglo de Turnos y las maquinas de estado de:
    - Garita (capacidad 1, controla el ingreso)
    - Pesaje + aguja desviadora (se cruza 2 veces por turno)
    - Zona de transferencia (capacidad 1, interactua con la grua)
    - Salida (capacidad 1)

  NOTA: el proyecto usa UNA SOLA pantalla LCD (estado general),
  no dos como en la version original del documento. La garita ya
  no tiene LCD propia: sus causas de rechazo se reportan via
  safety_reportarCausa() (consultable por consola serial con el
  comando ESTADO) y se senalizan con el semaforo. La LCD unica
  muestra el estado general del sistema, actualizado principalmente
  por la estacion de salida.

  Cada turno avanza de forma independiente; ninguna estacion lee
  ni modifica el turno de otro vehiculo (requisito de concurrencia
  del documento).
  ============================================================
*/
#include "Stations.h"
#include "Config.h"
#include "PreloadedData.h"
#include "Weighing.h"
#include "Crane.h"
#include "Yard.h"
#include "Safety.h"

#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Servo.h>

// CORREGIDO (otra vez): la prueba con el sketch DumpInfo confirmo que
// el RST del RC522 SI esta fijo a 3.3V por hardware (no conectado al
// pin 10) -- con RST_PIN=255 el modulo lee la tarjeta perfecto. El
// cambio anterior a PIN_RFID_RST estaba mal: el pin 10 del Mega no
// tiene nada conectado, queda flotando, y la libreria MFRC522 al
// recibir un pin de RST hace digitalRead() sobre el para decidir si
// hace un "reset duro". Si ese pin flota y lee LOW por ruido, la
// libreria se salta el reset por software normal (el que si configura
// bien el chip via SPI) y solo espera 50ms creyendo que reseteo por
// hardware -- dejando al RC522 mal inicializado. Por eso volvia 0x0.
// PIN_RFID_RST en Config.h queda sin usar (documenta que existe el
// pin por si algun dia se cablea fisicamente, pero hoy no aplica).
static MFRC522 rfid(PIN_RFID_SS, 255);
static LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);
static Servo servoTalanquera, servoAguja;

static Turno turnos[MAX_TURNOS];
static uint8_t siguienteIdTurno = 0;

// ---------------- utilidades de semaforo ----------------
static void semaforo(uint8_t pinR, uint8_t pinA, uint8_t pinV, char color) {
  digitalWrite(pinR, color == 'R');
  digitalWrite(pinA, color == 'A');
  digitalWrite(pinV, color == 'V');
}

static void lcdMostrar(const String &l1, const String &l2) {
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(l1.substring(0, LCD_COLS));
  lcd.setCursor(0, 1); lcd.print(l2.substring(0, LCD_COLS));
}

void stations_init() {
  SPI.begin();
  rfid.PCD_Init();

  // AGREGADO: self-test de comunicacion SPI con el RC522. Lee el
  // registro de version del chip (deberia ser 0x91 o 0x92 en modulos
  // genuinos). Si imprime 0x00 o 0xFF, el Arduino NO esta logrando
  // comunicarse con el modulo -> revisar cableado (SS=53, SCK=52,
  // MOSI=51, MISO=50, RST=10, VCC a 3.3V -no 5V-, GND comun) antes de
  // seguir buscando el bug en el software.
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print(F("RC522 VersionReg: 0x"));
  Serial.println(version, HEX);
  if (version == 0x00 || version == 0xFF) {
    Serial.println(F("ADVERTENCIA: no hay comunicacion SPI con el RC522. Revisar cableado/alimentacion (VCC debe ser 3.3V, no 5V)."));
  }

  Wire.begin();
  lcd.init();  lcd.backlight();
  lcdMostrar("PORTUS - Estado", "Esperando...");

  servoTalanquera.attach(PIN_SERVO_TALANQUERA);
  servoAguja.attach(PIN_SERVO_AGUJA);
  servoTalanquera.write(SERVO_CERRADO);
  servoAguja.write(AGUJA_RECTA);
  // AGREGADO: si esta linea se imprime, el firmware SI mando la orden a
  // los servos (attach + write). Si aun asi ninguno se mueve a su
  // posicion inicial, el problema es electrico: GND no compartido entre
  // la fuente externa y el Mega, o alimentacion de los servos.
  Serial.println(F("[SERVOS] attach + posicion inicial enviados (talanquera/aguja)"));

  pinMode(PIN_SEM_GARITA_R, OUTPUT); pinMode(PIN_SEM_GARITA_A, OUTPUT); pinMode(PIN_SEM_GARITA_V, OUTPUT);
  pinMode(PIN_SEM_TRANSF_R, OUTPUT); pinMode(PIN_SEM_TRANSF_A, OUTPUT); pinMode(PIN_SEM_TRANSF_V, OUTPUT);
  pinMode(PIN_FLECHA_VERDE, OUTPUT); pinMode(PIN_FLECHA_AMBAR, OUTPUT);

  pinMode(PIN_IR_ESPERA, INPUT);
  pinMode(PIN_IR_PESAJE, INPUT);
  pinMode(PIN_IR_TRANSFERENCIA, INPUT);
  pinMode(PIN_IR_SALIDA, INPUT);
  pinMode(PIN_IR_RAMAL, INPUT);

  semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'R');
  semaforo(PIN_SEM_TRANSF_R, PIN_SEM_TRANSF_A, PIN_SEM_TRANSF_V, 'R');

  for (uint8_t i = 0; i < MAX_TURNOS; i++) turnos[i].activo = false;
}

static Turno* turnoLibre() {
  for (uint8_t i = 0; i < MAX_TURNOS; i++) if (!turnos[i].activo) return &turnos[i];
  return nullptr;
}

// ============================================================
// GARITA (capacidad 1)
// ============================================================
enum EstadoGarita { GAR_LIBRE, GAR_LEYENDO, GAR_VALIDANDO, GAR_ESPERANDO_TALANQUERA, GAR_AUTORIZADO_ESPERANDO_PASO, GAR_RECHAZADO_MOSTRANDO };
static EstadoGarita estadoGarita = GAR_LIBRE;
static uint32_t garitaDesdeMs = 0;
static Turno *turnoEnGarita = nullptr;

// Garita y Salida comparten el mismo servo/semaforo (misma talanquera fisica).
// Esta variable evita que ambos lo controlen al mismo tiempo si llegan a
// coincidir dos camiones (uno entrando, otro saliendo) en simultaneo.
// 0 = libre, 1 = lo tiene la garita, 2 = lo tiene la salida.
static uint8_t duenoTalanquera = 0;

static void garita_update() {
  switch (estadoGarita) {
    case GAR_LIBRE: {
      if (digitalRead(PIN_IR_ESPERA) == LOW) { // vehiculo detectado (sensor con logica invertida: LOW = presencia)
        semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'A');
        estadoGarita = GAR_LEYENDO;
        garitaDesdeMs = millis();
      }
      break;
    }
    case GAR_LEYENDO: {
      // CORREGIDO: ya NO se usa noInterrupts()/interrupts() aqui.
      // SPI.transfer() (usado internamente por MFRC522) es espera activa
      // por hardware y no requiere que las interrupciones globales esten
      // apagadas para funcionar bien. Apagarlas globalmente detenia
      // tambien el Timer2 compartido (Weighing/Crane), los timers de
      // Servo (talanquera/puerta/aguja) y, lo mas grave, la interrupcion
      // externa del paro de emergencia (Safety.cpp) mientras el vehiculo
      // permanecia frente al sensor de la garita -- eso era lo que hacia
      // "trabarse" todo el sistema al activar el IR (pin 2).
      // Si en algun momento se detecta ruido real en la lectura SPI por
      // el tick de Timer2, la forma segura de mitigarlo es pausar SOLO
      // esa interrupcion puntual (TIMSK2 &= ~(1 << OCIE2A); ... TIMSK2 |=
      // (1 << OCIE2A);), nunca con noInterrupts() global.
      bool hayTarjeta = rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial();

      if (!hayTarjeta) {
        if (millis() - garitaDesdeMs > 4000) {
          safety_reportarCausa("RFID no leido");
          estadoGarita = GAR_RECHAZADO_MOSTRANDO;
          garitaDesdeMs = millis();
        }
        return;
      }
      int idCamion = buscarCamionPorUID(rfid.uid.uidByte, rfid.uid.size);
      rfid.PICC_HaltA();

      Serial.print("Tarjeta leida, UID: ");
      for (byte i = 0; i < rfid.uid.size; i++) {
        Serial.print(rfid.uid.uidByte[i] < 0x10 ? " 0" : " ");
        Serial.print(rfid.uid.uidByte[i], HEX);
      }
      Serial.println();

      if (idCamion < 0) {
        safety_reportarCausa("RFID no reconocido");
        estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
      }
      if (!CAMIONES[idCamion].autorizadoLocal) {
        safety_reportarCausa("Camion no autorizado");
        estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
      }
      int idManif = buscarManifiestoPendiente(idCamion);
      if (idManif == -1) {
        safety_reportarCausa("Sin manifiesto pendiente");
        estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
      }
      if (idManif == -2) {
        safety_reportarCausa("Varios manifiestos pendientes");
        estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
      }
      Manifiesto &m = MANIFIESTOS[idManif];
      if (m.tipo == OP_NINGUNA) {
        safety_reportarCausa("Operacion invalida");
        estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
      }

      // condiciones especificas de capacidad segun el tipo de operacion
      int8_t posicionAsignada = -1;
      if (m.tipo == OP_DEPOSITO) {
        posicionAsignada = yard_buscarPosicionLibre();
        if (posicionAsignada < 0) {
          safety_reportarCausa("Sin posicion accesible en patio");
          estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
        }
      } else if (m.tipo == OP_RETIRO) {
        int8_t pos = yard_localizarContenedor(m.idContenedor);
        if (pos < 0 || yard_getEstado(pos) == POS_BLOQUEADA) {
          safety_reportarCausa("Contenedor no ubicable en patio");
          estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
        }
        posicionAsignada = pos;
      }

      // todo correcto: crear turno
      Turno *t = turnoLibre();
      if (t == nullptr) {
        safety_reportarCausa("Siguiente estacion no disponible");
        estadoGarita = GAR_RECHAZADO_MOSTRANDO; garitaDesdeMs = millis(); return;
      }

      t->id = siguienteIdTurno++;
      t->activo = true;
      t->idCamion = idCamion;
      t->idManifiesto = idManif;
      t->estacionActual = EST_GARITA;
      t->siguienteEstacion = EST_PESAJE;
      t->pesajeInicialValido = false;
      t->pesajeFinalValido = false;
      t->posicionPatioAsignada = posicionAsignada;
      t->retenido = false;
      t->esperandoGrua = false;
      t->cantidadTrabajosGrua = 0;
      t->timestampInicioMs = millis();
      m.estado = MANIF_EN_PROCESO;

      if (m.tipo == OP_DEPOSITO) yard_reservarPosicion(posicionAsignada);

      turnoEnGarita = t;
      lcdMostrar(String("Camion ") + CAMIONES[idCamion].placa,
                 m.tipo == OP_DEPOSITO ? "Operac: DEPOSITO" : "Operac: RETIRO");
      estadoGarita = GAR_ESPERANDO_TALANQUERA;
      break;
    }
    case GAR_ESPERANDO_TALANQUERA: {
      // la talanquera es compartida con salida: si salida la tiene ocupada
      // ahorita, esperamos aqui en vez de pisarle el servo/semaforo
      if (duenoTalanquera == 2) return;
      duenoTalanquera = 1;
      semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'V');
      servoTalanquera.write(SERVO_ABIERTO);
      estadoGarita = GAR_AUTORIZADO_ESPERANDO_PASO;
      break;
    }
    case GAR_AUTORIZADO_ESPERANDO_PASO: {
      // cuando el IR ya no detecta al vehiculo bajo la talanquera, se cierra
      if (digitalRead(PIN_IR_ESPERA) == HIGH) { // sensor con logica invertida: HIGH = sin presencia
        servoTalanquera.write(SERVO_CERRADO);
        semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'R');
        duenoTalanquera = 0;
        turnoEnGarita->estacionActual = EST_PESAJE;
        turnoEnGarita = nullptr;
        estadoGarita = GAR_LIBRE;
      }
      break;
    }
    case GAR_RECHAZADO_MOSTRANDO: {
      servoTalanquera.write(SERVO_CERRADO);
      semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'R');
      // La causa ya quedo registrada en Safety (consultable por consola con ESTADO).
      if (millis() - garitaDesdeMs > 3000) {
        estadoGarita = GAR_LIBRE;
      }
      break;
    }
  }
}

// ============================================================
// PESAJE + AGUJA (capacidad 1, se cruza 2 veces por turno)
// ============================================================
enum EstadoPesaje { PES_LIBRE, PES_CAPTURANDO, PES_EVALUANDO };
static EstadoPesaje estadoPesaje = PES_LIBRE;
static Turno *turnoEnPesaje = nullptr;

static Turno* buscarTurnoParaPesaje() {
  for (uint8_t i = 0; i < MAX_TURNOS; i++) {
    if (turnos[i].activo && turnos[i].estacionActual == EST_PESAJE && !turnos[i].pesajeInicialValido && !turnos[i].retenido)
      return &turnos[i];
  }
  for (uint8_t i = 0; i < MAX_TURNOS; i++) {
    if (turnos[i].activo && turnos[i].estacionActual == EST_SALIDA && !turnos[i].pesajeFinalValido)
      return &turnos[i];
  }
  return nullptr;
}

static void pesaje_update() {
  weighing_update();

  // NUEVO: si un camion esta retenido esperando en el ramal (ya en
  // camino a salida) y el sensor IR del ramal (pin 26) se activa, se
  // le da por bueno el pesaje final automaticamente (como salida ya
  // acepta cualquier peso, esto solo lo deja avanzar sin tener que
  // volver a cruzar fisicamente la bascula). No aplica si ya tiene el
  // pesaje final valido.
  if (digitalRead(PIN_IR_RAMAL) == LOW) {
    for (uint8_t i = 0; i < MAX_TURNOS; i++) {
      if (turnos[i].activo && turnos[i].retenido &&
          turnos[i].estacionActual == EST_SALIDA && !turnos[i].pesajeFinalValido) {
        turnos[i].pesajeFinalValido = true;
        safety_reportarCausa("Liberado por sensor ramal: pesaje final forzado");
      }
    }
  }

  switch (estadoPesaje) {
    case PES_LIBRE: {
      if (digitalRead(PIN_IR_PESAJE) == LOW && turnoEnPesaje == nullptr) { // sensor con logica invertida: LOW = presencia
        Turno *t = buscarTurnoParaPesaje();
        if (t != nullptr) {
          turnoEnPesaje = t;
          weighing_startCapture();
          estadoPesaje = PES_CAPTURANDO;
        }
      }
      break;
    }
    case PES_CAPTURANDO: {
      static uint32_t ultimoPrintMs = 0;
      if (millis() - ultimoPrintMs > 300) {
        Serial.print(F("Peso en vivo: "));
        Serial.print(weighing_getLiveKg(), 2);
        Serial.println(F(" kg"));
        ultimoPrintMs = millis();
      }
      // Si se activa el sensor IR del ramal (pin 26) MIENTRAS se esta
      // pesando, este sensor manda: mueve la aguja al ramal de una vez
      // (sin esperar el resultado del peso) y marca el turno retenido.
      if (digitalRead(PIN_IR_RAMAL) == LOW && !turnoEnPesaje->retenido) {
        safety_reportarCausa("Retenido manual durante el pesaje (sensor ramal)");
        turnoEnPesaje->retenido = true;
        digitalWrite(PIN_FLECHA_VERDE, LOW); digitalWrite(PIN_FLECHA_AMBAR, HIGH);
        servoAguja.write(AGUJA_RAMAL);
      }
      if (weighing_resultReady()) estadoPesaje = PES_EVALUANDO;
      break;
    }
    case PES_EVALUANDO: {
      float lecturaKg = weighing_getResultKg();
      Manifiesto &m = MANIFIESTOS[turnoEnPesaje->idManifiesto];
      Camion &c = CAMIONES[turnoEnPesaje->idCamion];
      bool esInicial = !turnoEnPesaje->pesajeInicialValido && turnoEnPesaje->estacionActual == EST_PESAJE;
      bool dentroDeTolerancia;

      Serial.print(F("Peso leido: "));
      Serial.print(lecturaKg, 2);
      Serial.print(F(" kg  (declarado: "));
      Serial.print(m.pesoDeclaradoKg, 2);
      Serial.print(F(" kg, tolerancia: +-"));
      Serial.print(m.toleranciaKg, 2);
      Serial.println(F(" kg)"));

      if (turnoEnPesaje->retenido) {
        // el sensor IR del ramal ya decidio por su cuenta: se respeta
        // esa decision sin importar si el peso hubiera salido bien.
        // Se marca pesajeFinalValido de una vez: como salida ya acepta
        // cualquier peso, no hace falta que vuelva a cruzar la bascula.
        turnoEnPesaje->pesajeInicialKg = lecturaKg;
        turnoEnPesaje->pesajeInicialValido = true;
        turnoEnPesaje->pesajeFinalKg = lecturaKg;
        turnoEnPesaje->pesajeFinalValido = true;
        turnoEnPesaje->estacionActual = EST_SALIDA;
        safety_reportarCausa("Desviado por sensor de ramal (pin 26)");
      } else if (esInicial) {
        if (m.tipo == OP_DEPOSITO) {
          float pesoContenedor = lecturaKg - c.taraKg;
          dentroDeTolerancia = fabs(pesoContenedor - m.pesoDeclaradoKg) <= m.toleranciaKg;
        } else { // OP_RETIRO: el camion entra vacio, se compara contra su tara
          dentroDeTolerancia = fabs(lecturaKg - c.taraKg) <= m.toleranciaKg;
        }
        turnoEnPesaje->pesajeInicialKg = lecturaKg;
        turnoEnPesaje->pesajeInicialValido = true;

        if (dentroDeTolerancia) {
          digitalWrite(PIN_FLECHA_VERDE, HIGH); digitalWrite(PIN_FLECHA_AMBAR, LOW);
          servoAguja.write(AGUJA_RECTA);
          turnoEnPesaje->estacionActual = EST_TRANSFERENCIA;
        } else {
          digitalWrite(PIN_FLECHA_VERDE, LOW); digitalWrite(PIN_FLECHA_AMBAR, HIGH);
          servoAguja.write(AGUJA_RAMAL);
          turnoEnPesaje->retenido = true;
          turnoEnPesaje->pesajeFinalKg = lecturaKg;
          turnoEnPesaje->pesajeFinalValido = true; // no necesita pesarse otra vez, salida acepta cualquier peso
          turnoEnPesaje->estacionActual = EST_SALIDA; // ya no se detiene en el ramal: va directo a salida
          safety_reportarCausa("Pesaje fuera de tolerancia, desviado a salida");
        }
      } else { // pesaje final (antes de salida): AGREGADO, ahora acepta cualquier peso
        dentroDeTolerancia = true; // ya no se rechaza por peso en la salida
        turnoEnPesaje->pesajeFinalKg = lecturaKg;
        turnoEnPesaje->pesajeFinalValido = dentroDeTolerancia;
      }

      weighing_reset();
      turnoEnPesaje = nullptr;
      estadoPesaje = PES_LIBRE;
      break;
    }
  }
}

// ============================================================
// ZONA DE TRANSFERENCIA (capacidad 1, interactua con la grua)
// ============================================================
enum EstadoTransf { TR_LIBRE, TR_ESPERANDO_VEHICULO, TR_TRABAJANDO, TR_FINALIZANDO };
static EstadoTransf estadoTransf = TR_LIBRE;
static Turno *turnoEnTransf = nullptr;

static Turno* buscarTurnoParaTransferencia() {
  for (uint8_t i = 0; i < MAX_TURNOS; i++)
    if (turnos[i].activo && turnos[i].estacionActual == EST_TRANSFERENCIA && !turnos[i].esperandoGrua)
      return &turnos[i];
  return nullptr;
}

static void transferencia_update() {
  switch (estadoTransf) {
    case TR_LIBRE: {
      Turno *t = buscarTurnoParaTransferencia();
      if (t != nullptr) { turnoEnTransf = t; estadoTransf = TR_ESPERANDO_VEHICULO; }
      break;
    }
    case TR_ESPERANDO_VEHICULO: {
      semaforo(PIN_SEM_TRANSF_R, PIN_SEM_TRANSF_A, PIN_SEM_TRANSF_V, 'R');
      if (digitalRead(PIN_IR_TRANSFERENCIA) == LOW) { // sensor con logica invertida: LOW = presencia
        Manifiesto &m = MANIFIESTOS[turnoEnTransf->idManifiesto];
        int idTrabajo;
        if (m.tipo == OP_DEPOSITO) {
          idTrabajo = crane_enqueue(TRABAJO_DEPOSITO, turnoEnTransf->id,
                                     POS_TRANSFERENCIA, 1 + turnoEnTransf->posicionPatioAsignada,
                                     m.idContenedor);
        } else {
          // Si el contenedor no esta en el tope de la pila, primero se
          // encola una remocion hacia una posicion libre auxiliar.
          uint8_t nivelesAhi = yard_getNiveles(turnoEnTransf->posicionPatioAsignada);
          if (nivelesAhi > 1) {
            int8_t posAux = yard_buscarPosicionLibre();
            crane_enqueue(TRABAJO_REMOCION, turnoEnTransf->id,
                          1 + turnoEnTransf->posicionPatioAsignada,
                          1 + posAux, 255 /* contenedor superior, id gestionado por Yard */);
          }
          idTrabajo = crane_enqueue(TRABAJO_RETIRO, turnoEnTransf->id,
                                     1 + turnoEnTransf->posicionPatioAsignada, POS_TRANSFERENCIA,
                                     m.idContenedor);
        }
        turnoEnTransf->idsTrabajoGrua[turnoEnTransf->cantidadTrabajosGrua++] = idTrabajo;
        turnoEnTransf->esperandoGrua = true;
        estadoTransf = TR_TRABAJANDO;
      }
      break;
    }
    case TR_TRABAJANDO: {
      // aborta si el vehiculo se mueve durante la transferencia
      if (digitalRead(PIN_IR_TRANSFERENCIA) == HIGH) { // sensor con logica invertida: HIGH = sin presencia
        safety_reportarCausa("Movimiento del camion durante transferencia");
        // AGREGADO: se marca retenido -- antes esto abortaba la
        // transferencia pero dejaba pasar al camion como si nada.
        // Se puede demostrar tapando con la mano este sensor IR
        // mientras la grua esta trabajando.
        turnoEnTransf->retenido = true;
        crane_emergencyHalt();
        estadoTransf = TR_FINALIZANDO;
        return;
      }
      uint8_t ultimoJob = turnoEnTransf->idsTrabajoGrua[turnoEnTransf->cantidadTrabajosGrua - 1];
      if (crane_isJobDone(ultimoJob)) {
        estadoTransf = TR_FINALIZANDO;
      } else if (crane_isJobError(ultimoJob)) {
        safety_reportarCausa("Error en operacion de grua");
        // AGREGADO: mismo criterio, un error real de la grua tambien
        // deja el turno retenido en vez de dejarlo seguir.
        turnoEnTransf->retenido = true;
        estadoTransf = TR_FINALIZANDO;
      }
      break;
    }
    case TR_FINALIZANDO: {
      turnoEnTransf->estacionActual = EST_SALIDA;
      turnoEnTransf->esperandoGrua = false;
      turnoEnTransf = nullptr;
      estadoTransf = TR_LIBRE;
      break;
    }
  }
}

// ============================================================
// SALIDA (capacidad 1)
// ============================================================
enum EstadoSalida { SAL_LIBRE, SAL_ESPERANDO_PESAJE_FINAL, SAL_VALIDANDO, SAL_ESPERANDO_LLEGADA, SAL_ESPERANDO_TALANQUERA, SAL_SEMAFORO_VERDE_ESPERANDO, SAL_AUTORIZADA, SAL_RECHAZADA };
static EstadoSalida estadoSalida = SAL_LIBRE;
static Turno *turnoEnSalida = nullptr;
static uint32_t salidaDesdeMs = 0;

static Turno* buscarTurnoParaSalida() {
  for (uint8_t i = 0; i < MAX_TURNOS; i++)
    if (turnos[i].activo && turnos[i].estacionActual == EST_SALIDA) return &turnos[i];
  return nullptr;
}

static void salida_update() {
  static EstadoSalida estadoAnterior = SAL_LIBRE;
  if (estadoSalida != estadoAnterior) {
    Serial.print(F("[SALIDA] cambio de estado -> "));
    Serial.println((int)estadoSalida);
    estadoAnterior = estadoSalida;
  }

  switch (estadoSalida) {
    case SAL_LIBRE: {
      Turno *t = buscarTurnoParaSalida();
      if (t != nullptr) { turnoEnSalida = t; estadoSalida = SAL_ESPERANDO_PESAJE_FINAL; }
      break;
    }
    case SAL_ESPERANDO_PESAJE_FINAL: {
      if (turnoEnSalida->pesajeInicialValido && turnoEnSalida->pesajeFinalValido) {
        estadoSalida = SAL_VALIDANDO;
      } else if (turnoEnSalida->retenido) {
        // AJUSTADO: antes decia siempre "Anomalia de peso" en el LCD,
        // pero ahora un turno tambien puede quedar retenido por un
        // problema en la transferencia/grua. Se muestra la causa real
        // registrada por safety_reportarCausa().
        lcdMostrar("RETENIDO", safety_getUltimaCausa());
        estadoSalida = SAL_RECHAZADA;
        salidaDesdeMs = millis();
      }
      // si aun no hay pesaje final, la estacion de pesaje se encarga
      // de tomarlo cuando el camion vuelva a cruzar la plataforma.
      break;
    }
    case SAL_VALIDANDO: {
      bool condiciones = turnoEnSalida->pesajeFinalValido &&
                          !turnoEnSalida->esperandoGrua;
      // AJUSTADO: se quito el bloqueo por "retenido" (peso fuera de
      // tolerancia o desviado por el sensor de ramal). Ahora esos
      // camiones tambien pueden salir con normalidad.
      if (condiciones) {
        MANIFIESTOS[turnoEnSalida->idManifiesto].estado = MANIF_COMPLETADO;
        lcdMostrar("Turno finalizado", CAMIONES[turnoEnSalida->idCamion].placa);
        estadoSalida = SAL_ESPERANDO_LLEGADA;
      } else {
        lcdMostrar("RECHAZADO", "Validacion pend.");
        estadoSalida = SAL_RECHAZADA;
        salidaDesdeMs = millis();
      }
      break;
    }
    case SAL_ESPERANDO_LLEGADA: {
      // NUEVO: el pesaje final se puede validar mientras el camion
      // sigue en la bascula, lejos todavia de la puerta compartida.
      // No se abre nada hasta que el sensor IR de salida (pin 19)
      // confirme que el camion YA esta fisicamente ahi.
      if (digitalRead(PIN_IR_SALIDA) == LOW) { // sensor con logica invertida: LOW = presencia
        estadoSalida = SAL_ESPERANDO_TALANQUERA;
      }
      break;
    }
    case SAL_ESPERANDO_TALANQUERA: {
      // la talanquera es compartida con garita: si garita la tiene ocupada
      // ahorita, esperamos aqui en vez de pisarle el servo/semaforo
      if (duenoTalanquera == 1) return;
      duenoTalanquera = 2;
      // AJUSTADO: primero se enciende el semaforo en verde solo; el
      // servo se activa despues, una vez confirmado el verde.
      semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'V');
      salidaDesdeMs = millis();
      estadoSalida = SAL_SEMAFORO_VERDE_ESPERANDO;
      break;
    }
    case SAL_SEMAFORO_VERDE_ESPERANDO: {
      // pequena pausa para que el semaforo se vea encendido antes de
      // que se mueva la talanquera (evita que ambos pasen "a la vez")
      if (millis() - salidaDesdeMs >= 400) {
        servoTalanquera.write(SERVO_ABIERTO);
        estadoSalida = SAL_AUTORIZADA;
      }
      break;
    }
    case SAL_AUTORIZADA: {
      if (digitalRead(PIN_IR_SALIDA) == HIGH) { // sensor con logica invertida: HIGH = sin presencia
        servoTalanquera.write(SERVO_CERRADO);
        semaforo(PIN_SEM_GARITA_R, PIN_SEM_GARITA_A, PIN_SEM_GARITA_V, 'R');
        duenoTalanquera = 0;
        turnoEnSalida->estacionActual = EST_FINALIZADO;
        turnoEnSalida->activo = false; // libera el slot de turno
        turnoEnSalida = nullptr;
        estadoSalida = SAL_LIBRE;
      }
      break;
    }
    case SAL_RECHAZADA: {
      if (millis() - salidaDesdeMs > 3000) {
        lcdMostrar("PORTUS - Estado", "Esperando...");
        estadoSalida = SAL_ESPERANDO_PESAJE_FINAL; // reintenta cuando se corrija
      }
      break;
    }
  }
}

// ============================================================
void stations_update() {
  garita_update();
  pesaje_update();
  transferencia_update();
  salida_update();
  yard_update();
}

uint8_t stations_contarTurnosActivos() {
  uint8_t n = 0;
  for (uint8_t i = 0; i < MAX_TURNOS; i++) if (turnos[i].activo) n++;
  return n;
}

void stations_imprimirEstadoTurno(uint8_t indice) {
  if (indice >= MAX_TURNOS || !turnos[indice].activo) return;
  Turno &t = turnos[indice];
  Serial.print(F("Turno ")); Serial.print(t.id);
  Serial.print(F(" | Camion ")); Serial.print(CAMIONES[t.idCamion].placa);
  Serial.print(F(" | Estacion ")); Serial.print((int)t.estacionActual);
  Serial.print(F(" | Retenido: ")); Serial.print(t.retenido ? "SI" : "NO");
  Serial.print(F(" | PesajeInicial: ")); Serial.print(t.pesajeInicialKg);
  Serial.print(F(" | PesajeFinal: ")); Serial.println(t.pesajeFinalKg);
}