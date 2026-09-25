// Pestaña Operación: sinóptico en vivo alimentado por suscripción SSE.
// Refrescos de datos lógicos del servidor (retenciones, patio, turnos) se
// disparan por la llegada de eventos del stream, nunca por timer de polling.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  DoorOpen,
  DoorClosed,
  Construction,
  CircleSlash,
  Pause,
  Play,
  Crosshair,
  Wrench,
  Unlock,
  Lock,
  Truck,
  Boxes,
  Radio,
} from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../hooks/useAuth'
import {
  comandoRemoto,
  listPatio,
  listRetenciones,
  listTurnos,
  bloquearPosicion,
  liberarPosicion,
  crearTurno,
  listManifiestos,
} from '../../api/endpoints'
import type { CeldaPatio, EstadoTerminal, EventoSSE, Retencion, Turno } from '../../types'
import { Panel, StatusBadge, MonoId, Spinner, Modal, LiveIndicator } from '../../components/ui'
import {
  colorGarita,
  colorPuerta,
  colorAguja,
  colorPesaje,
  colorTurno,
  ETIQUETAS_ESTADO_TURNO,
} from '../../utils/status'
import { fmtFechaHora, fmtKg } from '../../utils/format'
import type { SinopticoStream } from '../../hooks/useSinopticoStream'

// Topics cuya llegada indica un cambio logico en servidor que afecta al
// parqueo / patio / turnos y justifica recargar esa lista.
const TOPICS_RECARGA = new Set([
  'portus/evt/garita',
  'portus/evt/pesaje',
  'portus/evt/aguja',
  'portus/evt/patio',
  'portus/evt/salida',
  'portus/cmd/respuesta',
  'portus/init',
])

function Estacion({
  titulo,
  children,
  className = '',
  onClick,
  activo,
}: {
  titulo: string
  children: React.ReactNode
  className?: string
  onClick?: () => void
  activo?: boolean
}) {
  return (
    <div
      onClick={onClick}
      className={`bg-surface2 border rounded p-2.5 min-w-0 ${
        activo ? 'border-accent/60' : 'border-line'
      } ${onClick ? 'cursor-pointer hover:border-line2' : ''} ${className}`}
    >
      <div className="text-2xs uppercase tracking-wider text-inkfaint font-medium mb-1.5">{titulo}</div>
      {children}
    </div>
  )
}

function Flecha({ rotado = false }: { rotado?: boolean }) {
  return (
    <div className={`flex items-center justify-center text-inkfaint shrink-0 ${rotado ? 'rotate-90' : ''}`}>
      <svg width="28" height="10" viewBox="0 0 28 10" fill="none" aria-hidden="true">
        <path d="M0 5h22m0 0-4-4m4 4-4 4" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </div>
  )
}

function Dato({ etiqueta, valor, color }: { etiqueta: string; valor: React.ReactNode; color?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="text-inkfaint">{etiqueta}</span>
      <span className={`font-medium ${color || 'text-ink'}`}>{valor}</span>
    </div>
  )
}

