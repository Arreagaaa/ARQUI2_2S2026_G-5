/*
  ============================================================
  Weighing.cpp - PORTUS Fase 1

  IMPORTANTE: en el Arduino Mega, la libreria Servo.h ocupa
  internamente los 4 timers de 16 bits (Timer1, Timer3, Timer4,
  Timer5). Por eso el muestreo del HX711 y los pulsos de la grua
  NO pueden tener cada uno su propio timer de 16 bits: comparten
  el UNICO timer libre (Timer2, 8 bits) mediante un "tick base"
  cada BASE_TICK_US. Weighing.cpp es el dueno del ISR de Timer2;
  en cada tick llama tambien a crane_timerTick() para que Crane.cpp
  cuente sus propios pasos sin necesitar su propio timer.

  Como funciona el pesaje:
  - Cada tick base (100 us) se revisa si toca tomar una muestra del
    HX711 (cada HX711_SAMPLE_PERIOD_US). El loop() principal jamas
    espera al pesaje con delay() ni while().
  - Cuando toca muestrear, se revisa si ambos HX711 tienen dato listo
    (DOUT baja a LOW cuando la conversion termino). Si ambos estan
    listos AL MISMO TIEMPO, se hace una rafaga de 24 pulsos de reloj
    COMPARTIDO, leyendo en cada pulso el bit de DOUT1 y DOUT2 de forma
    consecutiva, para que ambas conversiones correspondan al mismo
    instante fisico.
  - Cada muestra (suma celda A + celda B) se guarda en un buffer
    circular. weighing_update() (llamado desde loop) revisa si las
    ultimas N muestras forman una meseta estable durante al menos
    MESETA_MIN_MS; si es asi, calcula la mediana y publica el resultado.
  ============================================================
*/
#include "Weighing.h"
#include "Config.h"
#include "Crane.h"

// ---------- estado compartido entre ISR y loop (volatile) ----------
static volatile long  bufferGramos[HX711_MAX_MUESTRAS];
static volatile uint16_t bufferHead = 0;
static volatile bool  capturando = false;
static volatile uint32_t ultimaMuestraMs = 0;

// factor de calibracion: gramos = cuentaCruda / FACTOR_CAL - OFFSET_CAL
// AJUSTAR estos dos valores con un patron de peso conocido.
static float FACTOR_CAL  = -85494.9f;  // calibrado (celdas fijas): 0.196kg = diferencia de -16757 cuentas
static long  OFFSET_CAL  = 348005;     // re-zero: lectura cruda con la plataforma vacia (tras reconectar celda B)

// resultado publicado hacia el resto del sistema
static bool  resultadoListo = false;
static float resultadoKg = 0.0f;

// deteccion de meseta
static uint32_t inicioMesetaMs = 0;
static bool     enMeseta = false;
static long     ultimaLecturaEstable = 0;
#define UMBRAL_ESTABILIDAD_CUENTAS 800  // ajustar segun ruido real de las celdas

// ---------- contador de ticks para el muestreo del HX711 ----------
static volatile uint16_t weighingTickCounter = 0;
static uint16_t weighingTicksPorMuestra = 0;

// ---------- lectura sincronizada de los 2 HX711 (llamada desde el tick) ----------
// Usa manipulacion directa de puertos para minimizar el tiempo entre
// flancos de reloj (el HX711 exige pulsos de reloj cortos; permanecer
// demasiado tiempo con SCK en alto apaga el chip).
static inline bool hx711ListoAmbos() {
  return (digitalRead(PIN_HX711_DOUT1) == LOW) &&
         (digitalRead(PIN_HX711_DOUT2) == LOW);
}

