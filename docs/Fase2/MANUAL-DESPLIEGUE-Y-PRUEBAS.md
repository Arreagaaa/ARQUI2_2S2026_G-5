# Manual de Despliegue y Guia de Pruebas - PORTUS Fase 2

Este manual proporciona las instrucciones para instalar, configurar y ejecutar la plataforma PORTUS Fase 2 tanto en la Raspberry Pi 3 como en una maquina de desarrollo, junto con la guia paso a paso para demostrar los 15 escenarios de evaluacion.

---

## 1. Requisitos e Instalacion

### 1.0 Ejecucion local rapida en Windows

Para desarrollo local con simulador de Arduino se recomienda usar explicitamente Python 3.13 con el lanzador `py`. No usar `python` si apunta a otro interprete, porque puede no tener instaladas las dependencias.

Terminal 1, backend completo con MQTT y controlador simulado:

```cmd
cd D:\2S2026\ARQUI2\LAB\ARQUI2_2S2026_G-5\PortusFase2
py -3.13 -m pip install -r requirements.txt
py -3.13 run_fase2.py --mock
```

La salida esperada debe indicar:

```text
Servidor disponible en: http://localhost:5000
Running on http://127.0.0.1:5000
```

Terminal 2, frontend React en modo desarrollo:

```cmd
cd D:\2S2026\ARQUI2\LAB\ARQUI2_2S2026_G-5\PortusFase2\frontend
pnpm install
pnpm dev
```

Abrir en el navegador:

```text
http://localhost:5173
```

Notas importantes:

| Situacion | Solucion |
|---|---|
| `ModuleNotFoundError: No module named 'paho'` | Se ejecuto con otro Python. Usar `py -3.13 run_fase2.py --mock`. |
| `unrecognized arguments: --moc` | El parametro correcto es `--mock`. |
| El backend corre pero Vite no abre | Revisar que `pnpm dev` siga activo en Terminal 2. |
| La SPA en `localhost:5173` no carga datos | Verificar que Terminal 1 siga activo en `localhost:5000`. |
| Se quiere usar una sola URL | Ejecutar `pnpm build` y abrir `http://localhost:5000`. |

Build de produccion del frontend:

```cmd
cd D:\2S2026\ARQUI2\LAB\ARQUI2_2S2026_G-5\PortusFase2\frontend
pnpm build
```

Despues del build, Flask sirve el dashboard desde:

```text
http://localhost:5000
```

### 1.1 En Raspberry Pi 3 (Raspberry Pi OS / Linux)

1. Conectar el Arduino Mega 2560 al puerto USB de la Raspberry Pi 3.
2. Identificar el puerto serial asignado:
```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
```
(Normalmente `/dev/ttyACM0`).

3. Instalar paquetes del sistema y broker MQTT Mosquitto:
```bash
sudo apt update
sudo apt install -y python3 python3-pip mosquitto mosquitto-clients
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```

4. Instalar librerias de Python requeridas:
```bash
pip3 install Flask paho-mqtt pyserial
```

5. Clonar el repositorio y dar permisos de ejecucion:
```bash
cd ARQUI2_2S2026_G-5
chmod +x PortusFase2/run_fase2.sh
```

6. Iniciar la plataforma:
```bash
./PortusFase2/run_fase2.sh --port /dev/ttyACM0
```

### 1.2 En Entorno de Desarrollo (Windows con o sin Arduino fisico)

Si no se tiene el Arduino Mega conectado fisicamente, se utiliza el modo simulador integrado (`--mock`):

```cmd
PortusFase2\run_fase2.bat --mock
```

La plataforma abrira el puerto web en `http://localhost:5000` (o la IP local de la Raspberry Pi en el puerto 5000).

---

## 2. Credenciales de Prueba Preconfiguradas

| Rol | Usuario | Contraseña | Descripcion |
|---|---|---|---|
| TERMINAL | `operador1` | `terminal123` | Operador general de terminal (acceso a las 8 pestañas) |
| NAVIERA | `maersk` | `maersk123` | Naviera 1 (solo ve y crea sus propios manifiestos) |
| NAVIERA | `msc` | `msc123` | Naviera 2 (aislamiento frente a Naviera 1) |
| AGENTE | `agente1` | `agente123` | Agente aduanero (presenta declaraciones y pide levante) |
| AUTORIDAD | `sat1` | `sat123` | Autoridad aduanera SAT (otorga/retiene levante, canal rojo/verde) |
| TRANSPORTISTA | `trans_rapido` | (Canal) | Transportista 1 (opera por mensajes / vinculacion) |
| TRANSPORTISTA | `trans_global` | (Canal) | Transportista 2 (opera por mensajes / vinculacion) |

