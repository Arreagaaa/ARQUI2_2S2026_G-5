# Procedimiento de Calibracion - PORTUS Fase 1

Este documento describe los procesos de calibracion necesarios para el correcto funcionamiento de la maqueta. Deben completarse antes de la operacion normal del sistema.

## 1. Calibracion del Pesaje Dinamico (HX711)

### Requisitos
- Arduino Mega con firmware subido y funcionando
- Monitor serial abierto a 115200 baud
- Un peso conocido (peso patron). Ejemplo: un objeto de 200 gramos medido con precision
- La plataforma de pesaje debe estar libre de vibraciones

### Procedimiento automatico (comando CALIBRAR)

1. Asegurarse de que la plataforma este completamente vacia (sin camiones, contenedores, ni residuos)
2. Enviar el comando `CALIBRAR` por el monitor serial
3. Cuando el sistema pida confirmacion, escribir `PESO` y enviar
4. El sistema ejecutara la taracion automatica (promedia 10 lecturas)
5. Colocar el peso conocido sobre la plataforma, centrado entre ambas celdas
6. Ingresar el peso en gramos (ej: 200) y enviar
7. El sistema calcula el factor de calibracion y muestra los valores resultantes
8. Copiar los valores de `FACTOR_CAL` y `OFFSET_CAL` en el archivo `Weighing.cpp`
9. Recompilar y subir el firmware

### Procedimiento manual

Si el asistente automatico no funciona o se prefiere calibrar manualmente:

**Paso 1: Obtener el offset (plataforma vacia)**
1. Enviar el comando `TARA` con la plataforma vacia
2. Anotar el valor de offset retornado

**Paso 2: Obtener la lectura cruda con peso conocido**
1. Enviar `CRUDO` con el peso conocido sobre la plataforma
2. Anotar el valor de "Suma (usada por el sistema)"

**Paso 3: Calcular el factor**
```
FACTOR_CAL = (lectura_cruda - offset) / peso_en_kg
```
Ejemplo: si el offset es 348005, la lectura con 200g es 331248:
```
FACTOR_CAL = (331248 - 348005) / 0.2 = -16757 / 0.2 = -85494.9
```

**Paso 4: Editar el firmware**
En `Weighing.cpp`, modificar las variables:
```cpp
static float FACTOR_CAL = -85494.9f;  // su valor calculado
static long  OFFSET_CAL = 348005;     // el offset obtenido en Paso 1
```

### Verificacion
Despues de calibrar, enviar `PESO` con el peso conocido sobre la plataforma. El valor mostrado debe ser cercano al peso real (dentro de +/- 5 gramos para pesos sobre 100g).

### Notas
- El valor de OFFSET_CAL es temporal si se cambio con el comando TARA (se pierde al apagar). Solo el valor hardcodeado en `Weighing.cpp` persiste entre reinicios.
- Si se reconecta la celda B (segundo HX711), el offset puede cambiar. Repetir la calibracion.
- El umbral de estabilidad (`UMBRAL_ESTABILIDAD_CUENTAS` en `Weighing.cpp`, valor por defecto 800) puede necesitar ajuste si el pesaje es inestable. Aumentar si hay falsos positivos de meseta; disminuir si no detecta meseta.
- La tolerancia de peso para desviar camiones se define en `Config.h` (`TOLERANCIA_PESO_KG`, por defecto 5.0 kg).

## 2. Calibracion de Sensores LDR del Patio

### Concepto
Cada posicion del patio tiene 2 niveles, y cada nivel tiene un sensor LDR. Los LDR son sensores analogicos cuya lectura varia segun la cantidad de luz que reciben. Cuando un contenedor cubre un LDR, la lectura disminuye. El sistema compara la lectura contra un umbral para determinar si el sensor esta "tapado" (contenedor encima) o "destapado".

### Valores de referencia (maqueta de prueba)

| Posicion | Nivel | Vacio | Ocupado | Umbral | Observacion |
|---|---|---|---|---|---|
| P0 | N0 | 818 | 273 | 545 | Funcional |
| P0 | N1 | 509 | 204 | 356 | Funcional |
| P1 | N0 | 190 | 202 | 150 | Poco confiable |
| P1 | N1 | 382 | 210 | 295 | Funcional |

