// Rol AGENTE - pestaña Seguimiento: estado de las solicitudes presentadas,
// con canal asignado y motivo de retencion cuando corresponde.
import { useMemo, useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { useAuth } from '../../hooks/useAuth'
import { listDeclaraciones, listManifiestos } from '../../api/endpoints'
import type { Declaracion, Manifiesto } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Panel, MonoId, StatusBadge } from '../../components/ui'
import { colorDocumento, colorCanal } from '../../utils/status'
import { fmtFechaHora } from '../../utils/format'

type Fila = {
  numero: string
  manifiesto: string
  contenedor: string
  naviera: string
  regimen: string
  estado: string
  canal: string | null
  motivo: string | null
  fecha: string
}

function extraerMotivo(observaciones: string | null): string | null {
  if (!observaciones) return null
  if (observaciones.startsWith('Retenido por SAT:')) return observaciones.replace('Retenido por SAT:', '').trim()
  return observaciones
}

const ESTADO_SEGUIMIENTO = new Set(['DECLARADO', 'LEVANTE_SOLICITADO', 'LEVANTE_OTORGADO', 'LEVANTE_RETENIDO'])

export default function SeguimientoPage() {
  const { user } = useAuth()
  const [filtroEstado, setFiltroEstado] = useState('')
  const [busqueda, setBusqueda] = useState('')

  const manifiestosQ = useApi(() => listManifiestos(), [])
  const declaracionesQ = useApi(() => listDeclaraciones(), [])

  const filas = useMemo<Fila[]>(() => {
    const decls: Declaracion[] = declaracionesQ.data || []
    const manifs: Manifiesto[] = manifiestosQ.data || []
    const porId = new Map(manifs.map((m) => [m.id, m]))

    return decls
      .map((d) => {
        const m = porId.get(d.manifiesto_id)
        if (!m || !ESTADO_SEGUIMIENTO.has(m.estado_documental)) return null
        return {
          numero: d.numero_declaracion,
          manifiesto: m.id,
          contenedor: m.contenedor_id,
          naviera: m.naviera_id,
          regimen: d.regimen,
          estado: m.estado_documental,
          canal: m.canal_selectivo,
          motivo: m.estado_documental === 'LEVANTE_RETENIDO' ? extraerMotivo(m.observaciones) : null,
          fecha: d.created_at,
        } as Fila
      })
      .filter((f): f is Fila => f !== null)
  }, [declaracionesQ.data, manifiestosQ.data])

  const filtradas = useMemo(() => {
    let lista = filas
    if (filtroEstado) lista = lista.filter((f) => f.estado === filtroEstado)
    if (busqueda.trim()) {
      const q = busqueda.trim().toLowerCase()
      lista = lista.filter((f) => f.numero.toLowerCase().includes(q) || f.manifiesto.toLowerCase().includes(q) || f.contenedor.toLowerCase().includes(q))
    }
    return lista
  }, [filas, filtroEstado, busqueda])

  const columnas: Columna<Fila>[] = [
    { clave: 'num', encabezado: 'Declaracion', render: (f) => <MonoId className="text-ink">{f.numero}</MonoId> },
    { clave: 'man', encabezado: 'Manifiesto', render: (f) => <MonoId>{f.manifiesto}</MonoId>, ocultaEn: 'mobile' },
    { clave: 'cont', encabezado: 'Contenedor', render: (f) => <MonoId>{f.contenedor}</MonoId> },
    { clave: 'nav', encabezado: 'Naviera', render: (f) => <span className="text-2xs">{f.naviera}</span>, ocultaEn: 'mobile' },
    { clave: 'reg', encabezado: 'Regimen', render: (f) => <span className="text-2xs">{f.regimen}</span>, ocultaEn: 'tablet' },
    { clave: 'est', encabezado: 'Estado', render: (f) => <StatusBadge color={colorDocumento(f.estado)}>{f.estado}</StatusBadge> },
    {
      clave: 'canal',
      encabezado: 'Canal',
      render: (f) => (f.canal ? <StatusBadge color={colorCanal(f.canal)}>{f.canal}</StatusBadge> : <span className="text-inkfaint">pendiente</span>),
    },
    {
      clave: 'motivo',
      encabezado: 'Motivo de retencion',
      render: (f) => (f.motivo ? <span className="text-danger text-2xs">{f.motivo}</span> : <span className="text-inkfaint">-</span>),
      ocultaEn: 'tablet',
    },
    { clave: 'fecha', encabezado: 'Presentada', ocultaEn: 'tablet', render: (f) => <span className="font-mono text-2xs">{fmtFechaHora(f.fecha)}</span> },
  ]

  const loading = manifiestosQ.loading || declaracionesQ.loading
  const error = manifiestosQ.error || declaracionesQ.error

  return (
    <div className="space-y-4">
      <Panel
        title="Seguimiento de solicitudes"
        subtitle={`Declaraciones presentadas por ${user?.nombre_completo || user?.username}`}
        actions={
          <button
            className="btn-ghost"
            onClick={() => {
              manifiestosQ.reload()
              declaracionesQ.reload()
            }}
          >
            Actualizar
          </button>
        }
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={filtradas}
          claveFila={(f) => f.numero}
          loading={loading}
          error={error}
          onRetry={() => {
            manifiestosQ.reload()
            declaracionesQ.reload()
          }}
          vacio="No hay solicitudes presentadas con los filtros aplicados."
          toolbar={
            <>
              <div>
                <label className="label">Estado</label>
                <select className="input w-52" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
                  <option value="">Todos</option>
                  <option value="DECLARADO">Declarado</option>
                  <option value="LEVANTE_SOLICITADO">Levante solicitado</option>
                  <option value="LEVANTE_OTORGADO">Autorizada</option>
                  <option value="LEVANTE_RETENIDO">Retenida</option>
                </select>
              </div>
              <div className="flex-1 min-w-44">
                <label className="label">Busqueda</label>
                <input
                  className="input"
                  placeholder="Numero de declaracion, manifiesto o contenedor"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                />
              </div>
            </>
          }
        />
      </Panel>
    </div>
  )
}