static void leerHX711Sincronizado(long &valorA, long &valorB) {
  uint8_t portMaskSCK = digitalPinToBitMask(PIN_HX711_SCK);
  volatile uint8_t *portSCK = portOutputRegister(digitalPinToPort(PIN_HX711_SCK));

  long a = 0, b = 0;
  for (uint8_t i = 0; i < 24; i++) {
    *portSCK |= portMaskSCK;              // SCK = HIGH (pulso)
    delayMicroseconds(1);
    a = (a << 1) | digitalRead(PIN_HX711_DOUT1);
    b = (b << 1) | digitalRead(PIN_HX711_DOUT2);
    *portSCK &= ~portMaskSCK;             // SCK = LOW
    delayMicroseconds(1);
  }
  // 25o pulso: fija la ganancia/canal en 128 para el siguiente ciclo
  *portSCK |= portMaskSCK;
  delayMicroseconds(1);
  *portSCK &= ~portMaskSCK;

  // extension de signo (24 bits -> 32 bits)
  if (a & 0x800000) a |= 0xFF000000;
  if (b & 0x800000) b |= 0xFF000000;
  valorA = a;
  valorB = b;
}

// Se ejecuta DENTRO de la ISR de Timer2 (ver mas abajo), cuando toca
// muestrear. Ya no es su propia ISR de timer dedicado.
static void weighing_hacerMuestreo() {
  if (!capturando) return;
  if (!hx711ListoAmbos()) return; // conversion aun no lista, se reintenta en el proximo tick

  long a, b;
  leerHX711Sincronizado(a, b);
  long suma = a + b;

  bufferGramos[bufferHead] = suma;
  bufferHead = (bufferHead + 1) % HX711_MAX_MUESTRAS;
  ultimaMuestraMs = millis();
}

// ---------- ISR de Timer2: tick base COMPARTIDO con Crane ----------
// Este es el UNICO vector de interrupcion propio que usa este modulo
// (y el unico timer de 8 bits libre en el Mega, ya que Servo.h ocupa
// Timer1/3/4/5). En cada disparo: 1) revisa si toca muestrear el
// pesaje, 2) avisa a Crane para que cuente sus propios pasos.
ISR(TIMER2_COMPA_vect) {
  weighingTickCounter++;
  if (weighingTickCounter >= weighingTicksPorMuestra) {
    weighingTickCounter = 0;
    weighing_hacerMuestreo();
  }
  crane_timerTick();
}

void weighing_init() {
  pinMode(PIN_HX711_SCK, OUTPUT);
  digitalWrite(PIN_HX711_SCK, LOW);
  pinMode(PIN_HX711_DOUT1, INPUT);
  pinMode(PIN_HX711_DOUT2, INPUT);

  weighingTicksPorMuestra = HX711_SAMPLE_PERIOD_US / BASE_TICK_US;
  if (weighingTicksPorMuestra == 0) weighingTicksPorMuestra = 1;

  // Timer2 en modo CTC, prescaler 8 -> 2 MHz de reloj de cuenta (Mega @16MHz)
  noInterrupts();
  TCCR2A = 0;
  TCCR2B = 0;
  TCNT2  = 0;
  uint8_t ticks = (uint8_t)((16000000UL / 8UL) * ((float)BASE_TICK_US / 1000000.0f));
  OCR2A = ticks;
  TCCR2A |= (1 << WGM21);              // CTC
  TCCR2B |= (1 << CS21);               // prescaler = 8
  TIMSK2 |= (1 << OCIE2A);             // habilita interrupcion por comparacion
  interrupts();

  capturando = false;
  resultadoListo = false;
}

void weighing_startCapture() {
  noInterrupts();
  bufferHead = 0;
  for (uint16_t i = 0; i < HX711_MAX_MUESTRAS; i++) bufferGramos[i] = 0;
  weighingTickCounter = 0;
  capturando = true;
  interrupts();
  resultadoListo = false;
  enMeseta = false;
  inicioMesetaMs = 0;
}

void weighing_reset() {
  noInterrupts();
  capturando = false;
  interrupts();
  resultadoListo = false;
}

// mediana simple sobre las ultimas K muestras validas del buffer circular
static long medianaUltimasK(uint16_t k) {
  long copia[HX711_MAX_MUESTRAS];
  uint16_t n = 0;
  noInterrupts();
  uint16_t head = bufferHead;
  interrupts();
  for (uint16_t i = 0; i < k && i < HX711_MAX_MUESTRAS; i++) {
    uint16_t idx = (head + HX711_MAX_MUESTRAS - 1 - i) % HX711_MAX_MUESTRAS;
    copia[n++] = bufferGramos[idx];
  }
  // insertion sort (n es pequeno, suficiente)
  for (uint16_t i = 1; i < n; i++) {
    long key = copia[i];
    int j = i - 1;
    while (j >= 0 && copia[j] > key) { copia[j+1] = copia[j]; j--; }
    copia[j+1] = key;
  }
  return (n == 0) ? 0 : copia[n/2];
}

