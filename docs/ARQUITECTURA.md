# Arquitectura del Sistema - PORTUS Fase 1

## Descripcion General

PORTUS es un sistema de control firmware para una maqueta fisica de una terminal de contenedores. El Arduino Mega 2560 orquesta el flujo completo de operaciones: ingreso de camiones por RFID, pesaje dinamico, desvio o autorizacion por peso, operaciones de grua en la zona de transferencia, y gestion del patio de almacenamiento.

Todo el control se basa en maquinas de estado no bloqueantes. La funcion `loop()` nunca ejecuta `delay()` ni entra en bucles de espera. Cada modulo se actualiza una vez por ciclo de loop, avanzando su maquina de estado segun las condiciones actuales de los sensores y la logica interna.

## Flujo Operativo

El ciclo de vida de una operacion (un "turno") sigue estas etapas:

```
Camion llega
    |
    v
[GARITA] ---RFID---> Validar UID + manifiesto pendiente
    |                     |
    | (rechazo)           | (aprobado)
    v                     v
  Salida             [PESAJE INICIAL]
  (3s, causa)             |
                          v
                    [AGUJA DESVIADORA]
                     /            \
           (en tolerancia)   (fuera de tolerancia)
                /                    \
               v                      v
    [ZONA TRANSFERENCIA]        [SALIDA RETENIDA]
               |                      |
               v                      v
          [GRUA]               Pesaje final
               |               (anomalia)
               v                      |
          [PATIO]                     v
               |                 [SALIDA]
               v
    [PESAJE FINAL]
               |
               v
          [SALIDA]
```

### Estaciones y capacidades

| Estacion | Capacidad | Descripcion |
|---|---|---|
| Garita | 1 camion | Lee RFID, valida contra base local, crea turno |
| Pesaje/Aguja | 1 camion | Cruza la plataforma 2 veces (inicial y final) |
| Zona Transferencia | 1 camion | Interactua con la grua para deposito/retiro |
| Patio | 2 posiciones x 2 niveles | Almacenamiento apilable de contenedores |
| Salida | 1 camion | Pesaje final, validacion, apertura de talanquera |

### Condiciones de rechazo en garita

El sistema rechaza un camion por cualquiera de estas razones:
1. RFID no leido en 4 segundos
2. UID no reconocido en la base local
3. Camion no autorizado (`autorizadoLocal = false`)
4. Sin manifiesto pendiente para ese camion
5. Mas de un manifiesto pendiente para ese camion
6. Operacion invalida en el manifiesto (`OP_NINGUNA`)
7. Sin posicion accesible en el patio (para depositos)
8. Contenedor no ubicable en el patio (para retiros)
9. Todos los turnos ocupados (maximo 6 concurrentes)

## Modulos del Firmware

### Config.h
Definicion centralizada de pines y constantes. Todo el codigo referencia estas definiciones; no se usan numeros de pin directamente en el resto de los archivos.

### DataModels.h
Estructuras de datos: `Camion`, `Contenedor`, `Manifiesto`, `Turno`. Todos los registros viven en RAM/PROGMEM del Mega, no hay base de datos externa.

### PreloadedData.h
Datos precargados para la demostracion: 6 camiones (3 con RFID real), 10 contenedores, 8 manifiestos (5 operaciones activas). Los UIDs de RFID deben editarse con los valores reales de las tarjetas fisicas.

### Weighing.cpp / Weighing.h
Pesaje dinamico con 2 celdas HX711. Muestreo por interrupcion de Timer2. Buffer circular de 64 muestras con filtrado por mediana. Deteccion de meseta estable (minimo 1.4 segundos). Formula de conversion: `kg = (raw - OFFSET_CAL) / FACTOR_CAL`.

Dueño exclusivo del ISR de Timer2. En cada tick, tambien llama a `crane_timerTick()` para que la grua cuente sus pasos.

### Crane.cpp / Crane.h
Grua de 2 grados de libertad (traslacion longitudinal + izaje vertical). Motores 28BYJ-48 con secuencia half-step (8 pasos). Cola FIFO de trabajos (deposito, retiro, remocion). Maquina de estado con 16 estados internos. Referenciado por deteccion de marca optica (sin fin de carrera fisico de home).

### Yard.cpp / Yard.h
Patio lineal apilable. Cada posicion tiene 2 niveles, cada nivel con su propio sensor LDR. El inventario solo se modifica despues de confirmacion fisica (lectura analogica del LDR), nunca por comando directo de software. Estados de cada posicion: libre, reservada, ocupada, bloqueada.

### Stations.cpp / Stations.h
Administra el arreglo de turnos y las maquinas de estado de garita, pesaje, zona de transferencia y salida. Cada turno avanza de forma independiente; ninguna estacion modifica el turno de otro vehiculo.

### Safety.cpp / Safety.h
Paro de emergencia por interrupcion externa real (INT5, pin 18). Pulsador momentaneo: cada pulsacion alterna el estado (detiene/reanuda). Incluye debounce de 250ms. Al activarse, energiza el electroiman para evitar que se suelte la carga. Requiere rearme explicito (boton o comando REARME por consola). Registra la ultima causa de error/retencion.

### Console.cpp / Console.h
Consola serial a 115200 baud. Lectura no bloqueante de comandos. Soporta comandos de consulta (ESTADO, PATIO, GRUA, PESO), comandos de calibracion (CRUDO, TARA, CALIBRAR), y rearme (REARME).

## Asignacion de Timers

En el Arduino Mega, la libreria `Servo.h` consume internamente Timer1, Timer3, Timer4 y Timer5. Esto deja disponible unicamente Timer2 (8 bits) para el resto del sistema.

| Timer | Uso | Dueño |
|---|---|---|
| Timer1 | Servo (talanquera, aguja) | Servo.h (interno) |
| Timer2 | Tick base de 100us compartido | Weighing.cpp (ISR) + Crane.cpp |
| Timer3 | Servo | Servo.h (interno) |
| Timer4 | Servo | Servo.h (interno) |
| Timer5 | Servo | Servo.h (interno) |

El tick base de 100us (definido en `BASE_TICK_US`) se configura en modo CTC con prescaler 8, resultando en un reloj de cuenta de 2 MHz sobre el Mega a 16 MHz.

## Estructura de Turnos

Cada camion dentro de la terminal tiene un `Turno` asociado. El sistema soporta hasta 6 turnos concurrentes (`MAX_TURNOS`). Un turno contiene:

- Identificador del camion y manifiesto asociado
- Estacion actual y siguiente estacion
- Pesaje inicial y final (valores y banderas de validez)
- Posicion asignada en el patio
- Bandera de retencion (si fue desviado al ramal)
- Trabajos de grua asociados (hasta 3)
- Timestamp de inicio

El turno se crea en la garita cuando el RFID valida correctamente, y se destruye cuando el camion cruza la barrera de salida.
