/*
  ============================================================
  Config.h - PORTUS Fase 1
  Definicion centralizada de pines (Arduino Mega 2560) y
  constantes del sistema. Ajustar aqui segun el cableado real
  de la maqueta; el resto del codigo NO deberia tocar numeros
  de pin directamente.
  ============================================================
*/
#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ---------------------------------------------------------
// RFID (modulo RC522, bus SPI)
// ---------------------------------------------------------
#define PIN_RFID_SS    53
#define PIN_RFID_RST   10
// SCK=52, MOSI=51, MISO=50 son fijos por el bus SPI del Mega

// ---------------------------------------------------------
// Pesaje dinamico - 2 x HX711 (reloj compartido, datos separados)
// ---------------------------------------------------------
#define PIN_HX711_SCK   24   // reloj COMPARTIDO por ambas celdas
#define PIN_HX711_DOUT1 22   // celda extremo A
#define PIN_HX711_DOUT2 23   // celda extremo B

// ---------------------------------------------------------
// Grua: motor de traslacion longitudinal (28BYJ-48 + driver ULN2003)
// ---------------------------------------------------------
#define PIN_TRANS_IN1  30
#define PIN_TRANS_IN2  31
#define PIN_TRANS_IN3  32
#define PIN_TRANS_IN4  33

// ---------------------------------------------------------
// Grua: motor de izaje vertical (28BYJ-48 + driver ULN2003)
// ---------------------------------------------------------
#define PIN_IZAJE_IN1  34
#define PIN_IZAJE_IN2  35
#define PIN_IZAJE_IN3  36
#define PIN_IZAJE_IN4  37

// ---------------------------------------------------------
// Grua: sensor de contacto (unico fin de carrera fisico usado;
// los limites izquierdo/derecho del riel se quitaron y el
// referenciado ahora usa la primera marca optica detectada)
// ---------------------------------------------------------
#define PIN_FC_CONTACTO  38
// Marca optica de posicion sobre el riel (una por posicion de trabajo)
#define PIN_MARCA_OPTICA A0  // sensor que detecta el paso por una marca

// ---------------------------------------------------------
// Electroiman del cabezal (via modulo de rele)
// ---------------------------------------------------------
#define PIN_ELECTROIMAN 39   // IN del modulo de rele

// ---------------------------------------------------------
// Servomotores
// ---------------------------------------------------------
#define PIN_SERVO_TALANQUERA 5   // garita
// PIN_SERVO_PUERTA eliminado: salida unificada con garita (usa PIN_SERVO_TALANQUERA)
#define SERVO_CERRADO   0
#define SERVO_ABIERTO   90

// ---------------------------------------------------------
// Semaforos (R/A/V) por estacion
// ---------------------------------------------------------
#define PIN_SEM_GARITA_R  40
#define PIN_SEM_GARITA_A  41
#define PIN_SEM_GARITA_V  42

#define PIN_SEM_TRANSF_R  43
#define PIN_SEM_TRANSF_A  44
#define PIN_SEM_TRANSF_V  45

// Semaforo de salida eliminado: salida unificada con garita (usa PIN_SEM_GARITA_*)

// ---------------------------------------------------------
// Flecha luminosa del pesaje (dos direcciones)
// ---------------------------------------------------------
#define PIN_FLECHA_VERDE  8   // continuar a transferencia
#define PIN_FLECHA_AMBAR  9   // desviar al ramal

// ---------------------------------------------------------
// Aguja desviadora (servo de una sola hoja)
// ---------------------------------------------------------
#define PIN_SERVO_AGUJA   7
#define AGUJA_RECTA       0    // continua hacia transferencia
#define AGUJA_RAMAL       90   // desvia al ramal

// ---------------------------------------------------------
// Sensores infrarrojos de presencia de vehiculo
// ---------------------------------------------------------
#define PIN_IR_ESPERA        2
#define PIN_IR_PESAJE        3
#define PIN_IR_TRANSFERENCIA 25
#define PIN_IR_SALIDA        19  // sensor independiente; comparte servo/semaforo con garita
#define PIN_IR_RAMAL         26

// ---------------------------------------------------------
// Paro de emergencia (boton tipo hongo, normalmente cerrado -> abre al presionar)
// Usa INT5 (pin 18) para atencion inmediata por interrupcion real.
// ---------------------------------------------------------
#define PIN_PARO_EMERGENCIA 18
#define PARO_ACTIVO_EN_LOW  true   // con INPUT_PULLUP, se activa al ir a LOW

// ---------------------------------------------------------
// Patio: 2 posiciones, hasta 2 niveles cada una.
// Un sensor LDR POR NIVEL (no uno solo por posicion), para poder
// distinguir 0, 1 o 2 contenedores apilados en cada posicion.
// ---------------------------------------------------------
#define YARD_POS_COUNT 2
#define YARD_MAX_NIVELES 2

