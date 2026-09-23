# Manual de Despliegue y Guia de Pruebas - PORTUS Fase 2

Este manual proporciona las instrucciones para instalar, configurar y ejecutar la plataforma PORTUS Fase 2 tanto en la Raspberry Pi 3 como en una maquina de desarrollo, junto con la guia paso a paso para demostrar los 15 escenarios de evaluacion.

---

## 1. Requisitos e Instalacion

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

## 3. Guia Paso a Paso de los 15 Escenarios de Evaluacion

Para la calificacion se recomienda seguir los 4 bloques del guion de demostracion (Seccion 10.5):

### Bloque 1: Cadena Documental y Operacion Base (E01 a E05)
1. **E01 (Manifiesto):** Iniciar sesion como `maersk`. En pestaña *Manifiestos*, presionar `+ Nuevo Manifiesto`. Llenar con contenedor `MSKU1002`, operacion `DEPOSITO`, peso `22500` g, transportista `trans_rapido`. El manifiesto pasa a estado `CREADO`.
2. **E02 (Declaracion y Solicitud):** Iniciar sesion como `agente1`. En pestaña *Declaraciones*, el manifiesto aparece disponible. Presionar `Presentar Declaración` (ingresar numero ej. `DEC-01`, regimen `Importacion definitiva`, descripcion textil y valor). Luego presionar `Solicitar Levante`. Pasa a `LEVANTE_SOLICITADO`.
3. **E03 (Retencion por Autoridad):** Iniciar sesion como `sat1`. En pestaña *Solicitudes de levante*, seleccionar `Evaluar Levante`, presionar `Retener Levante` e ingresar motivo (ej. "Falta factura comercial"). El transportista recibe aviso automatico y en garita el camion no puede ingresar.
4. **E04 (Levante Verde y Cita):** El agente subsana. `sat1` presiona `Evaluar Levante`, selecciona `Canal VERDE` y presiona `Otorgar Levante`. El transportista `trans_rapido` recibe notificacion con canal verde. Desde la mensajeria escribe `/cita MSKU1002` y el sistema le confirma ventana de atencion (ej. 10:15 - 10:30). La cita aparece en la pestaña *Citas* de la terminal.
5. **E05 (Ingreso en Ventana):** El camion llega a garita dentro de ventana. La talanquera abre, se crea el turno `TRN-0001` y el sinoptico refleja el estado en menos de 2 segundos.

### Bloque 2: Excepciones Operativas y Pesaje (E06 a E08)
6. **E06 (Fuera de Ventana):** Un segundo camion se presenta fuera de su horario asignado. El sistema genera automaticamente la retencion `RT04`, asigna la Plaza 1 del parqueo y notifica al transportista.
7. **E07 (Discrepancia de Peso):** Un camion cruza la bascula con peso alterado (ej. 28000 g vs 22000 g declarado, diferencia > 5%). Se genera la retencion `RT01`, la aguja se posiciona hacia el parqueo (`AgujaParqueo`), asigna la Plaza 2 y muestra la evidencia de peso en la bandeja de *Retenciones*.
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

## 4. Ejecucion de Pruebas Automatizadas

Para validar todos los modulos sin intervención manual:
```bash
python -m unittest PortusFase2/tests/test_integration.py
python -m unittest PortusFase2/tests/validate_scenarios.py
```
Ambas suites deben reportar `OK` confirmando el cumplimiento de la totalidad de las reglas del enunciado.