---

## 3. Uso De La Plataforma Por Rol

Despues de iniciar sesion, la aplicacion muestra permanentemente el nombre del usuario y su rol en la cabecera. Cada rol ve un conjunto distinto de pestanas. El control real de permisos tambien se aplica en el servidor; no depende solo de ocultar botones.

### 3.1 Rol TERMINAL: `operador1 / terminal123`

Este usuario representa al operador de la terminal. Es el rol principal para la demostracion fisica y para el control remoto de la maqueta.

Pestanas disponibles:

| Pestana | Para que sirve | Acciones principales |
|---|---|---|
| Operacion | Sinoptico en vivo de la maqueta. Muestra garita, talanquera, pesaje, aguja, parqueo, transferencia, grua, patio, salida, enlace y modo. | Suspender grua, reanudar grua, referenciar grua, abrir/cerrar talanquera, abrir puerta de salida, liberar parqueo, activar modo mantenimiento. |
| Turnos | Consulta operaciones activas e historicas. | Filtrar, buscar por contenedor o vehiculo, ver linea de tiempo, retener manualmente, anular turno. |
| Retenciones | Bandeja de retenciones operativas y aduaneras visibles para terminal. | Aclarar, corregir peso cuando aplique, rechazar cuando el rol facultado sea TERMINAL. |
| Patio | Inventario y estado de posiciones del patio. | Bloquear posicion, liberar posicion, ver permanencia y remociones. |
| Grua | Estado, cola e historial de la grua. | Ver ciclos, fallas, tiempos de ciclo, exportar historial. |
| Alarmas | Alarmas activas e historicas AL01-AL14. | Reconocer alarma individual, reconocer todas las bajas/medias, filtrar por severidad. |
| Citas | Agenda diaria en franjas de 15 minutos. | Cancelar cita, reprogramar cita, bloquear franja, desbloquear franja, ver cumplimiento de ventana. |
| Reportes | Calculo de metricas de corrida. | Generar reporte, ver 8 metricas, exportar CSV. |

Flujo recomendado para probar TERMINAL:

1. Entrar a `Operacion` y verificar `ENLACE CONECTADO`.
2. Probar botones de grua en modo mock: `Suspender grua`, `Reanudar grua`, `Referenciar`.
3. Entrar a `Alarmas` y verificar que se puedan reconocer alarmas.
4. Entrar a `Citas` y probar bloqueo/desbloqueo de una franja.
5. Entrar a `Reportes` y generar metricas.

### 3.2 Rol NAVIERA: `maersk / maersk123` y `msc / msc123`

Este rol declara manifiestos y consulta sus propios contenedores. Hay dos navieras para demostrar aislamiento de datos.

Pestanas disponibles:

| Pestana | Para que sirve | Acciones principales |
|---|---|---|
| Manifiestos | Lista manifiestos declarados por la naviera en sesion. | Crear nuevo manifiesto, ver detalle, ver historial de peso, anular manifiesto sin turno asociado. |
| Mis contenedores | Consulta solo contenedores propios. | Buscar por contenedor, filtrar por estado. No tiene acciones fisicas. |

Campos obligatorios al crear manifiesto:

| Campo | Ejemplo |
|---|---|
| Contenedor | `MSKU1002` |
| Tipo de operacion | `DEPOSITO` o `RETIRO` |
| Peso declarado | `22500` gramos |
| Tolerancia | opcional, por defecto 5% |
| Transportista asignado | `trans_rapido` o `trans_global` |
| Observaciones | opcional |

Reglas importantes:

1. `maersk` no puede ver ni modificar manifiestos de `msc`.
2. `msc` no puede ver ni modificar manifiestos de `maersk`.
3. Un contenedor no puede tener dos manifiestos activos al mismo tiempo.
4. NAVIERA no puede emitir comandos remotos ni resolver retenciones.

### 3.3 Rol AGENTE: `agente1 / agente123`

Este rol completa la parte documental aduanera despues de que una naviera declara un manifiesto.

Pestanas disponibles:

| Pestana | Para que sirve | Acciones principales |
|---|---|---|
| Declaraciones | Muestra manifiestos que aun necesitan declaracion o levante. | Presentar declaracion, solicitar levante, adjuntar observacion documental si aplica. |
| Seguimiento | Consulta solicitudes presentadas por el agente. | Filtrar por estado, buscar por numero de declaracion. No tiene acciones fisicas. |

