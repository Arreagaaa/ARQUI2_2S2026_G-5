// Rol NAVIERA - pestaña Mis contenedores: solo la carga propia, con ubicacion,
// autorizacion vigente y reloj de permanencia. Sin controles de accion.
import { useMemo, useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { useAuth } from '../../hooks/useAuth'
import { api } from '../../api/client'
import type { Manifiesto, CeldaPatio } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Panel, MonoId, StatusBadge } from '../../components/ui'
import { colorDocumento, colorCanal } from '../../utils/status'
import { fmtFechaHora } from '../../utils/format'

type Fila = {
  contenedor: string
  manifiesto: string | null
  ubicacion: string
  estado: string
  estadoDoc: string
  canal: string | null
  permanencia: string
  excesiva: boolean
  ingreso: string | null
}

export default function MisContenedoresPage() {
  const { user } = useAuth()
  const [busqueda, setBusqueda] = useState('')
  const [filtroEstado, setFiltroEstado] = useState('')

  const carga = useApi(() => api.get<Fila[]>('/api/carga'), [])
  const filas = carga.data || []

  const filtradas = useMemo(() => {
    let lista = filas
    if (busqueda.trim()) {
      const q = busqueda.trim().toLowerCase()
      lista = lista.filter((f) => f.contenedor.toLowerCase().includes(q) || (f.manifiesto || '').toLowerCase().includes(q))
    }
    if (filtroEstado) lista = lista.filter((f) => f.estadoDoc === filtroEstado)
    return lista
  }, [filas, busqueda, filtroEstado])

  const columnas: Columna<Fila>[] = [
    { clave: 'cont', encabezado: 'Contenedor', render: (f) => <MonoId className="text-ink">{f.contenedor}</MonoId> },
    { clave: 'man', encabezado: 'Manifiesto', render: (f) => <MonoId>{f.manifiesto}</MonoId>, ocultaEn: 'mobile' },
    { clave: 'ubi', encabezado: 'Ubicacion', render: (f) => <MonoId>{f.ubicacion}</MonoId> },
    { clave: 'est', encabezado: 'Estado', render: (f) => <span className="text-ink">{f.estado}</span> },
    { clave: 'doc', encabezado: 'Autorizacion', render: (f) => <StatusBadge color={colorDocumento(f.estadoDoc)}>{f.estadoDoc}</StatusBadge> },
    {
      clave: 'canal',
      encabezado: 'Canal',
      render: (f) => (f.canal ? <StatusBadge color={colorCanal(f.canal)}>{f.canal}</StatusBadge> : <span className="text-inkfaint">-</span>),
    },
    {
      clave: 'perm',
      encabezado: 'Permanencia',
      render: (f) => (
        <span className={`font-mono ${f.excesiva ? 'text-danger font-semibold' : 'text-ink'}`}>
          {f.permanencia}
          {f.excesiva && <span className="ml-1 text-2xs">EXCESIVA</span>}
        </span>
      ),
    },
    { clave: 'ing', encabezado: 'Ingreso', ocultaEn: 'tablet', render: (f) => <span className="font-mono text-2xs">{fmtFechaHora(f.ingreso)}</span> },
  ]

  const loading = carga.loading
  const error = carga.error

  return (
    <div className="space-y-4">
      <Panel
        title="Mis contenedores"
        subtitle={`Carga declarada por ${user?.nombre_completo || user?.username} - la informacion de otras navieras no es visible`}
        actions={
          <button
            className="btn-ghost"
            onClick={() => {
              carga.reload()
              carga.reload()
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
          claveFila={(f) => f.contenedor}
          loading={loading}
          error={error}
          onRetry={() => {
            carga.reload()
          }}
          vacio="No hay contenedores asociados a sus manifiestos."
          toolbar={
            <>
              <div className="flex-1 min-w-44">
                <label className="label">Busqueda</label>
                <input
                  className="input"
                  placeholder="Contenedor o manifiesto"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Estado de autorizacion</label>
                <select className="input w-52" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
                  <option value="">Todos</option>
                  <option value="CREADO">Creado</option>
                  <option value="DECLARADO">Declarado</option>
                  <option value="LEVANTE_SOLICITADO">Levante solicitado</option>
                  <option value="LEVANTE_OTORGADO">Levante otorgado</option>
                  <option value="LEVANTE_RETENIDO">Levante retenido</option>
                </select>
              </div>
            </>
          }
        />
      </Panel>
    </div>
  )
}