### Procedimiento
1. Colocar un contenedor sobre el nivel a calibrar (o dejarlo vacio)
2. Enviar el comando `CRUDO` para verificar comunicacion con las celdas (no relacionado directamente con LDR, pero confirma que el sistema responde)
3. Leer el valor analogico del LDR. Si el debug del patio esta activado (`YARD_LDR_DEBUG_PRINT` en `Yard.cpp`), las lecturas se imprimen cada 5 segundos
4. Alternativamente, usar un sketch aparte que lea `analogRead()` en los pines A8-A11
5. Tomar nota del valor con el sensor vacio y con el sensor cubierto
6. Calcular el umbral como el punto medio entre ambos valores
7. Editar `UMBRAL_LDR_OSCURO` en `Config.h`

### Problema conocido: P1N0
El sensor en posicion 1, nivel 0 (pin A10) presenta una anomalia: la lectura con contenedor encima (202) es Practicamente igual o mayor que la lectura en vacio (190). Esto impide distinguir entre tapado y destapado por software. El firmware ignora este sensor y confia en el registro por software para ese nivel puntual.

Causas posibles:
- Luz ambiental entrando por un costado de la maqueta
- LDR mal orientado o desalineado
- Contenedor no cubre bien el sensor en esa posicion

Si se necesita confiabilidad en P1N0, revisar fisicamente el sensor y corregir el montaje antes de intentar un ajuste de umbral.

## 3. Calibracion del Sensor Optico de Marca (Grua)

### Concepto
La grua usa un sensor analogico para detectar marcas de posicion sobre el riel. El firmware detecta una marca cuando la lectura supera un umbral fijo de 512 (en `Crane.cpp`, dentro de `crane_timerTick()`).

### Procedimiento
1. Al iniciar el sistema, el firmware imprime el valor del sensor en reposo: `[GRUA] Marca optica en reposo (analogRead): XXXX`
2. Si este valor es cercano o superior a 512, la grua detectara marcas falsas
3. Si el valor es bajo (menor a 200), el umbral de 512 es adecuado
4. Si es necesario ajustar, modificar la comparacion en `crane_timerTick()`:
   ```cpp
   bool marcaAhora = (analogRead(PIN_MARCA_OPTICA) > UMBRAL_AJUSTADO);
   ```

### Verificacion
Al reiniciar el sistema, la grua debe ejecutar el referenciado automatico: se mueve hacia el extremo del riel (posicion 0) hasta detectar la primera marca optica. Si se detiene inmediatamente sin moverse, el umbral es demasiado bajo o el sensor esta demasiado cerca de una marca permanente.

## 4. Calibracion de los Sensores IR

### Concepto
Los 5 sensores infrarrojos de presencia usan logica invertida: LOW indica presencia, HIGH indica ausencia. No requieren calibracion de valores analogicos, pero si verificacion de la polaridad correcta.

### Verificacion
Para cada sensor, pasar un objeto (o el camion miniatura) frente al sensor y verificar que el LED del sensor cambie de estado. En el monitor serial, los sensores se leen con `digitalRead()`: el valor debe cambiar de HIGH a LOW cuando se detecta presencia.

### Sensibilidad
Si un sensor es demasiado sensible (detecta presencia cuando no la hay) o poco sensible (no detecta el camion), ajustar la posicion fisica del sensor o la distancia al punto de deteccion. No hay ajuste por software para esto.

## 5. Verificacion del Paro de Emergencia

### Procedimiento
1. Presionar el boton de paro una vez: el sistema debe detener la grua inmediatamente y energizar el electroiman (prevenir caida de carga)
2. Verificar en el serial que se imprima el estado de paro
3. Presionar el boton nuevamente: el sistema debe reanudar automaticamente y re-referenciar la grua
4. Verificar en el serial que se imprima el mensaje de reanudacion

### Nota sobre debounce
El sistema ignora pulsaciones dentro de los 250ms posteriores a una pulsacion valida (debounce). Si el boton genera rebote electrico, es posible que una sola pulsacion fisica no registre. En ese caso, incrementar `DEBOUNCE_MS` en `Safety.cpp`.