Campos obligatorios de declaracion:

| Campo | Ejemplo |
|---|---|
| Numero de declaracion | `DEC-001` |
| Regimen | `Importacion definitiva` o `Deposito temporal` |
| Descripcion de mercancia | minimo 10 caracteres |
| Valor declarado | mayor que cero |

Reglas importantes:

1. AGENTE puede ver manifiestos completos para gestionar documentacion.
2. AGENTE no puede otorgar levante.
3. AGENTE no puede emitir comandos remotos.
4. AGENTE no puede resolver retenciones.

### 3.4 Rol AUTORIDAD: `sat1 / sat123`

Este rol representa a la autoridad aduanera. Decide si otorga o retiene levante y asigna canal verde o rojo.

Pestanas disponibles:

| Pestana | Para que sirve | Acciones principales |
|---|---|---|
| Solicitudes de levante | Bandeja de solicitudes pendientes. | Ver declaracion, otorgar levante, seleccionar canal verde/rojo, retener con motivo. |
| Retenciones aduaneras | Retenciones de origen aduanero: `RT03` canal rojo y `RT05` documental. | Aclarar o rechazar. Rechazar exige motivo. |
| Consulta de carga | Consulta transversal de carga de cualquier naviera. | Buscar por contenedor, naviera o estado de autorizacion. No tiene acciones fisicas. |

Reglas importantes:

1. Si otorga levante con canal `VERDE`, el transportista puede solicitar cita y el camion sigue flujo normal.
2. Si otorga levante con canal `ROJO`, el camion puede ingresar pero sera retenido despues del pesaje de entrada con `RT03`.
3. Si retiene levante, la talanquera no debe abrir para ese manifiesto.
4. AUTORIDAD puede resolver retenciones aduaneras, pero no puede corregir peso.

### 3.5 Rol TRANSPORTISTA: canal de mensajeria

El transportista no entra al dashboard web. Opera por canal de mensajeria usando una cuenta vinculada por codigo generado por TERMINAL.

Transportistas semilla:

| Transportista | Uso |
|---|---|
| `trans_rapido` | Transportista 1 para demostrar citas y aislamiento. |
| `trans_global` | Transportista 2 para demostrar que no ve carga ajena. |

Comandos obligatorios:

| Comando | Funcion |
|---|---|
| `/inicio` | Presenta el servicio y lista comandos. |
| `/vincular CODIGO` | Vincula la cuenta de mensajeria al transportista. |
| `/cita` | Paso 1: lista los contenedores con levante otorgado pendientes de cita. |
| `/cita CONTENEDOR` | Paso 2: ofrece las proximas franjas con capacidad disponible. |
| Hora elegida (ej. `10:15`) o `/cita CONTENEDOR 10:15` | Paso 3: confirma la cita y envia el aviso obligatorio. |
| `/miscitas` | Lista citas vigentes e historicas. |
| `/estado CONTENEDOR` | Consulta estado de una carga propia. |
| `/misturnos` | Lista turnos activos del transportista. |
| `/ayuda` | Repite lista de comandos. |

#### Vinculacion desde la interfaz web

1. Iniciar sesion como `operador1` (rol TERMINAL) e entrar a la pestana *Citas*.
2. En el panel **Vinculacion de transportista**, elegir el transportista y presionar `Generar codigo`.
3. El codigo de 6 caracteres aparece en pantalla (vigencia 60 minutos) y el estado del transportista cambia a `Vinculado` cuando el chat ya amarro su cuenta.
4. El transportista envia `/vincular CODIGO` desde Telegram (o desde el simulador) y el servicio responde `Vinculacion exitosa`.

#### Bot de Telegram (demostracion desde el telefono)

1. Converse con `@BotFather` en Telegram, ejecute `/newbot`, elija nombre y usuario y copie el token.
2. Pegue el token en `PortusFase2/.env` como `TELEGRAM_BOT_TOKEN=<token>`.
3. Reinicie `run_fase2.py`: el arranque imprime `Bot de Telegram activo (long polling)`.
4. Busque su bot en Telegram, envie `/start` y opere con los comandos de la tabla.

Mientras `TELEGRAM_BOT_TOKEN` este vacio el sistema opera igual: los avisos se encolan y se registran en el log con el prefijo `[SIN TELEGRAM]` (o `[SIN CANAL]` si el transportista no tiene cuenta vinculada). Ninguna peticion HTTP ni el hilo de telemetria esperan a Telegram.

