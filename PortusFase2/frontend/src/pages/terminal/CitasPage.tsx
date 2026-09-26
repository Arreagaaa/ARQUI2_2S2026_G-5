// Pestaña Citas: agenda del dia en franjas de 15 minutos con capacidad maxima de dos.
// Acciones operativas: cancelar cita, reprogramar cita y bloquear/desbloquear franjas,
// todas validadas en el servidor (capacidad maxima 2, franja bloqueada, solo PROGRAMADA).
import { useMemo, useState } from 'react'
import { CalendarClock, Ban, Repeat, Lock, LockOpen } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import {
  listCitas,
  listFranjasBloqueadas,
  cancelarCita,
  reprogramarCita,
  bloquearFranja,
  desbloquearFranja,
} from '../../api/endpoints'
import type { Cita } from '../../types'
import { Panel, MonoId, StatusBadge, EmptyState } from '../../components/ui'
import { colorCita } from '../../utils/status'
import { hoyISO, minutosATexto } from '../../utils/format'

const INICIO_JORNADA = 6 * 60 // 06:00
const FIN_JORNADA = 20 * 60 // 20:00
const CAPACIDAD = 2

function hhmmAMinutos(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

export default function CitasPage() {
  const { push } = useToast()
  const [fecha, setFecha] = useState(hoyISO())
  const citas = useApi(() => listCitas(fecha), [fecha])
  const bloqueadas = useApi(() => listFranjasBloqueadas(fecha), [fecha])

  const recargar = () => {
    citas.reload()
    bloqueadas.reload()
  }

  const franjas = useMemo(() => {
    const lista = citas.data || []
    const setBloq = new Set((bloqueadas.data || []).map((b) => b.hora_inicio))
    const all: { inicio: number; fin: number; citas: Cita[]; bloqueada: boolean }[] = []
    for (let m = INICIO_JORNADA; m < FIN_JORNADA; m += 15) {
      const inicioStr = minutosATexto(m)
      const enFranja = lista.filter(
        (c) => c.hora_inicio === inicioStr || (hhmmAMinutos(c.hora_inicio) >= m && hhmmAMinutos(c.hora_inicio) < m + 15),
      )
      all.push({ inicio: m, fin: m + 15, citas: enFranja, bloqueada: setBloq.has(inicioStr) })
    }
    return all
  }, [citas.data, bloqueadas.data])

  const total = franjas.reduce((acc, f) => acc + f.citas.length, 0)
  const conContenido = franjas
  const pctCumplimiento = useMemo(() => {
    const conVentana = (citas.data || []).filter((c) => c.estado === 'CUMPLIDA' || c.estado === 'VENCIDA')
    if (conVentana.length === 0) return null
    const enVentana = conVentana.filter((c) => c.cumplida_en_ventana === 1).length
    return Math.round((enVentana / conVentana.length) * 100)
  }, [citas.data])

  const accionCancelar = async (c: Cita) => {
    if (!window.confirm(`¿Cancelar la cita del contenedor ${c.contenedor_id}? El transportista sera notificado.`)) return
    try {
      const r = await cancelarCita(c.id)
      push('exito', r.message)
      recargar()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo cancelar la cita')
    }
  }

  const accionReprogramar = async (c: Cita) => {
    const fechaNueva = window.prompt('Nueva fecha (AAAA-MM-DD):', c.fecha)
    if (fechaNueva === null) return
    const horaNueva = window.prompt('Nueva hora de inicio de franja (HH:MM):', c.hora_inicio)
    if (horaNueva === null) return
    try {
      const r = await reprogramarCita(c.id, fechaNueva.trim(), horaNueva.trim())
      push('exito', r.message)
      recargar()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo reprogramar la cita')
    }
  }

  const accionFranja = async (inicioMin: number, bloqueada: boolean) => {
    const inicioStr = minutosATexto(inicioMin)
    try {
      const r = bloqueada ? await desbloquearFranja(fecha, inicioStr) : await bloquearFranja(fecha, inicioStr)
      push('exito', r.message)
      recargar()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo actualizar la franja')
    }
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Agenda de atencion"
        subtitle="Franjas de 15 minutos - capacidad maxima 2 citas por franja"
        actions={
          <div className="flex items-center gap-2">
            {pctCumplimiento !== null && (
              <StatusBadge color={pctCumplimiento >= 80 ? 'ok' : 'warn'}>
                Cumplimiento en ventana: {pctCumplimiento}%
              </StatusBadge>
            )}
            <input
              type="date"
              className="input w-40 !py-1"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
              aria-label="Selector de fecha"
            />
          </div>
        }
        bodyClassName="p-4"
      >
        <div className="mb-3 flex flex-wrap items-center gap-3 text-2xs text-inkfaint">
          <span>
            Citas del dia: <span className="font-mono text-ink">{total}</span>
          </span>
          <span className="hidden sm:inline">Indicador de cumplimiento sobre citas con ventana registrada.</span>
        </div>

        {citas.loading ? (
          <div className="text-xs text-inkfaint py-6 text-center">Cargando agenda...</div>
        ) : citas.error ? (
          <div className="text-xs text-danger py-6 text-center">{citas.error}</div>
        ) : conContenido.length === 0 ? (
          <EmptyState mensaje={`No hay citas programadas para el ${fecha}.`} icon={<CalendarClock size={22} />} />
        ) : (
          <div className="space-y-2">
            {conContenido.map((f) => {
              const llena = f.citas.filter((c) => c.estado === 'PROGRAMADA').length >= CAPACIDAD
              return (
                <div
                  key={f.inicio}
                  className={`border rounded p-3 ${
                    f.bloqueada
                      ? 'border-danger/40 bg-danger-soft'
                      : llena
                        ? 'border-warn/40 bg-warn-soft'
                        : 'border-line bg-surface2'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <MonoId className="text-ink text-xs">
                        {minutosATexto(f.inicio)} - {minutosATexto(f.fin)}
                      </MonoId>
                      {f.bloqueada ? (
                        <StatusBadge color="danger">Franja bloqueada</StatusBadge>
                      ) : (
                        <StatusBadge color={llena ? 'warn' : 'ok'}>{f.citas.length}/{CAPACIDAD} citas</StatusBadge>
                      )}
                    </div>
                    <div className="flex gap-1.5">
                      <button
                        className="btn-ghost !px-2 !py-1"
                        onClick={() => accionFranja(f.inicio, f.bloqueada)}
                        title={f.bloqueada ? 'Permitir nuevas citas en esta franja' : 'Impedir nuevas citas en esta franja'}
                      >
                        {f.bloqueada ? <LockOpen size={12} /> : <Lock size={12} />}
                        {f.bloqueada ? ' Desbloquear franja' : ' Bloquear franja'}
                      </button>
                    </div>
                  </div>
                  {f.citas.length > 0 && (
                    <ul className="space-y-1.5">
                      {f.citas.map((c) => (
                        <li
                          key={c.id}
                          className="flex flex-wrap items-center gap-3 text-xs border border-line rounded px-2.5 py-1.5 bg-surface"
                        >
                          <StatusBadge color={colorCita(c.estado)}>{c.estado}</StatusBadge>
                          <MonoId className="text-ink">{c.contenedor_id}</MonoId>
                          <span className="text-inkdim">{c.transportista_id}</span>
                          <MonoId className="text-inkfaint">{c.manifiesto_id}</MonoId>
                          {c.estado === 'PROGRAMADA' && (
                            <span className="ml-auto flex gap-1.5">
                              <button
                                className="btn-ghost !px-2 !py-0.5"
                                onClick={() => accionCancelar(c)}
                                title="Cancelar la cita y notificar al transportista"
                              >
                                <Ban size={12} /> Cancelar
                              </button>
                              <button
                                className="btn-ghost !px-2 !py-0.5"
                                onClick={() => accionReprogramar(c)}
                                title="Mover la cita a otra franja con capacidad disponible y notificar al transportista"
                              >
                                <Repeat size={12} /> Reprogramar
                              </button>
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Panel>

      <Panel title="Nota de operacion" bodyClassName="p-4">
        <p className="text-xs text-inkdim leading-relaxed">
          Las citas se solicitan desde el canal de mensajeria del transportista con el comando{' '}
          <MonoId className="text-accent">/cita</MonoId>. Solo se admite cita para contenedores con levante otorgado
          y sin otra cita vigente. La agenda se llena por capacidad de franja y no admite mas de dos citas cada
          quince minutos. Una franja bloqueada no se ofrece al transportista.
        </p>
      </Panel>
    </div>
  )
}
