# Referencia de Comandos Seriales - PORTUS Fase 1

## Configuracion

- Puerto: Serial (USB)
- Velocidad: 115200 baud
- Formato: texto plano, terminado por newline (`\n`)
- Los comandos no distinguen mayusculas/minusculas (se convierten internamente a mayusculas)
- Buffer maximo de 40 caracteres; los comandos mas largos se descartan

Al conectar el monitor serial, el sistema imprime el encabezado y la lista de comandos disponibles.

## Comandos Disponibles

### AYUDA
Muestra la lista de comandos disponibles con una breve descripcion de cada uno.

**Salida esperada:**
```
Comandos disponibles:
  ESTADO   - resumen de turnos activos
  PATIO    - estado de cada posicion del patio
  GRUA     - estado general de la grua
  REARME   - solicita rearme tras paro de emergencia
  CRUDO    - lectura cruda de las celdas (para calibrar)
  TARA     - re-zera el offset con la plataforma vacia
  CALIBRAR - asistente de calibracion con peso conocido
  PESO     - muestra el peso calibrado actual (verificacion)
  AYUDA    - esta lista
```

### ESTADO
Muestra un resumen de todos los turnos activos en el sistema, incluyendo:
- Cantidad de turnos activos
- Para cada turno: ID, placa del camion, estacion actual, si esta retenido, pesaje inicial y final
- Si el paro de emergencia esta activo, lo indica
- Muestra la ultima causa de error/retencion registrada

**Salida esperada:**
```
Turnos activos: 2
Turno 0 | Camion P001AAA | Estacion 3 | Retenido: NO | PesajeInicial: 0.195 | PesajeFinal: 0.138
Turno 1 | Camion P002BBB | Estacion 5 | Retenido: NO | PesajeInicial: 0.201 | PesajeFinal: 0.000
Ultima causa registrada: Ninguna
```

Los valores de estacion corresponden al enum `Estacion`:
- 1 = ESPERA
- 2 = GARITA
- 3 = PESAJE
- 4 = RAMAL_RETENIDO
- 5 = TRANSFERENCIA
- 6 = SALIDA
- 7 = FINALIZADO

### PATIO
Muestra el estado de cada posicion del patio (2 posiciones):

**Salida esperada:**
```
Posicion 0: estado=OCUPADA niveles=1
Posicion 1: estado=LIBRE niveles=0
```

Estados posibles:
- `LIBRE`: sin contenedores
- `RESERVADA`: se asigno un deposito pendiente
- `OCUPADA`: al menos un contenedor confirmado fisicamente
- `BLOQUEADA`: inconsistencia entre inventario y sensor LDR fisico

### GRUA
Muestra el estado de la grua:

**Salida esperada:**
```
Referenciada: SI
Libre (idle): SI
```

- `Referenciada`: indica si la grua ya ejecuto el referenciado inicial (deteccion de marca optica home). Si es `NO`, la grua se moviera automaticamente hacia la marca de referencia al iniciar.
- `Libre (idle)`: indica si la grua esta sin trabajo asignado. Si es `NO`, hay un trabajo en ejecucion.

### PESO
Muestra el peso actual calibrado de la plataforma. Lee directamente las celdas HX711 y aplica la calibracion (OFFSET_CAL y FACTOR_CAL).

**Salida esperada:**
```
Cruda: -16757 | Calibrada: 0.196 kg
```

Util para verificar que la lectura sea coherente antes de que un camion cruce la plataforma.

### CRUDO
Muestra la lectura cruda de cada celda HX711 por separado y la suma total. No aplica calibracion.

**Salida esperada:**
```
Celda A: 174023  |  Celda B: 174028  |  Suma (usada por el sistema): 348051
```

Util para diagnostico de cableado y calibracion. Si un timeout de 500ms se produce, el sistema reporta error de comunicacion HX711.

### TARA
Re-calibra el offset de la plataforma con la lectura actual (plataforma vacia). Promedia 10 lecturas para reducir ruido.

**Procedimiento:**
1. Asegurarse de que la plataforma este completamente vacia (sin camion ni contenedor)
2. Enviar el comando TARA
3. Esperar la confirmacion

**Salida esperada:**
```
Tarando... asegurate de que la plataforma este VACIA.
Listo. Nuevo offset (temporal, solo dura hasta apagar): 348005
```

El valor es temporal y se pierde al reiniciar el Arduino. Para hacerlo permanente, editar `OFFSET_CAL` en `Weighing.cpp`.

### CALIBRAR
Asistente interactivo de calibracion paso a paso. Guia al operador para establecer el factor de calibracion (FACTOR_CAL) con un peso conocido.

**Procedimiento:**
1. Enviar el comando CALIBRAR
2. El sistema pide que la plataforma este vacia. Responder `PESO` cuando este lista
3. El sistema tar automaticamente y muestra el offset
4. Colocar un peso conocido en la plataforma
5. Ingresar el peso en gramos (ej: 200 para 200 gramos)
6. El sistema calcula y muestra el FACTOR_CAL resultante
7. Copiar los valores mostrados en `Weighing.cpp` (`FACTOR_CAL` y `OFFSET_CAL`) y recompilar

**Salida esperada:**
```
=== ASISTENTE DE CALIBRACION ===
Paso 1: Asegurate de que la plataforma este VACIA
         (sin camion ni contenedor encima)

Escribe PESO cuando la plataforma este vacia...
TARANDO plataforma vacia...
Offset vacio: 348005

Paso 2: Coloca un peso CONOCIDO en la plataforma
         (ejemplo: 200 gramos = 0.2 kg)
         Escribe el peso en gramos (ej: 200)
Leyendo peso...

=== CALIBRACION COMPLETADA ===
Offset (vacio):    348005
Lectura con peso:  331248
Diferencia:        -16757
Peso conocido:     200 gramos
FACTOR_CAL = -85494.9
OFFSET_CAL = 348005

Copia estos valores en Weighing.cpp:
  static float FACTOR_CAL = X.Xf;  // reemplazar X
  static long  OFFSET_CAL = YYY;    // reemplazar Y

Verificacion: deberia leer 0.200 kg
Lectura actual: 0.196 kg
```

El comando CALIBRAR usa esperas bloqueantes (solo durante el asistente) a diferencia del resto del sistema. No ejecutar其他 comandos mientras dura el proceso.

### REARME
Solicita el rearme del sistema despues de un paro de emergencia. Tambien puede rearmarse pulsando fisicamente el boton de paro una segunda vez (rearme automatico).

**Salida esperada:**
```
Rearme completado.
```
o
```
No se pudo rearmar (revisar boton de paro).
```

El rearme fuerza un re-referenciado de la grua, ya que no se asume que el ultimo movimiento termino correctamente antes del paro.

### Comando no reconocido
Si se envia un texto que no coincide con ningun comando:

```
Comando no reconocido. Escriba AYUDA.
```
