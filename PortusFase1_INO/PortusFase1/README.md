# PORTUS - Fase 1 - Codigo fuente (Arduino Mega)

## Como abrir esto en el Arduino IDE

1. Crea una carpeta llamada **exactamente** `PortusFase1` (el IDE exige que el
   nombre de la carpeta coincida con el del archivo `.ino`).
2. Copia todos los archivos de este paquete dentro de esa carpeta.
3. Abre `PortusFase1.ino` con el Arduino IDE. Los demas archivos apareceran
   como pestañas.
4. Selecciona placa **Arduino Mega or Mega 2560** y el puerto correspondiente.

## Librerias que hay que instalar (Herramientas > Administrar Bibliotecas)

- `MFRC522` (by GithubCommunity) - lector RFID
- `LiquidCrystal_I2C` (by Frank de Brabander, o cualquier fork compatible)
- `Servo` - ya viene incluida con el IDE, no requiere instalacion

## Antes de subir el codigo: cosas que SI o SI hay que ajustar

1. **UID de los tags RFID** — en `PreloadedData.h`, arreglo `CAMIONES[]`.
   Para leer el UID real de cada tarjeta, sube primero el ejemplo
   `MFRC522 > DumpInfo` (viene con la libreria), abre el monitor serial,
   acerca cada tag y copia el UID que imprime.

2. **Calibracion de las celdas de carga** — en `Weighing.cpp`:
   - `OFFSET_CAL`: lectura cruda con la plataforma vacia (sumatoria de
     ambos HX711). Se obtiene corriendo el sistema, viendo por consola
     (agregar un print temporal si hace falta) el valor crudo en reposo.
   - `FACTOR_CAL`: cuentas por kilogramo. Se calcula poniendo un peso
     conocido sobre la plataforma y despejando: `FACTOR_CAL = (lectura_cruda - OFFSET_CAL) / peso_kg_conocido`.

3. **Pasos por posicion de la grua** — `PASOS_POR_POSICION_DEFECTO` en
   `Config.h`. En movimiento normal ya NO se usa para decidir cuando
   parar: el sensor A0 (marca optica) detiene el horizontal en vivo
   apenas ve la marca esperada (ver `Crane.cpp`, `crane_timerTick`).
   `PASOS_POR_POSICION_DEFECTO` solo queda como presupuesto de pasos de
   respaldo, por si la marca fallara. Igual conviene ajustarlo cerca del
   valor real: mueve la grua una posicion y cuenta cuantos pasos toma
   llegar de una marca optica a la siguiente.

4. **Polaridad de los sensores IR y de ocupacion** — el codigo asume
   HIGH = "detecta vehiculo/contenedor". Si tus sensores son activos en
   bajo, invierte la condicion en `Stations.cpp` y `Yard.cpp` (buscar los
   `digitalRead(...)  == HIGH` / `== LOW`).

5. **Sensores de la grua (A0 y FC)** — `PIN_MARCA_OPTICA` (A0) y
   `PIN_FC_CONTACTO` en `Crane.cpp` son IR digitales (`digitalRead`, no
   `analogRead`), logica invertida (LOW = activado). A0 es exclusivo del
   eje horizontal (marcas del riel) y FC es exclusivo del eje de izaje
   (contacto con el contenedor/pila, dispara el electroiman). Si algun
   sensor real es activo en alto, invierte la comparacion correspondiente
   en `Crane.cpp`.

## Pines usados (resumen — el detalle completo esta en Config.h)