Endpoint local para simular mensajes mientras no se conecte Telegram:

```http
POST http://localhost:5000/api/mensajeria/simulador
```

Payload de ejemplo:

```json
{
  "chat_id": "telefono_prueba_1",
  "texto": "/inicio"
}
```

Reglas importantes:

1. Un transportista no puede consultar contenedores que no le pertenecen.
2. Un usuario no vinculado recibe siempre solicitud de vinculacion.
3. Un codigo de vinculacion vence a los 60 minutos y solo se usa una vez.
4. Una franja admite dos citas; una franja bloqueada nunca se ofrece al transportista.
5. Todo texto sin barra que no sea la eleccion de franja pendiente se responde con
   `Comando ... no reconocido` mas la indicacion de `/ayuda`.
6. Las 9 notificaciones automaticas se encolan en `PortusFase2/mensajeria/notifier.py`
   y se entregan en un hilo propio: levante otorgado, levante retenido, cita asignada,
   recordatorio de cita (1 hora antes), vehiculo retenido (RT01-RT06), retencion
   resuelta, cita cancelada/reprogramada, turno cerrado y turno anulado.

---

## 4. Guia Paso a Paso de los 15 Escenarios de Evaluacion

Para la calificacion se recomienda seguir los 4 bloques del guion de demostracion (Seccion 10.5):

### Bloque 1: Cadena Documental y Operacion Base (E01 a E05)
1. **E01 (Manifiesto):** Iniciar sesion como `maersk`. En pestaña *Manifiestos*, presionar `+ Nuevo Manifiesto`. Llenar con contenedor `MSKU1002`, operacion `DEPOSITO`, peso `22500` g, transportista `trans_rapido`. El manifiesto pasa a estado `CREADO`.
2. **E02 (Declaracion y Solicitud):** Iniciar sesion como `agente1`. En pestaña *Declaraciones*, el manifiesto aparece disponible. Presionar `Presentar Declaración` (ingresar numero ej. `DEC-01`, regimen `Importacion definitiva`, descripcion textil y valor). Luego presionar `Solicitar Levante`. Pasa a `LEVANTE_SOLICITADO`.
3. **E03 (Retencion por Autoridad):** Iniciar sesion como `sat1`. En pestaña *Solicitudes de levante*, seleccionar `Evaluar Levante`, presionar `Retener Levante` e ingresar motivo (ej. "Falta factura comercial"). El transportista recibe aviso automatico y en garita el camion no puede ingresar.
4. **E04 (Levante Verde y Cita):** El agente subsana. `sat1` presiona `Evaluar Levante`, selecciona `Canal VERDE` y presiona `Otorgar Levante`. El transportista `trans_rapido` recibe notificacion con canal verde. Desde la mensajeria escribe `/cita MSKU1002` y el sistema le ofrece las proximas franjas con capacidad; al responder con la hora elegida (ej. `10:15`) confirma la ventana de atencion (ej. 10:15 - 10:30). La cita aparece en la pestaña *Citas* de la terminal.
5. **E05 (Ingreso en Ventana):** El camion llega a garita dentro de ventana. La talanquera abre, se crea el turno `TRN-0001` y el sinoptico refleja el estado en menos de 2 segundos.

### Bloque 2: Excepciones Operativas y Pesaje (E06 a E08)
6. **E06 (Fuera de Ventana):** Un segundo camion se presenta fuera de su horario asignado. El sistema genera automaticamente la retencion `RT04`, asigna la Plaza 1 del parqueo y notifica al transportista.
7. **E07 (Discrepancia de Peso):** Un camion cruza la bascula con peso alterado (ej. 28000 g vs 22000 g declarado, diferencia > 5%). El servidor compara el `PesajeLectura` con el peso declarado del manifiesto y su tolerancia (5% por defecto): genera la alarma `AL09`, la retencion `RT01` (o `RT02` si ocurre en la salida), posiciona la aguja hacia el parqueo (`AgujaParqueo`), asigna plaza y muestra la evidencia de peso (declarado, medido, diferencia absoluta y porcentual) en la bandeja de *Retenciones*. El transportista recibe el aviso con esos mismos datos.

   > Nota de la maqueta: la bascula fisica pesa en la escala del modelo (por ejemplo 1160 g), mientras que un manifiesto puede declarar tonelaje de terminal (por ejemplo 22000 g). Si el orden de magnitud del valor declarado y el medido difiere mas de 10 veces, el servidor no genera la retencion automatica y deja la advertencia `fuera de escala comparable` en el log: la retencion queda bajo criterio manual con `RT06`. Para demostrar E07 declare en el manifiesto el peso real de la maqueta y altere ese peso fisicamente.