// ultima lectura "reciente" (mediana de 5 muestras), para monitoreo en vivo
static volatile long ultimaLecturaRecienteCruda = 0;

void weighing_update() {
  if (!capturando || resultadoListo) return;

  uint32_t ahora = millis();
  if (ultimaMuestraMs == 0) return;

  long lecturaReciente = medianaUltimasK(5);
  ultimaLecturaRecienteCruda = lecturaReciente;

  if (!enMeseta) {
    // primera vez que aparece una lectura "significativa" (fuera del offset vacio)
    if (labs(lecturaReciente - OFFSET_CAL) > UMBRAL_ESTABILIDAD_CUENTAS) {
      enMeseta = true;
      inicioMesetaMs = ahora;
      ultimaLecturaEstable = lecturaReciente;
    }
    return;
  }

  // ya estamos en meseta candidata: verificar estabilidad
  if (labs(lecturaReciente - ultimaLecturaEstable) > UMBRAL_ESTABILIDAD_CUENTAS) {
    // hubo un salto brusco -> reinicia deteccion de meseta (vehiculo aun cruzando)
    enMeseta = true;
    inicioMesetaMs = ahora;
    ultimaLecturaEstable = lecturaReciente;
    return;
  }

  if (ahora - inicioMesetaMs >= MESETA_MIN_MS) {
    long medianaFinal = medianaUltimasK(20);
    // FACTOR_CAL se calibra para que este cociente entregue kilogramos directamente.
    resultadoKg = (float)(medianaFinal - OFFSET_CAL) / FACTOR_CAL;
    resultadoListo = true;
    capturando = false;
  }
}

bool weighing_resultReady() { return resultadoListo; }
float weighing_getResultKg() { return resultadoKg; }

// Peso "en vivo" (no confirmado por meseta aun), util para monitoreo
// por consola mientras el camion esta cruzando las celdas.
float weighing_getLiveKg() {
  return (float)(ultimaLecturaRecienteCruda - OFFSET_CAL) / FACTOR_CAL;
}

// Lectura CRUDA sin calibrar (sin restar OFFSET_CAL ni dividir por
// FACTOR_CAL). Solo para el proceso de calibracion.
long weighing_getLiveRaw() {
  return ultimaLecturaRecienteCruda;
}

// Lectura directa "bajo demanda" de las 2 celdas, independiente del
// ciclo normal de captura de un camion. Espera hasta que el HX711
// tenga dato listo (con timeout de 500ms). Pensada solo para el
// proceso de calibracion desde el comando CRUDO de la consola.
bool weighing_readRawNow(long &sumaCruda, long &celdaA, long &celdaB) {
  uint32_t inicio = millis();
  while (!hx711ListoAmbos()) {
    if (millis() - inicio > 500) return false; // timeout, revisar cableado
  }
  leerHX711Sincronizado(celdaA, celdaB);
  sumaCruda = celdaA + celdaB;
  return true;
}

// CORREGIDO: weighing_tare() original hacia 10 lecturas con
// weighing_readRawNow() (hasta 500ms cada una) + delay(20) entre
// ellas = hasta 5+ segundos bloqueando loop(). Eso congelaba todas
// las estaciones, la grua y la consola. Ahora se reduce a 3 lecturas
// sin delay() entre ellas (max ~1.5s total en el peor caso). La
// precision es suficiente para tarar con plataforma vacia; si se
// necesita mas promediado, hacerlo con el comando CRUDO y ajustar
// OFFSET_CAL manualmente.
bool weighing_tare(long &nuevoOffset) {
  long suma = 0;
  uint8_t leidas = 0;
  for (uint8_t i = 0; i < 3; i++) {
    long s, a, b;
    if (!weighing_readRawNow(s, a, b)) continue;
    suma += s;
    leidas++;
  }
  if (leidas == 0) return false;
  OFFSET_CAL = suma / leidas;
  nuevoOffset = OFFSET_CAL;
  return true;
}