| Modulo               | Pines Mega                          |
|-----------------------|--------------------------------------|
| RFID RC522 (SPI)      | SS=53, RST=49, SCK=52, MOSI=51, MISO=50 |
| HX711 celda A / B     | DOUT=22/23, SCK=24 (compartido)      |
| Motor traslacion (28BYJ-48+ULN2003) | IN1-IN4 = 30,31,32,33   |
| Motor izaje (28BYJ-48+ULN2003)      | IN1-IN4 = 34,35,36,37   |
| Marca optica (A0, horizontal)       | A0                      |
| Fin de carrera CONTACTO (izaje)     | 38                      |
| Electroiman           | 39                                    |
| Servo talanquera      | 5                                     |
| Servo puerta salida   | 6                                     |
| Servo aguja desviadora| 7                                     |
| Semaforo garita       | R=40, A=41, V=42                     |
| Semaforo transferencia| R=43, A=44, V=45                     |
| Semaforo salida       | R=46, A=47, V=48                     |
| Flecha pesaje         | Verde=8, Ambar=9                     |
| IR espera/pesaje/...  | 2, 3, 18, 19, 20                     |
| Paro de emergencia    | 21 (INT2, interrupcion real)         |
| Patio (ocup./LED)     | A8-A11 / A12-A15                     |
| LCD garita / salida   | I2C 0x27 / 0x26                      |

## Timers usados (para que el equipo lo tenga presente al agregar cosas)

- **Servo library**: ocupa internamente Timer1/3/4/5 completos en el Mega.
- **Timer2** (8 bits, el unico que queda libre): tick base compartido,
  inicializado por `Weighing.cpp` (`weighing_init()`). En cada tick llama
  tanto al muestreo de los HX711 como a `crane_timerTick()`, que avanza
  los pasos de los motores de la grua (traslacion o izaje). Ver el
  encabezado de `Crane.cpp` para el detalle.
- **INT5 (pin 18)**: interrupcion externa dedicada al paro de emergencia.

Si agregan mas timers, eviten Timer0 (lo usa `millis()`/`delay()`).

## Que SI cubre este codigo (alineado al alcance obligatorio del documento)

- Identificacion RFID en garita con validaciones y causas de rechazo
  explicitas (RFID no reconocido, sin manifiesto, manifiesto duplicado,
  sin posicion en patio, etc.)
- Pesaje dinamico con mediana sobre una meseta estable, muestreado por
  interrupcion de timer (no bloqueante), 2 HX711 sincronizados por
  reloj compartido.
- Aguja desviadora controlada por el resultado del pesaje.
- Grua de 2 GDL con referenciado por marcas opticas (no solo conteo de
  pasos): A0 detiene el horizontal en vivo al llegar a la marca
  esperada, FC detiene el descenso y dispara el electroiman al hacer
  contacto, y la subida usa como referencia los mismos pasos del
  descenso. Ciclo completo de deposito/retiro/remocion, cola de
  trabajos FIFO documentada.
- Patio con inventario que solo se actualiza tras confirmacion fisica.
- Concurrencia: turnos independientes por camion, sin que una estacion
  toque el turno de otro vehiculo.
- Paro de emergencia por interrupcion real, con rearme explicito.
- Consola serial de supervision (comandos ESTADO, PATIO, GRUA, REARME).

## Que queda pendiente / simplificado y el equipo debe reforzar

- La verificacion de "agarre confirmado" del electroiman es por tiempo
  fijo (300 ms); si quieren mayor robustez, agreguen un sensor de
  proximidad o lectura de corriente del electroiman.
- La deteccion de "posible levantamiento de dos contenedores" no esta
  implementada explicitamente; puede inferirse comparando el peso
  izado (si agregan una celda en el cabezal) contra el peso esperado.
- El manejo de remociones asume que siempre hay una posicion libre
  auxiliar; si quieren, agreguen la validacion explicita de "si no hay
  posicion disponible, la operacion no debe comenzar" antes de encolar.
- Falta pulir el mensaje de "causa concreta" en la pantalla de salida
  para separar bien "retenido por peso" de "esperando pesaje final".
- Probar y ajustar tiempos (millis) de cada maquina de estados una vez
  que el hardware este armado; los valores actuales son de partida.

Cualquier ajuste de logica de negocio (tolerancias, cantidad de
camiones, cantidad de posiciones del patio) se hace en `Config.h` y
`PreloadedData.h`, sin tocar el resto del codigo.