8. **E08 (Resolucion Corregir):** El operador de terminal (`operador1`) entra a la pestaña *Retenciones*. En la retencion RT01 presiona `Resolver` -> `Corregir Peso`. El manifiesto se actualiza con el peso medido, guarda el valor previo en su historial, la aguja libera la plaza (`AgujaLiberar`) y el vehiculo continúa su turno.

### Bloque 3: Control Aduanero y Seguridad de Acceso (E09 a E12)
9. **E09 (Canal Rojo):** `sat1` otorga levante con `Canal ROJO` a un camion. Al pasar el pesaje de entrada, el camion es desviado al parqueo con retencion `RT03`. Si `operador1` intenta resolverla, el sistema lo rechaza; unicamente `sat1` puede resolverla.
10. **E10 (Resolucion Rechazar):** `sat1` entra a *Retenciones aduaneras*, presiona `Rechazar` e ingresa el motivo obligatorio ("Carga no declarada detectada"). La plaza se libera, el turno pasa a `Anulado`, el camion sale sin operar y el transportista recibe el aviso con el motivo.
11. **E11 (Parqueo Lleno):** Con las 3 plazas ocupadas, un cuarto camion con canal rojo o fuera de ventana intenta entrar. La garita rechaza el ingreso indicando parqueo lleno y el sistema genera la alarma `AL11`.
12. **E12 (Permisos y Aislamiento):** 
    - `maersk` intenta consultar manifiestos de `msc`: el servidor solo muestra los propios.
    - `maersk` intenta enviar un comando remoto: el servidor devuelve HTTP 403 Permiso insuficiente.
    - Transportista escribe `/estado CONTENEDOR_AJENO`: el servicio responde "No tiene carga asociada a ese identificador".

### Bloque 4: Control de Grua, Tolerancia a Fallos y Reportes (E13 a E15)
13. **E13 (Suspender y Reanudar Grua):** Con un trabajo en curso, `operador1` presiona `Suspender Grúa`. La grua termina el ciclo en ejecucion y no toma trabajos nuevos. Luego presiona `Reanudar Grúa` y la cola continúa normalmente.
14. **E14 (Desconexion del Servidor):** Durante un traslado de grua, se desconecta el cable USB del servidor. La maqueta física concluye el movimiento con seguridad y rechaza ingresos en modo degradado. Tras 15 segundos el servidor detecta enlace perdido y genera la alarma critica `AL01`. Al reconectar el cable, el enlace se restablece y el operador reconoce `AL01`.
15. **E15 (Retiro, Remocion y Reporte):** Se solicita el retiro de un contenedor ubicado en nivel 0 que tiene otro encima. La grua ejecuta la remocion a otra celda, actualiza el contador de remociones y entrega la carga. En la pestaña *Reportes*, el operador ingresa la etiqueta de corrida, presiona `Calcular Métricas` (se calculan las 8 metricas) y descarga el reporte en formato CSV.

---

## 5. Ejecucion de Pruebas Automatizadas

Para validar todos los modulos sin intervención manual:
```bash
cd D:\2S2026\ARQUI2\LAB\ARQUI2_2S2026_G-5\PortusFase2
py -3.13 -m unittest discover -s tests -v
py -3.13 tests\validate_scenarios.py -v
```
Ambas suites deben reportar `OK` confirmando el cumplimiento de la totalidad de las reglas del enunciado.

> Estado observado el 2026-09-29: `validate_scenarios.py` reporta `OK` (12 pruebas).
> En `unittest discover` quedan 5 pruebas en rojo de `test_api_gaps`
> (`test_01` a `test_04` y `test_11`), **preexistentes y ajenas al canal de
> mensajeria**: el guard de `protect_operational_data` en `server/app.py:333`
> devuelve HTTP 409 `Fase1 opera localmente` para `POST /api/turnos` y
> `POST /api/retenciones/<id>/resolver` mientras `terminal_state['protocolo']`
> sea `fase1`. Verificado contra el arbol limpio (sin cambios de la sesion de
> mensajeria).

Prueba de navegador con Playwright:

```cmd
cd D:\2S2026\ARQUI2\LAB\ARQUI2_2S2026_G-5\PortusFase2\frontend
pnpm exec playwright test tests/playwright_smoke.spec.js --browser=chromium --reporter=line
```

Si Playwright indica que falta Chromium:

```cmd
pnpm exec playwright install chromium
```