// YARD_OCC_PIN[posicion][nivel]: nivel 0 = base, nivel 1 = segundo piso
static const uint8_t YARD_OCC_PIN[YARD_POS_COUNT][YARD_MAX_NIVELES] = {
  { A8, A9 },    // posicion 0: LDR nivel 0, LDR nivel 1
  { A10, A11 }   // posicion 1: LDR nivel 0, LDR nivel 1
};
static const uint8_t YARD_LED_PIN[YARD_POS_COUNT] = { A12, A13 };

// Umbral de deteccion para los LDR del patio. Por debajo de este
// valor (lectura de analogRead) se considera "tapado" (contenedor
// encima). Un solo numero global NO sirve: cada LDR tiene su propia
// luz base segun sombra/angulo, y con datos reales las 4 lecturas de
// "vacio" (818, 509, 190, 382) y "ocupado" (273, 204, 202, 210) estan
// demasiado dispersas para compartir un umbral. Se calibro un umbral
// por sensor, a mitad de camino entre su vacio y su ocupado reales:
//   P0N0: vacio=818 ocupado=273 -> umbral 545
//   P0N1: vacio=509 ocupado=204 -> umbral 356
//   P1N0: vacio=190 ocupado=202 -> SIN separacion confiable (ver nota
//         abajo, esto es un problema fisico del sensor/montaje, no de
//         software; el umbral que se puso aqui es un valor provisional
//         y NO va a distinguir tapado/destapado en ese sensor)
//   P1N1: vacio=382 ocupado=210 -> umbral 295
// NOTA sobre P1N0: la lectura con contenedor (202) salio MAS ALTA que
// la lectura en vacio (190) -- practicamente no hay diferencia entre
// tapado y destapado. Revisar fisicamente ese sensor: posible luz
// entrando por un costado, LDR mal orientado, o el contenedor no lo
// cubre bien en esa posicion. Ningun ajuste de umbral arregla eso.
static const int UMBRAL_LDR_OSCURO[YARD_POS_COUNT][YARD_MAX_NIVELES] = {
  { 545, 356 }, // posicion 0: nivel 0, nivel 1
  { 150, 295 }  // posicion 1: nivel 0 (provisional, ver nota), nivel 1
};

// ---------------------------------------------------------
// Pantalla LCD I2C. NOTA: el proyecto usa UNA SOLA pantalla
// (estado general), no dos como planteaba el documento original.
// Ver Stations.cpp para el detalle de esta simplificacion.
// ---------------------------------------------------------
#define LCD_ADDR 0x27
#define LCD_COLS 16
#define LCD_ROWS 2

// ---------------------------------------------------------
// Parametros de pesaje dinamico
// ---------------------------------------------------------
#define VELOCIDAD_NOMINAL_CM_S   5.0
#define MESETA_MIN_MS            1400UL   // 1.4 s minimo de meseta
#define HX711_SAMPLE_PERIOD_US   500      // periodo de muestreo del pesaje
#define HX711_MAX_MUESTRAS       64       // buffer circular para mediana
#define TOLERANCIA_PESO_KG       5.0      // ajustar segun calibracion

// ---------------------------------------------------------
// Tick base compartido (Timer2) para Weighing y Crane, ya que
// Servo.h ocupa Timer1/3/4/5 completos en el Mega y solo deja
// libre Timer2 (8 bits) para el resto del sistema.
// ---------------------------------------------------------
#define BASE_TICK_US 100

// ---------------------------------------------------------
// Parametros de la grua (pasos = unidad de movimiento)
// Motores reales: 28BYJ-48 (5V, con reductor 1/64), mas lentos
// que un NEMA17 - el periodo de pulso se subio de 400 a 2500 us
// para no perder pasos. Ajustar segun pruebas reales.
// ---------------------------------------------------------
#define PASOS_POR_POSICION_DEFECTO 800   // valor de respaldo si falla la marca
#define PASOS_TOLERANCIA_MARCA     50    // margen antes de declarar perdida de referencia
#define IZAJE_PASOS_SEGURO         300   // altura segura para trasladar con carga
#define STEP_PULSE_HALF_PERIOD_US  2500  // 28BYJ-48: mas lento que NEMA17+A4988

// ---------------------------------------------------------
// Cantidad de posiciones "de trabajo" de la grua sobre el riel
// (posicion 0 = transferencia, 1..YARD_POS_COUNT = patio)
// ---------------------------------------------------------
#define TOTAL_POSICIONES_RIEL (YARD_POS_COUNT + 1)
#define POS_TRANSFERENCIA 0

#endif