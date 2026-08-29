/*
  ============================================================
  PORTUS - Fase 1
  Arquitectura de Computadoras y Ensambladores 2 - USAC

  Sketch principal. TODO el codigo esta organizado en pestañas
  (archivos .h/.cpp) por modulo:

    Config.h        - pines y constantes
    DataModels.h     - structs de Camion/Contenedor/Manifiesto/Turno
    PreloadedData.h  - registros precargados (EDITAR los UID de RFID aqui)
    Weighing.h/.cpp  - pesaje dinamico con 2x HX711, dueno de Timer2
                       (unico timer de 8 bits libre en el Mega, ya que
                       Servo.h ocupa Timer1/3/4/5 completos)
    Crane.h/.cpp     - grua 2 GDL, cola de trabajos; recibe ticks de
                       Timer2 desde Weighing.cpp via crane_timerTick()
    Yard.h/.cpp      - patio lineal apilable
    Stations.h/.cpp  - garita, pesaje/aguja, transferencia, salida
    Safety.h/.cpp    - paro de emergencia (interrupcion externa)
    Console.h/.cpp   - consola serial de supervision

  IMPORTANTE: loop() jamas debe usar delay() ni while() de espera.
  Todo el control es mediante maquinas de estado no bloqueantes
  que se actualizan un tick por iteracion de loop().

  Librerias necesarias (Administrador de Librerias del IDE):
    - MFRC522 (por GithubCommunity)
    - LiquidCrystal_I2C (por Frank de Brabander o similar)
    - Servo (incluida con el IDE; ocupa Timer1/3/4/5 en el Mega)
  ============================================================
*/
#include "Config.h"
#include "Weighing.h"
#include "Crane.h"
#include "Yard.h"
#include "Stations.h"
#include "Safety.h"
#include "Console.h"

void setup() {
  console_init();      // Serial.begin() debe ir primero
  safety_init();        // registra la interrupcion del paro de emergencia
  weighing_init();      // arranca Timer2 (tick base compartido con Crane)
  crane_init();          // configura pines de motores/sensores; NO tiene timer propio
  yard_init();
  stations_init();

  Serial.println(F("Sistema inicializado. La grua se referenciara automaticamente."));
}

void loop() {
  // Si el paro de emergencia esta activo, se detiene la operacion normal
  // pero la consola sigue viva para poder consultar el estado y rearmar.
  static bool estopActivoAnterior = false;
  bool estopActivoAhora = safety_isEstopActive();

  if (estopActivoAhora) {
    // nada mas que hacer: crane_emergencyHalt() ya se llamo desde el ISR
  } else if (estopActivoAnterior && !estopActivoAhora) {
    // el boton acaba de desactivar el paro (segunda pulsacion): rearme automatico
    safety_requestRearm();
    Serial.println(F("Reanudado automaticamente por boton de paro."));
  }
  estopActivoAnterior = estopActivoAhora;

  if (!estopActivoAhora) {
    stations_update();   // garita, pesaje, transferencia, salida
    crane_update();       // avanza la maquina de estados de la grua
  }

  console_update();       // siempre activo, no bloqueante
}