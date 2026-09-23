// Pestaña Citas: agenda del dia en franjas de 15 minutos con capacidad maxima de dos.
// Cancelar y reprogramar quedan visibles pero inhabilitados: el backend todavia no
// expone esos endpoints (anotado en status.md).
import { useMemo, useState } from 'react'
import { CalendarClock, Ban, Repeat } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { listCitas } from '../../api/endpoints'
import type { Cita } from '../../types'
import { Panel, MonoId, StatusBadge, EmptyState } from '../../components/ui'
import { colorCita } from '../../utils/status'
import { hoyISO, minutosATexto } from '../../utils/format'

const INICIO_JORNADA = 6 * 60 // 06:00
const FIN_JORNADA = 20 * 60 // 20:00
const CAPACIDAD = 2

interface Franja {
  inicio: number
  fin: number
  citas: Cita[]
}

function hhmmAMinutos(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

export default function CitasPage() {
  const [fecha, setFecha] = useState(hoyISO())
  const citas = useApi(() => listCitas(fecha), [fecha])

  const franjas = useMemo<Franja[]>(() => {
    const lista = citas.data || []
    const out: Franja[] = []
    for (let m = INICIO_JORNADA; m < FIN_JORNADA; m += 15) {
      const inicioStr = minutosATexto(m)
      const finStr = minutosATexto(m + 15)
      const enFranja = lista.filter((c) => c.hora_inicio === inicioStr || (hhmmAMinutos(c.hora_inicio) >= m && hhmmAMinutos(c.hora_inicio) < m + 15))
      out.push({ inicio: m, fin: m + 15, citas: enFranja })
    }
    return out
  }, [citas.data])

  const total = franjas.reduce((acc, f) => acc + f.citas.length, 0)
  const capacidadTotal = franjas.filter((f) => f.citas.length > 0).length * CAPACIDAD || 1
  const pctCumplimiento = useMemo(() => {
    const conVentana = (citas.data || []).filter((c) => c.estado === 'CUMPLIDA' || c.estado === 'VENCIDA')
    if (conVentana.length === 0) return null
    const enVentana = conVentana.filter((c) => c.cumplida_en_ventana === 1).length
    return Math.round((enVentana / conVentana.length) * 100)
  }, [citas.data])

  const conCitas = franjas.filter((f) => f.citas.length > 0)

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
          <span>
            Ocupacion de franjas activas: <span className="font-mono text-ink">{conCitas.length * CAPACIDAD}/{capacidadTotal}</span>
          </span>
          <span className="hidden sm:inline">Indicador de cumplimiento sobre citas con ventana registrada.</span>
        </div>

        {citas.loading ? (
          <div className="text-xs text-inkfaint py-6 text-center">Cargando agenda...</div>
        ) : citas.error ? (
          <div className="text-xs text-danger py-6 text-center">{citas.error}</div>
        ) : conCitas.length === 0 ? (
          <EmptyState
            mensaje={`No hay citas programadas para el ${fecha}.`}
            icon={<CalendarClock size={22} />}
          />
        ) : (
          <div className="space-y-2">
            {conCitas.map((f) => {
              const llena = f.citas.length >= CAPACIDAD
              return (
                <div
                  key={f.inicio}
                  className={`border rounded p-3 ${llena ? 'border-warn/40 bg-warn-soft' : 'border-line bg-surface2'}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <MonoId className="text-ink text-xs">
                        {minutosATexto(f.inicio)} - {minutosATexto(f.fin)}
                      </MonoId>
                      <StatusBadge color={llena ? 'warn' : 'ok'}>
                        {f.citas.length}/{CAPACIDAD} citas
                      </StatusBadge>
                    </div>
                    <div className="flex gap-1.5">
                      <button
                        className="btn-ghost !px-2 !py-1"
                        disabled
                        title="Pendiente de endpoint de cancelacion en el backend"
                      >
                        <Ban size={12} /> Cancelar
                      </button>
                      <button
                        className="btn-ghost !px-2 !py-1"
                        disabled
                        title="Pendiente de endpoint de reprogramacion en el backend"
                      >
                        <Repeat size={12} /> Reprogramar
                      </button>
                      <button
                        className="btn-ghost !px-2 !py-1"
                        disabled
                        title="Pendiente de endpoint de bloqueo de franja en el backend"
                      >
                        Bloquear franja
                      </button>
                    </div>
                  </div>
                  <ul className="space-y-1.5">
                    {f.citas.map((c) => (
                      <li key={c.id} className="flex flex-wrap items-center gap-3 text-xs border border-line rounded px-2.5 py-1.5 bg-surface">
                        <StatusBadge color={colorCita(c.estado)}>{c.estado}</StatusBadge>
                        <MonoId className="text-ink">{c.contenedor_id}</MonoId>
                        <span className="text-inkdim">{c.transportista_id}</span>
                        <MonoId className="text-inkfaint">{c.manifiesto_id}</MonoId>
                      </li>
                    ))}
                  </ul>
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
          quince minutos.
        </p>
      </Panel>
    </div>
  )
}
