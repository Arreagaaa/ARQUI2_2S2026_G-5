// Pestaña Turnos: bandeja activa e historica con filtros, detalle y linea de tiempo.
import { useMemo, useState } from 'react'
import { Eye, ShieldAlert, Trash2 } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { anularTurno, getTimeline, retenerTurno, listTurnos } from '../../api/endpoints'
import type { EventoTimeline, Turno } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField, Skeleton } from '../../components/ui'
import {
  colorTurno,
  ETIQUETAS_ESTADO_TURNO,
} from '../../utils/status'
import { fmtFechaHora, fmtKg, fmtMinutos } from '../../utils/format'

const ESTADOS_TURNO = [
  'Programado',
  'EnGarita',
  'EnPesajeEntrada',
  'EnRuta',
  'EnTransferencia',
  'EnPesajeSalida',
  'EnSalida',
  'Retenido',
  'Cerrado',
  'Anulado',
]

const FINALES = new Set(['Cerrado', 'Anulado'])

function DetalleTurno({ turno, onClose }: { turno: Turno | null; onClose: () => void }) {
  const timeline = useApi<EventoTimeline[]>(
    () => (turno ? getTimeline(turno.id) : Promise.resolve([])),
    [turno?.id],
  )

  return (
    <Modal open={turno !== null} onClose={onClose} title={turno ? `Turno ${turno.codigo_turno} - Linea de tiempo` : ''} width="max-w-2xl">
      {turno && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <div className="label">Estado</div>
              <StatusBadge color={colorTurno(turno.estado_actual)}>
                {ETIQUETAS_ESTADO_TURNO[turno.estado_actual]}
              </StatusBadge>
            </div>
            <div>
              <div className="label">Vehiculo</div>
              <MonoId>{turno.placa_vehiculo}</MonoId>
            </div>
            <div>
              <div className="label">Contenedor</div>
              <MonoId>{turno.contenedor_id}</MonoId>
            </div>
            <div>
              <div className="label">Operacion</div>
              <span>{turno.tipo_operacion}</span>
            </div>
            <div>
              <div className="label">Peso declarado</div>
              <span className="font-mono">{fmtKg(turno.peso_declarado_g)}</span>
            </div>
            <div>
              <div className="label">Pesaje entrada</div>
              <span className="font-mono">{fmtKg(turno.peso_medido_entrada_g)}</span>
            </div>
            <div>
              <div className="label">Pesaje salida</div>
              <span className="font-mono">{fmtKg(turno.peso_medido_salida_g)}</span>
            </div>
            <div>
              <div className="label">Posicion patio</div>
              <span className="font-mono">
                {turno.posicion_patio_asignada != null
                  ? `P${turno.posicion_patio_asignada} N${turno.nivel_patio_asignado ?? 0}`
                  : '-'}
              </span>
            </div>
          </div>

          <div>
            <div className="label">Eventos del turno</div>
            {timeline.loading ? (
              <Skeleton rows={4} />
            ) : timeline.error ? (
              <p className="text-xs text-danger">{timeline.error}</p>
            ) : (timeline.data || []).length === 0 ? (
              <p className="text-xs text-inkfaint">Sin eventos registrados.</p>
            ) : (
              <ol className="border border-line rounded divide-y divide-line max-h-80 overflow-y-auto">
                {(timeline.data || []).map((ev) => (
                  <li key={ev.id} className="px-3 py-2 flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-3 text-xs">
                    <span className="font-mono text-inkfaint shrink-0 w-40">{fmtFechaHora(ev.timestamp)}</span>
                    <span className="shrink-0 w-24 text-2xs uppercase tracking-wider text-accent">{ev.origen}</span>
                    <span className="text-inkdim flex-1">{ev.descripcion}</span>
                    {ev.valores_asociados && (
                      <MonoId className="text-inkfaint shrink-0 max-w-48 truncate" >
                        {ev.valores_asociados}
                      </MonoId>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function TurnosPage() {
  const { push } = useToast()
  const [filtroEstado, setFiltroEstado] = useState('')
  const [filtroTipo, setFiltroTipo] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [detalle, setDetalle] = useState<Turno | null>(null)
  const [retener, setRetener] = useState<Turno | null>(null)
  const [observacion, setObservacion] = useState('')
  const [anular, setAnular] = useState<Turno | null>(null)
  const [accionando, setAccionando] = useState(false)

  const turnos = useApi(() => listTurnos({ estado: filtroEstado || undefined, tipo: filtroTipo || undefined, q: busqueda || undefined }), [
    filtroEstado,
    filtroTipo,
    busqueda,
  ])

  const { activos, historicos } = useMemo(() => {
    const lista = turnos.data || []
    return {
      activos: lista.filter((t) => !FINALES.has(t.estado_actual)),
      historicos: lista.filter((t) => FINALES.has(t.estado_actual)),
    }
  }, [turnos.data])

  const columnas: Columna<Turno>[] = [
    { clave: 'cod', encabezado: 'Turno', render: (t) => <MonoId className="text-ink">{t.codigo_turno}</MonoId> },
    { clave: 'veh', encabezado: 'Vehiculo / Transportista', render: (t) => (
      <div>
        <MonoId className="text-ink">{t.placa_vehiculo}</MonoId>
        <div className="text-2xs text-inkfaint">{t.transportista_id}</div>
      </div>
    )},
    { clave: 'cont', encabezado: 'Contenedor', render: (t) => <MonoId>{t.contenedor_id}</MonoId>, ocultaEn: 'mobile' },
    { clave: 'tipo', encabezado: 'Operacion', render: (t) => <span className="text-2xs uppercase">{t.tipo_operacion}</span>, ocultaEn: 'mobile' },
    { clave: 'est', encabezado: 'Estado', render: (t) => (
      <div className="flex flex-col gap-0.5">
        <StatusBadge color={colorTurno(t.estado_actual)}>{ETIQUETAS_ESTADO_TURNO[t.estado_actual]}</StatusBadge>
        <span className="text-2xs text-inkfaint">{t.estacion_actual}</span>
      </div>
    )},
    { clave: 'pesos', encabezado: 'Pesos decl / ent / sal', ocultaEn: 'tablet', render: (t) => (
      <span className="font-mono text-2xs">
        {t.peso_declarado_g ?? '-'} / {t.peso_medido_entrada_g ?? '-'} / {t.peso_medido_salida_g ?? '-'}
      </span>
    )},
    { clave: 'pos', encabezado: 'Posicion', ocultaEn: 'tablet', render: (t) =>
      t.posicion_patio_asignada != null ? (
        <MonoId>P{t.posicion_patio_asignada}N{t.nivel_patio_asignado ?? 0}</MonoId>
      ) : (
        '-'
      ),
    },
    { clave: 'tiempo', encabezado: 'Inicio / Transcurrido', render: (t) => (
      <div className="text-2xs">
        <span className="font-mono">{fmtFechaHora(t.tiempo_inicio)}</span>
        <div className="text-inkfaint">{fmtMinutos(t.tiempo_transcurrido_min)} dentro</div>
      </div>
    )},
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (t) => (
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button className="btn-ghost !px-2 !py-1" title="Ver detalle" onClick={() => setDetalle(t)}>
            <Eye size={13} />
          </button>
          {!FINALES.has(t.estado_actual) && (
            <>
              <button
                className="btn-ghost !px-2 !py-1"
                title="Retener turno"
                onClick={() => {
                  setRetener(t)
                  setObservacion('')
                }}
              >
                <ShieldAlert size={13} />
              </button>
              <button className="btn-ghost !px-2 !py-1" title="Anular turno" onClick={() => setAnular(t)}>
                <Trash2 size={13} />
              </button>
            </>
          )}
        </div>
      ),
    },
  ]

  const toolbar = (
    <>
      <div>
        <label className="label">Estado</label>
        <select className="input w-44" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
          <option value="">Todos</option>
          {ESTADOS_TURNO.map((s) => (
            <option key={s} value={s}>
              {ETIQUETAS_ESTADO_TURNO[s]}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="label">Operacion</label>
        <select className="input w-36" value={filtroTipo} onChange={(e) => setFiltroTipo(e.target.value)}>
          <option value="">Ambas</option>
          <option value="DEPOSITO">Deposito</option>
          <option value="RETIRO">Retiro</option>
        </select>
      </div>
      <div className="flex-1 min-w-44">
        <label className="label">Busqueda</label>
        <input
          className="input"
          placeholder="Contenedor, placa o codigo de turno"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
      </div>
      <div className="flex gap-2 ml-auto">
        <button
          className="btn-ghost"
          onClick={() => {
            setFiltroEstado('')
            setFiltroTipo('')
            setBusqueda('')
          }}
        >
          Limpiar
        </button>
        <button className="btn-primary" onClick={turnos.reload}>
          Actualizar
        </button>
      </div>
    </>
  )

  const ejecutarRetener = async () => {
    if (!retener) return
    setAccionando(true)
    try {
      const res = await retenerTurno(retener.id, observacion || undefined)
      push('exito', res.message)
      setRetener(null)
      turnos.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo retener el turno')
    } finally {
      setAccionando(false)
    }
  }

  const ejecutarAnular = async () => {
    if (!anular) return
    setAccionando(true)
    try {
      const res = await anularTurno(anular.id)
      push('exito', res.message)
      setAnular(null)
      turnos.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo anular el turno')
    } finally {
      setAccionando(false)
    }
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Turnos activos"
        subtitle={`${activos.length} operaciones en curso`}
        actions={<button className="btn-ghost" onClick={turnos.reload}>Actualizar</button>}
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={activos}
          claveFila={(t) => t.id}
          loading={turnos.loading}
          error={turnos.error}
          onRetry={turnos.reload}
          toolbar={toolbar}
          vacio="No hay turnos activos con los filtros aplicados."
          onFilaClick={(t) => setDetalle(t)}
        />
      </Panel>

      <Panel title="Turnos historicos" subtitle={`${historicos.length} operaciones cerradas o anuladas`} bodyClassName="p-4">
        <DataTable
          columnas={columnas}
          filas={historicos}
          claveFila={(t) => t.id}
          loading={turnos.loading}
          error={turnos.error}
          onRetry={turnos.reload}
          vacio="Sin turnos historicos todavia."
          onFilaClick={(t) => setDetalle(t)}
        />
      </Panel>

      <DetalleTurno turno={detalle} onClose={() => setDetalle(null)} />

      {/* Retencion manual */}
      <Modal
        open={retener !== null}
        onClose={() => setRetener(null)}
        title={retener ? `Retener ${retener.codigo_turno}` : ''}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setRetener(null)}>
              Cancelar
            </button>
            <button className="btn-danger" disabled={accionando} onClick={ejecutarRetener}>
              {accionando ? 'Reteniendo...' : 'Retener'}
            </button>
          </>
        }
      >
        <p className="text-xs text-inkdim mb-3">
          El vehiculo sera enviado al parqueo de retencion si se encuentra antes de la transferencia. Se generara la
          causa RT06.
        </p>
        <FormField label="Observacion (opcional)">
          <textarea
            className="input min-h-20"
            value={observacion}
            onChange={(e) => setObservacion(e.target.value)}
            placeholder="Motivo operativo de la retencion"
          />
        </FormField>
      </Modal>

      {/* Anulacion */}
      <Modal
        open={anular !== null}
        onClose={() => setAnular(null)}
        title={anular ? `Anular turno ${anular.codigo_turno}` : ''}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setAnular(null)}>
              Volver
            </button>
            <button className="btn-danger" disabled={accionando} onClick={ejecutarAnular}>
              {accionando ? 'Anulando...' : 'Confirmar anulacion'}
            </button>
          </>
        }
      >
        <p className="text-xs text-inkdim">
          El turno pasara a estado Anulado y se autorizara la salida del vehiculo sin completar la operacion. El
          inventario conserva su estado fisico real.
        </p>
      </Modal>
    </div>
  )
}
