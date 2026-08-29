# Guia de Instalacion de Hardware - PORTUS Fase 1

## Materiales Requeridos

### Microcontrolador y placa
- 1x Arduino Mega 2560
- 1x Cable USB Type-A a Type-B (para programacion y alimentacion serial)

### Alimentacion
- 1x Fuente externa 5V/2A minimo (para servos, motores stepper, electroiman)
- Cables de conexion a tierra comun entre fuente externa y Mega

### Sensores
- 1x Modulo RFID MFRC522 (lector de tags, bus SPI)
- 2x Tarjetas RFID de 4 bytes (asignar a camiones en `PreloadedData.h`)
- 2x Celda de carga HX711 (con sus respectivos sensores de peso)
- 5x Sensor infrarrojo de presencia (logica invertida: LOW = presencia)
- 4x Sensor LDR (para deteccion de ocupacion en el patio, divisor de voltaje con resistencia externa a GND)
- 1x Sensor optico de marca de posicion (sobre el riel de la grua)
- 1x Sensor de contacto (fin de carrera en el cabezal de la grua)

### Actuadores
- 2x Servomotores (talanquera y aguja desviadora)
- 2x Motor stepper 28BYJ-48 con driver ULN2003 (traslacion e izaje de la grua)
- 1x Electroiman (via modulo de rele)
- 6x LED para semaforos (2x R/A/V: garita y zona de transferencia)
- 2x LED flecha direccional (verde y ambar, zona de pesaje)
- 2x LED de estado del patio

### Pantalla
- 1x Pantalla LCD 16x2 con interfaz I2C (direccion 0x27)

### Seguridad
- 1x Boton pulsador momentaneo (paro de emergencia, normalmente cerrado, pin 18)

### Maqueta fisica
- Estructura del riel de la grua (longitud según la cantidad de posiciones del patio)
- Plataforma de pesaje (soporte para las 2 celdas de carga)
- Base del patio con 2 posiciones, cada una con capacidad para 2 niveles
- Camiones miniatura con tags RFID adheridos
- Contenedores miniatura (magnetizados para el electroiman)

## Conexiones Electricas

Consultar el archivo `DIAGRAMA-PINES.md` en esta misma carpeta para el mapeo completo de pines. Las conexiones criticas que requieren atencion especial son:

1. **RFID MFRC522**: Alimentar con 3.3V (no 5V). El pin RST del modulo en esta implementacion esta fijo a 3.3V por hardware y no se conecta al Mega. Verificar que la communicateion SPI funcione antes de continuar (el sketch DumpInfo de la libreria MFRC522 sirve para esto).

2. **HX711**: Ambos modulos comparten un unico pin de reloj (SCK = pin 24). Cada modulo tiene su pin de datos independiente (DOUT1 = pin 22, DOUT2 = pin 23). Verificar que ambos modulos respondan antes de calibrar.

3. **Motores 28BYJ-48**: Cada motor requiere sus 4 pines de bobina conectados al driver ULN2003. El driver necesita su propia fuente de 5V. Compartir GND entre el driver y el Mega.

4. **Servos**: Alimentar desde la fuente externa, no desde los pines de 5V del Mega (no soportan la corriente). Compartir GND con el Mega.

5. **Sensores IR**: Los 5 sensores usan logica invertida. Se configuran como `INPUT` sin pull-up. Verificar la polaridad: LOW indica presencia, HIGH indica ausencia.

6. **LDR del patio**: Cada LDR forma un divisor de voltaje con una resistencia fija a GND. Se leen directamente con `analogRead()`. No requieren `pinMode` ni pull-up. Cada sensor tiene su propio umbral calibrado (ver `Config.h`, variable `UMBRAL_LDR_OSCURO`).

7. **Paro de emergencia**: Boton momentaneo en pin 18 (INT5). Configurado con `INPUT_PULLUP` y deteccion por flanco descendente (FALLING). Cada pulsacion alterna el estado: detiene o reanuda.

## Pasos de Montaje

### Paso 1: Montar la estructura fisica
Posicionar el riel de la grua, la plataforma de pesaje, y las posiciones del patio sobre la maqueta. Las posiciones del riel son:

- Posicion 0: zona de transferencia (extremo del riel)
- Posicion 1: primera posicion del patio
- Posicion 2: segunda posicion del patio

### Paso 2: Cablear el Arduino Mega
Seguir el diagrama de pines. Prestar atencion a:
- Los pines SPI (50-53) son fijos para el RFID
- Los pines I2C (20-21) son fijos para la LCD
- Timer2 (pines asociados internamente) se usa para el tick base del sistema

### Paso 3: Cablear la alimentacion
- Arduino Mega: alimentar por USB (programacion) o por pin VIN (fuente externa 7-12V)
- Servos, stepper, electroiman: alimentar desde la fuente externa de 5V
- Compartir GND entre TODAS las fuentes (Mega, fuente externa, drivers)

### Paso 4: Verificar comunicacion
Antes de subir el firmware:
1. Verificar SPI con el RFID usando el sketch DumpInfo
2. Verificar que la LCD muestre algun caracter al inicializar
3. Verificar lectura cruda de los HX711 con el comando `CRUDO` de la consola
4. Verificar que los sensores IR respondan (monitor serial, logica invertida)

### Paso 5: Subir el firmware
1. Abrir `PortusFase1_INO/PortusFase1.ino` en el Arduino IDE
2. Seleccionar placa: Arduino Mega or Mega 2560
3. Seleccionar puerto COM correcto
4. Verificar que las librerias esten instaladas (MFRC522, LiquidCrystal_I2C)
5. Editar los UIDs de RFID en `PreloadedData.h` con los valores reales de las tarjetas
6. Ajustar los valores de calibracion en `Weighing.cpp` (FACTOR_CAL, OFFSET_CAL)
7. Ajustar los umbrales LDR del patio en `Config.h` segun el sensor real
8. Subir el sketch

### Paso 6: Calibrar
Seguir el procedimiento descrito en `CALEBRACION.md`. La calibracion incluye:
- Pesaje dinamico (celdas HX711)
- Sensores LDR del patio
- Sensor optico de marca de la grua

## Notas Importantes

- El proyecto ocupa Timer2 como unico timer disponible para el sistema (Servo.h consume Timer1/3/4/5 en el Mega). Esto significa que el pesaje y los pulsos de la grua comparten el mismo tick base de 100 microsegundos.
- La garita y la salida comparten el mismo servo y semaforo (la talanquera fisica es una sola). El firmware gestiona la exclusion mutua con la variable `duenoTalanquera`.
- El sensor LDR de la posicion P1N0 (posicion 1, nivel 0) resulto poco confiable en las pruebas de la maqueta. El firmware ignora ese sensor y confia en el registro por software para ese nivel puntual. Revisar fisicamente el sensor si se necesita confiabilidad en esa posicion.
