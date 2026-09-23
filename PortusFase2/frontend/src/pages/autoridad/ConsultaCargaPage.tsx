// Rol AUTORIDAD - pestaña Consulta de carga: ubicacion, estado, autorizacion y
// permanencia de cualquier contenedor de la terminal, sin restriccion de propietario.
import { useMemo, useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { listManifiestos, listPatio } from '../../api/endpoints'
import type { CeldaPatio, Manifiesto } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Panel, MonoId, StatusBadge } from '../../components/ui'
import { colorDocumento, colorCanal } from '../../utils/status'
import { fmtFechaHora } from '../../utils/format'

type Fila = {
  contenedor: string
  naviera: string
  ubicacion: string
  estadoPatio: string
  bloqueada: number
  autorizacion: string
  canal: string | null
  permanencia: string
  excesiva: boolean
  ingreso: string | null
  remociones: number
  manifiesto: string | null
}

export default function ConsultaCargaPage() {
  const [busqueda, setBusqueda] = useState('')
  const [filtroNaviera, setFiltroNaviera] = useState('')
  const [filtroAuth, setFiltroAuth] = useState('')

  const patioQ = useApi(() => listPatio(), [])
  const manifiestosQ = useApi(() => listManifiestos(), [])

  const filas = useMemo<Fila[]>(() => {
    const celdas: CeldaPatio[] = patioQ.data || []
    const manifs: Manifiesto[] = manifiestosQ.data || []

    const manifPorContenedor = new Map<string, Manifiesto>()
    for (const m of manifs) manifPorContenedor.set(m.contenedor_id, m)

    // Incluye tambien contenedores con manifiesto activo pero fuera del patio.
    const enPatio = celdas.filter((c) => c.contenedor_id)
    const idsEnPatio = new Set(enPatio.map((c) => c.contenedor_id))

    const base: Fila[] = enPatio.map((c) => {
      const m = manifPorContenedor.get(c.contenedor_id!)
      return {
        contenedor: c.contenedor_id!,
        naviera: c.naviera_id || m?.naviera_id || '-',
        ubicacion: `P${c.posicion} N${c.nivel}`,
        estadoPatio: 'En patio',
        bloqueada: c.bloqueada,
        autorizacion: m?.estado_documental || c.estado_autorizacion,
        canal: m?.canal_selectivo || null,
        permanencia: c.permanencia_str,
        excesiva: c.permanencia_excesiva,
        ingreso: c.ingreso_at,
        remociones: c.remociones,
        manifiesto: m?.id || null,
      }
    })

    const fuera: Fila[] = manifs
      .filter((m) => !idsEnPatio.has(m.contenedor_id) && m.estado_documental !== 'ANULADO')
      .map((m) => ({
        contenedor: m.contenedor_id,
        naviera: m.naviera_id,
        ubicacion: 'Fuera de patio',
        estadoPatio: 'En transito / garita',
        bloqueada: 0,
        autorizacion: m.estado_documental,
        canal: m.canal_selectivo,
        permanencia: '-',
        excesiva: false,
        ingreso: null,
        remociones: 0,
        manifiesto: m.id,
      }))

    return [...base, ...fuera]
  }, [patioQ.data, manifiestosQ.data])

  const navieras = useMemo(() => Array.from(new Set(filas.map((f) => f.naviera))).sort(), [filas])

  const filtradas = useMemo(() => {
    let lista = filas
    if (busqueda.trim()) {
      const q = busqueda.trim().toLowerCase()
      lista = lista.filter((f) => f.contenedor.toLowerCase().includes(q) || (f.manifiesto || '').toLowerCase().includes(q))
    }
    if (filtroNaviera) lista = lista.filter((f) => f.naviera === filtroNaviera)
    if (filtroAuth) lista = lista.filter((f) => f.autorizacion === filtroAuth)
    return lista
  }, [filas, busqueda, filtroNaviera, filtroAuth])

  const columnas: Columna<Fila>[] = [
    { clave: 'cont', encabezado: 'Contenedor', render: (f) => <MonoId className="text-ink">{f.contenedor}</MonoId> },
    { clave: 'nav', encabezado: 'Naviera', render: (f) => <span className="text-2xs">{f.naviera}</span> },
    { clave: 'ubi', encabezado: 'Ubicacion', render: (f) => <MonoId>{f.ubicacion}</MonoId> },
    { clave: 'est', encabezado: 'Estado', render: (f) => (
      <div>
        <span className="text-ink text-2xs">{f.estadoPatio}</span>
        {f.bloqueada === 1 && <StatusBadge color="danger">bloqueada</StatusBadge>}
      </div>
    )},
    { clave: 'auth', encabezado: 'Autorizacion', render: (f) => (
      <div className="flex flex-col gap-0.5">
        <StatusBadge color={colorDocumento(f.autorizacion)}>{f.autorizacion}</StatusBadge>
        {f.canal && <StatusBadge color={colorCanal(f.canal)}>canal {f.canal}</StatusBadge>}
      </div>
    )},
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
    { clave: 'rem', encabezado: 'Remociones', render: (f) => <span className="font-mono">{f.remociones}</span> },
    { clave: 'man', encabezado: 'Manifiesto', ocultaEn: 'mobile', render: (f) => (f.manifiesto ? <MonoId>{f.manifiesto}</MonoId> : <span className="text-inkfaint">-</span>) },
  ]

  const loading = patioQ.loading || manifiestosQ.loading
  const error = patioQ.error || manifiestosQ.error

  return (
    <div className="space-y-4">
      <Panel
        title="Consulta de carga"
        subtitle="Ubicacion, estado y autorizacion de cualquier contenedor de la terminal"
        actions={
          <button
            className="btn-ghost"
            onClick={() => {
              patioQ.reload()
              manifiestosQ.reload()
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
          claveFila={(f) => `${f.contenedor}-${f.ubicacion}`}
          loading={loading}
          error={error}
          onRetry={() => {
            patioQ.reload()
            manifiestosQ.reload()
          }}
          vacio="No hay contenedores que coincidan con la busqueda."
          toolbar={
            <>
              <div className="flex-1 min-w-44">
                <label className="label">Contenedor o manifiesto</label>
                <input
                  className="input"
                  placeholder="MSKU1001"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Naviera</label>
                <select className="input w-44" value={filtroNaviera} onChange={(e) => setFiltroNaviera(e.target.value)}>
                  <option value="">Todas</option>
                  {navieras.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Estado de autorizacion</label>
                <select className="input w-52" value={filtroAuth} onChange={(e) => setFiltroAuth(e.target.value)}>
                  <option value="">Todos</option>
                  <option value="LEVANTE_OTORGADO">Levante otorgado</option>
                  <option value="LEVANTE_SOLICITADO">Levante solicitado</option>
                  <option value="LEVANTE_RETENIDO">Levante retenido</option>
                  <option value="AUTORIZADO">Autorizado (patio)</option>
                  <option value="DECLARADO">Declarado</option>
                </select>
              </div>
            </>
          }
        />
      </Panel>
    </div>
  )
}