export default function OperacionPage() {
  const { stream } = useOutletContext<{ stream: SinopticoStream }>()
  const estado: EstadoTerminal = stream.estado
  const { push } = useToast()
  const { user } = useAuth()

  const [confirmacion, setConfirmacion] = useState<null | { titulo: string; mensaje: string; comando: string; parametros?: Record<string, unknown> }>(null)
  const [plazaLiberar, setPlazaLiberar] = useState<number>(1)
  const [turnoDetalle, setTurnoDetalle] = useState<Turno | null>(null)
  const [celdaDetalle, setCeldaDetalle] = useState<CeldaPatio | null>(null)
  const [esperandoCmd, setEsperandoCmd] = useState(false)
  const ultimoTopicRef = useRef<string | null>(null)

  const retencionesQ = useApi(() => listRetenciones({ estado: 'ABIERTA' }), [])
  const patioQ = useApi(() => listPatio(), [])
  const turnosQ = useApi(() => listTurnos(), [])
  const manifiestosQ = useApi(() => listManifiestos(), [])

  const [modalIngreso, setModalIngreso] = useState(false)
  const [placaIngreso, setPlacaIngreso] = useState('')
  const [manifiestoIngreso, setManifiestoIngreso] = useState('')
  const [creandoTurno, setCreandoTurno] = useState(false)

  const recargarLogicos = useCallback(() => {
    retencionesQ.reload()
    turnosQ.reload()
  }, [retencionesQ, turnosQ])

  // Recarga por llegada de eventos relevantes (suscripcion, no polling).
  const topicActual = stream.ultimoEvento?.topic ?? null
  useEffect(() => {
    if (topicActual && topicActual !== ultimoTopicRef.current) {
      ultimoTopicRef.current = topicActual
      if (TOPICS_RECARGA.has(topicActual)) {
        recargarLogicos()
        if (topicActual === 'portus/evt/patio') patioQ.reload()
      }
    }
  }, [topicActual, recargarLogicos, patioQ])

  // Respuesta async del controlador a un comando remoto (ACK / NAK + causa).
  const evt = stream.ultimoEvento
  useEffect(() => {
    if (evt?.topic === 'portus/cmd/respuesta' && evt.data) {
      const datos = evt.data.datos || {}
      const resultado = String(datos['resultado'] || '')
      const comando = String(datos['comando'] || evt.data.comando || '')
      const error = datos['error']
      if (resultado === 'ACK') push('exito', `Comando ${comando} aceptado por el controlador.`)
      else if (resultado === 'NAK') push('error', `Comando ${comando} rechazado: ${String(error || 'condicion de seguridad no cumplida')}`)
      setEsperandoCmd(false)
    }
  }, [evt, push])

  const enviarComando = async (comando: string, parametros: Record<string, unknown> = {}) => {
    setEsperandoCmd(true)
    try {
      const res = await comandoRemoto(comando, parametros)
      push('info', res.message)
      // Si en ~4s no llega respuesta SSE, se libera el indicador igual.
      setTimeout(() => setEsperandoCmd(false), 4000)
    } catch (err) {
      setEsperandoCmd(false)
      push('error', err instanceof Error ? err.message : 'No se pudo despachar el comando')
    }
  }

  const confirmar = (titulo: string, mensaje: string, comando: string, parametros?: Record<string, unknown>) =>
    setConfirmacion({ titulo, mensaje, comando, parametros })

  // Ocupacion real de plazas: retenciones abiertas (el campo parqueo del estado
  // SSE del backend se mantiene estatico, la fuente logica es retention_manager).
  const plazasOcupadas = useMemo(() => {
    const mapa: Record<number, Retencion | undefined> = { 1: undefined, 2: undefined, 3: undefined }
    for (const r of retencionesQ.data || []) mapa[r.plaza_numero] = r
    return mapa
  }, [retencionesQ.data])

  const turnosActivos = useMemo(
    () => (turnosQ.data || []).filter((t) => t.estado_actual !== 'Cerrado' && t.estado_actual !== 'Anulado'),
    [turnosQ.data],
  )

  const enlaceOk = stream.conectado && estado.enlace === 'CONECTADO'
  const ultimoLatido = estado.ultimo_latido_timestamp ? fmtFechaHora(estado.ultimo_latido_timestamp) : '-'

  const modoMantenimiento = estado.modo === 'MANTENIMIENTO' || estado.modo === 'Mantenimiento'
  const grua = estado.grua

  const bloquesPatio = useMemo(() => {
    const celdas = patioQ.data || []
    const posiciones = Array.from(new Set(celdas.map((c) => c.posicion))).sort((a, b) => a - b)
    return posiciones.map((p) => ({
      posicion: p,
      niveles: celdas.filter((c) => c.posicion === p).sort((a, b) => b.nivel - a.nivel),
    }))
  }, [patioQ.data])

  return (
    <div className="space-y-4">
      {/* Barra de estado del enlace y modo */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <LiveIndicator conectado={enlaceOk} ultimoMensajeEn={stream.ultimoMensajeEn} etiqueta="Enlace con controlador" />
        <StatusBadge color={enlaceOk ? 'ok' : 'danger'}>
          {enlaceOk ? 'ENLACE CONECTADO' : 'ENLACE DESCONECTADO - datos del ultimo estado conocido'}
        </StatusBadge>
        <StatusBadge color={modoMantenimiento ? 'warn' : 'accent'}>
          MODO: {estado.modo}
        </StatusBadge>
        <span className="text-2xs text-inkfaint font-mono">Ultimo latido: {ultimoLatido}</span>
        {esperandoCmd && (
          <span className="flex items-center gap-1.5 text-2xs text-accent">
            <Spinner size={12} /> Esperando respuesta del controlador...
          </span>
        )}
      </div>

      {!enlaceOk && (
        <div className="border border-warn/40 bg-warn-soft text-warn text-xs rounded px-3 py-2">
          El enlace con el controlador esta caido. El sinoptico muestra el ultimo estado conocido con marca de
          tiempo {ultimoLatido} y no debe interpretarse como estado actual.
        </div>
      )}

      {/* Sinoptico */}
      <Panel
        title="Sinoptico de la terminal"
        subtitle="Actualizacion por suscripcion SSE - latencia objetivo menor a 2 segundos"
        actions={
          <span className="text-2xs text-inkfaint hidden sm:block">
            Espera: <span className="font-mono text-ink">{estado.zona_espera.cantidad_vehiculos}</span> veh.
          </span>
        }
        bodyClassName="p-3 sm:p-4 space-y-4"
      >
        {/* Flujo principal */}
        <div className="flex flex-col lg:flex-row lg:items-stretch gap-2">
          {/* Zona de espera */}
          <Estacion titulo="Zona de espera" className="lg:w-36">
            <div className="flex items-center gap-2">
              <Truck size={16} className="text-inkdim" />
              <span className="text-xl font-semibold font-mono text-ink">
                {estado.zona_espera.cantidad_vehiculos}
              </span>
            </div>
            <div className="text-2xs text-inkfaint mt-1">vehiculos en cola</div>
          </Estacion>

          <Flecha />

          {/* Garita */}
          <Estacion
            titulo="Garita"
            className="lg:w-44"
            activo={estado.garita.vehiculo != null}
            onClick={() => {
              if (turnosActivos.length > 0) setTurnoDetalle(turnosActivos[0])
              else {
                if (estado.garita.vehiculo) setPlacaIngreso(estado.garita.vehiculo)
                setModalIngreso(true)
              }
            }}
          >
            <StatusBadge color={colorGarita(estado.garita.estado)}>{estado.garita.estado}</StatusBadge>
            <div className="mt-1.5">
              <Dato
                etiqueta="Vehiculo"
                valor={estado.garita.vehiculo ? <MonoId>{estado.garita.vehiculo}</MonoId> : 'ninguno'}
              />
            </div>
            <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-line text-2xs">
              {estado.talanquera.toLowerCase().includes('abiert') ? (
                <DoorOpen size={13} className="text-ok" />
              ) : estado.talanquera.toLowerCase().includes('movim') ? (
                <Construction size={13} className="text-warn" />
              ) : (
                <DoorClosed size={13} className="text-inkdim" />
              )}
              <span className="text-inkfaint">Talanquera:</span>
              <StatusBadge color={colorPuerta(estado.talanquera)}>{estado.talanquera}</StatusBadge>
            </div>
          </Estacion>

          <Flecha />

          {/* Pesaje */}
          <Estacion titulo="Plataforma de pesaje" className="lg:w-48">
            <StatusBadge color={colorPesaje(estado.pesaje.estado)}>{estado.pesaje.estado}</StatusBadge>
            <div className="mt-1.5 space-y-1">
              <Dato etiqueta="Ultimo valor" valor={<span className="font-mono">{fmtKg(estado.pesaje.ultimo_valor_kg)}</span>} />
              <Dato etiqueta="Comparacion" valor={estado.pesaje.resultado} />
            </div>
          </Estacion>

          <Flecha />

          {/* Aguja */}
          <Estacion titulo="Aguja desviadora" className="lg:w-44">
            <StatusBadge color={colorAguja(estado.aguja)}>{estado.aguja}</StatusBadge>
            <div className="mt-2 space-y-1">
              <Dato etiqueta="Transferencia" valor={estado.transferencia.estado} />
              {estado.transferencia.vehiculo && (
                <Dato etiqueta="Vehiculo" valor={<MonoId>{estado.transferencia.vehiculo}</MonoId>} />
              )}
            </div>
          </Estacion>

          <Flecha />

          {/* Grua */}
          <Estacion titulo="Grua" className="lg:w-56">
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusBadge color={grua.en_falla ? 'danger' : grua.suspendida ? 'warn' : 'ok'}>{grua.estado}</StatusBadge>
              {grua.referenciada && <StatusBadge color="accent">ref</StatusBadge>}
            </div>
            <div className="mt-1.5 space-y-1">
              <Dato etiqueta="Posicion" valor={<span className="font-mono">{grua.posicion}</span>} />
              <Dato etiqueta="Cola" valor={<span className="font-mono">{grua.cola_pendientes}</span>} />
              <Dato etiqueta="Trabajo" valor={grua.trabajo_en_curso || 'ninguno'} />
            </div>
          </Estacion>

          <Flecha />

          {/* Puerta de salida */}
          <Estacion titulo="Puerta de salida" className="lg:w-40">
            <div className="flex items-center gap-2">
              {estado.puerta_salida.toLowerCase().includes('abiert') ? (
                <DoorOpen size={16} className="text-ok" />
              ) : (
                <DoorClosed size={16} className="text-inkdim" />
              )}
              <StatusBadge color={colorPuerta(estado.puerta_salida)}>{estado.puerta_salida}</StatusBadge>
            </div>
          </Estacion>
        </div>

        {/* Parqueo de retencion: 3 plazas */}
        <div>
          <div className="text-2xs uppercase tracking-wider text-inkfaint font-medium mb-2">
            Parqueo de retencion
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {[1, 2, 3].map((n) => {
              const ret = plazasOcupadas[n]
              const ocupada = !!ret
              const minutos = ocupada
                ? Math.max(0, Math.floor((Date.now() - new Date(ret!.tiempo_inicio).getTime()) / 60000))
                : 0
              return (
                <div
                  key={n}
                  className={`border rounded p-2.5 ${
                    ocupada ? 'border-warn/50 bg-warn-soft' : 'border-line bg-surface2'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-2xs uppercase tracking-wider text-inkfaint">Plaza {n}</span>
                    <StatusBadge color={ocupada ? 'warn' : 'neutral'}>{ocupada ? 'Ocupada' : 'Libre'}</StatusBadge>
                  </div>
                  {ocupada && ret ? (
                    <div className="mt-1.5 space-y-1">
                      <Dato etiqueta="Vehiculo" valor={<MonoId>{ret.placa_vehiculo}</MonoId>} />
                      <Dato etiqueta="Contenedor" valor={<MonoId>{ret.contenedor_id}</MonoId>} />
                      <Dato etiqueta="Causa" valor={ret.causa} />
                      <Dato etiqueta="Retencion" valor={<span className="font-mono">{minutos} min</span>} />
                    </div>
                  ) : (
                    <div className="text-2xs text-inkfaint mt-1.5">Sin vehiculo asignado</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Patio */}
        <div>
          <div className="text-2xs uppercase tracking-wider text-inkfaint font-medium mb-2">
            Posiciones del patio (clic para bloquear o liberar)
          </div>
          {patioQ.loading ? (
            <Spinner />
          ) : (
            <div className="flex flex-wrap gap-2">
              {bloquesPatio.map(({ posicion, niveles }) => {
                const bloqueada = niveles.some((n) => n.bloqueada === 1)
                return (
                  <button
                    key={posicion}
                    type="button"
                    onClick={() => setCeldaDetalle(niveles.find((n) => n.contenedor_id) || niveles[0])}
                    className={`border rounded p-2 w-40 text-left transition-colors ${
                      bloqueada
                        ? 'border-danger/50 bg-danger-soft'
                        : niveles.some((n) => n.contenedor_id)
                          ? 'border-accent/40 bg-accent-soft hover:border-accent'
                          : 'border-line bg-surface2 hover:border-line2'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-2xs font-mono text-inkfaint">P{posicion}</span>
                      <StatusBadge color={bloqueada ? 'danger' : niveles.some((n) => n.contenedor_id) ? 'ok' : 'neutral'}>
                        {bloqueada ? 'Bloqueada' : niveles.some((n) => n.contenedor_id) ? 'Ocupada' : 'Libre'}
                      </StatusBadge>
                    </div>
                    <div className="mt-1 space-y-0.5">
                      {niveles.map((n) => (
                        <div key={n.nivel} className="text-2xs flex justify-between">
                          <span className="text-inkfaint">N{n.nivel}</span>
                          <span className="font-mono text-inkdim">{n.contenedor_id || '---'}</span>
                        </div>
                      ))}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Cola de trabajos */}
        <div className="flex items-center gap-3 border-t border-line pt-3 text-xs">
          <Boxes size={14} className="text-inkfaint" />
          <span className="text-inkfaint">Cola de trabajos de grua:</span>
          <span className="font-mono text-ink">{grua.cola_pendientes}</span>
          <span className="text-inkfaint ml-auto">
            Turnos activos: <span className="font-mono text-ink">{turnosActivos.length}</span>
          </span>
        </div>
      </Panel>

      {/* Controles de comando remoto */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Panel title="Control de grua" bodyClassName="p-3 flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={() => enviarComando('GruaSuspender')} title="La grua termina el movimiento en curso y no toma nuevos trabajos">
            <Pause size={13} /> Suspender grua
          </button>
          <button
            className="btn-ghost"
            disabled={!grua.suspendida}
            onClick={() => enviarComando('GruaReanudar')}
            title={grua.suspendida ? 'Reanudar cola de trabajos' : 'Disponible solo si la grua esta suspendida'}
          >
            <Play size={13} /> Reanudar grua
          </button>
          <button
            className="btn-ghost"
            disabled={!(grua.estado.toLowerCase().includes('reposo') || grua.suspendida)}
            onClick={() => enviarComando('GruaReferenciar')}
            title="Disponible en reposo o suspendida"
          >
            <Crosshair size={13} /> Referenciar
          </button>
        </Panel>

        <Panel title="Puertas y accesos" bodyClassName="p-3 flex flex-wrap gap-2">
          <button
            className="btn-primary"
            onClick={() => {
              if (estado.garita.vehiculo) setPlacaIngreso(estado.garita.vehiculo)
              setModalIngreso(true)
            }}
          >
            <Truck size={13} /> Autorizar ingreso garita
          </button>
          <button
            className="btn-ghost"
            onClick={() => confirmar('Abrir talanquera', 'El controlador rechazara el comando si hay un vehiculo detectado bajo la talanquera.', 'AbrirTalanquera')}
          >
            <DoorOpen size={13} /> Abrir talanquera
          </button>
          <button
            className="btn-ghost"
            onClick={() => confirmar('Cerrar talanquera', 'El controlador rechazara el comando si hay un vehiculo detectado bajo la talanquera.', 'CerrarTalanquera')}
          >
            <DoorClosed size={13} /> Cerrar talanquera
          </button>
          <button
            className="btn-ghost"
            onClick={() => confirmar('Abrir puerta de salida', 'El controlador rechazara el comando si hay un vehiculo detectado bajo la puerta.', 'AbrirPuertaSalida')}
          >
            <DoorOpen size={13} /> Abrir puerta salida
          </button>
        </Panel>

        <Panel title="Parqueo y modo" bodyClassName="p-3 space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="label">Plaza a liberar</label>
              <select className="input w-28" value={plazaLiberar} onChange={(e) => setPlazaLiberar(Number(e.target.value))}>
                <option value={1}>Plaza 1</option>
                <option value={2}>Plaza 2</option>
                <option value={3}>Plaza 3</option>
              </select>
            </div>
            <button
              className="btn-ghost"
              disabled={!plazasOcupadas[plazaLiberar]}
              onClick={() => enviarComando('AgujaLiberar', { plaza: plazaLiberar })}
              title="Disponible solo si la plaza esta ocupada"
            >
              <Unlock size={13} /> Liberar parqueo
            </button>
          </div>
          <div className="flex flex-wrap gap-2 pt-2 border-t border-line">
            <button
              className="btn-ghost"
              onClick={() =>
                confirmar(
                  modoMantenimiento ? 'Desactivar modo mantenimiento' : 'Activar modo mantenimiento',
                  'En modo mantenimiento la grua no admite trabajos originados por turnos. Requiere confirmacion.',
                  'ModoMantenimiento',
                  { valor: modoMantenimiento ? 'desactivar' : 'activar' },
                )
              }
            >
              <Wrench size={13} /> {modoMantenimiento ? 'Salir de mantenimiento' : 'Modo mantenimiento'}
            </button>
            <span className="text-2xs text-inkfaint self-center">
              <Radio size={11} className="inline mr-1" />
              El paro de emergencia no es comando remoto: solo se opera en la maqueta.
            </span>
          </div>
        </Panel>
      </div>

      {/* Confirmacion de comando */}
      <Modal
        open={confirmacion !== null}
        onClose={() => setConfirmacion(null)}
        title={confirmacion?.titulo || ''}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setConfirmacion(null)}>
              Cancelar
            </button>
            <button
              className="btn-primary"
              onClick={() => {
                if (confirmacion) enviarComando(confirmacion.comando, confirmacion.parametros)
                setConfirmacion(null)
              }}
            >
              Confirmar comando
            </button>
          </>
        }
      >
        <p className="text-xs text-inkdim leading-relaxed">{confirmacion?.mensaje}</p>
        {confirmacion && (
          <p className="mt-3 text-2xs text-inkfaint">
            Comando: <MonoId className="text-accent">{confirmacion.comando}</MonoId>
            {confirmacion.parametros ? ` ${JSON.stringify(confirmacion.parametros)}` : ''}
          </p>
        )}
      </Modal>

      {/* Detalle de celda de patio */}
      <Modal
        open={celdaDetalle !== null}
        onClose={() => setCeldaDetalle(null)}
        title={celdaDetalle ? `Posicion P${celdaDetalle.posicion} - Nivel ${celdaDetalle.nivel}` : ''}
        footer={
          celdaDetalle && (
            <>
              <button
                className="btn-ghost"
                disabled={celdaDetalle.bloqueada === 1}
                onClick={async () => {
                  try {
                    await liberarPosicion(celdaDetalle.posicion)
                    push('exito', `Posicion ${celdaDetalle.posicion} liberada.`)
                    patioQ.reload()
                    setCeldaDetalle(null)
                  } catch (e) {
                    push('error', e instanceof Error ? e.message : 'Error al liberar')
                  }
                }}
              >
                <Unlock size={13} /> Liberar posicion
              </button>
              <button
                className="btn-danger"
                disabled={celdaDetalle.bloqueada === 1}
                onClick={async () => {
                  try {
                    await bloquearPosicion(celdaDetalle.posicion)
                    push('exito', `Posicion ${celdaDetalle.posicion} bloqueada.`)
                    patioQ.reload()
                    setCeldaDetalle(null)
                  } catch (e) {
                    push('error', e instanceof Error ? e.message : 'Error al bloquear')
                  }
                }}
              >
                <Lock size={13} /> Bloquear posicion
              </button>
            </>
          )
        }
      >
        {celdaDetalle && (
          <div className="space-y-2 text-xs">
            <Dato etiqueta="Contenedor" valor={celdaDetalle.contenedor_id ? <MonoId>{celdaDetalle.contenedor_id}</MonoId> : 'vacia'} />
            <Dato etiqueta="Naviera" valor={celdaDetalle.naviera_id || '-'} />
            <Dato etiqueta="Peso declarado" valor={fmtKg(celdaDetalle.peso_declarado_g)} />
            <Dato etiqueta="Estado" valor={celdaDetalle.estado_autorizacion} />
            <Dato etiqueta="Bloqueada" valor={celdaDetalle.bloqueada === 1 ? 'si' : 'no'} />
            <Dato etiqueta="Remociones" valor={celdaDetalle.remociones} />
            <Dato etiqueta="Ingreso" valor={fmtFechaHora(celdaDetalle.ingreso_at)} />
          </div>
        )}
      </Modal>

      {/* Detalle del turno activo */}
      <Modal
        open={turnoDetalle !== null}
        onClose={() => setTurnoDetalle(null)}
        title={turnoDetalle ? `Turno ${turnoDetalle.codigo_turno}` : ''}
        width="max-w-xl"
      >
        {turnoDetalle && (
          <div className="space-y-2 text-xs">
            <div className="flex items-center gap-2">
              <StatusBadge color={colorTurno(turnoDetalle.estado_actual)}>
                {ETIQUETAS_ESTADO_TURNO[turnoDetalle.estado_actual]}
              </StatusBadge>
              <span className="text-inkfaint">estacion: {turnoDetalle.estacion_actual}</span>
            </div>
            <Dato etiqueta="Vehiculo" valor={<MonoId>{turnoDetalle.placa_vehiculo}</MonoId>} />
            <Dato etiqueta="Transportista" valor={turnoDetalle.transportista_id} />
            <Dato etiqueta="Contenedor" valor={<MonoId>{turnoDetalle.contenedor_id}</MonoId>} />
            <Dato etiqueta="Operacion" valor={turnoDetalle.tipo_operacion} />
            <Dato etiqueta="Pesos (decl / ent / sal)" valor={`${turnoDetalle.peso_declarado_g ?? '-'} / ${turnoDetalle.peso_medido_entrada_g ?? '-'} / ${turnoDetalle.peso_medido_salida_g ?? '-'}`} />
            <Dato etiqueta="Inicio" valor={fmtFechaHora(turnoDetalle.tiempo_inicio)} />
            <p className="text-2xs text-inkfaint pt-2 border-t border-line">
              La linea de tiempo completa se consulta en la pestaña Turnos.
            </p>
            <p className="text-2xs text-inkfaint">Operado por {user?.username}.</p>
          </div>
        )}
      </Modal>

      {/* Modal de autorizacion manual de ingreso / creacion de turno */}
      <Modal
        open={modalIngreso}
        onClose={() => setModalIngreso(false)}
        title="Autorizar ingreso en garita (Crear turno)"
        width="max-w-md"
        footer={
          <>
            <button className="btn-ghost" onClick={() => setModalIngreso(false)} disabled={creandoTurno}>
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={creandoTurno || !placaIngreso.trim() || !manifiestoIngreso}
              onClick={async () => {
                setCreandoTurno(true)
                try {
                  const res = await crearTurno({
                    placa_vehiculo: placaIngreso.trim().toUpperCase(),
                    manifiesto_id: manifiestoIngreso,
                  })
                  push('exito', res.message)
                  setModalIngreso(false)
                  setPlacaIngreso('')
                  setManifiestoIngreso('')
                  recargarLogicos()
                } catch (e) {
                  push('error', e instanceof Error ? e.message : 'Error al autorizar ingreso')
                } finally {
                  setCreandoTurno(false)
                }
              }}
            >
              {creandoTurno ? <Spinner size={13} /> : <DoorOpen size={13} />}
              {creandoTurno ? 'Autorizando...' : 'Autorizar y abrir'}
            </button>
          </>
        }
      >
        <div className="space-y-3 text-xs">
          <p className="text-inkdim">
            Valida manifiesto con levante aduanero, horario de cita y capacidad del parqueo. Al autorizar, se abre la talanquera e inicia el turno operativo.
          </p>
          <div>
            <label className="label">Placa o UID del vehiculo</label>
            <input
              className="input w-full font-mono"
              placeholder="Ej: P002BBB o D9D87BD3"
              value={placaIngreso}
              onChange={(e) => setPlacaIngreso(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Manifiesto con levante otorgado</label>
            <select
              className="input w-full"
              value={manifiestoIngreso}
              onChange={(e) => setManifiestoIngreso(e.target.value)}
            >
              <option value="">-- Seleccione manifiesto con levante --</option>
              {(manifiestosQ.data || [])
                .filter((m) => m.estado_documental === 'LEVANTE_OTORGADO')
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id} - {m.contenedor_id} ({m.tipo_operacion}, {m.naviera_id}, {m.canal_selectivo || 'VERDE'})
                  </option>
                ))}
            </select>
          </div>
        </div>
      </Modal>
    </div>
  )
}
