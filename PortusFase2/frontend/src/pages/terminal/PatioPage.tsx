// Pestaña Patio: representacion de celdas e inventario con reloj de permanencia.
import { useMemo, useState } from 'react'
import { ArrowDownWideNarrow, Lock, Unlock } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { bloquearPosicion, liberarPosicion, listPatio } from '../../api/endpoints'
import type { CeldaPatio } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Panel, MonoId, StatusBadge } from '../../components/ui'
import { fmtFechaHora, fmtKg } from '../../utils/format'

export default function PatioPage() {
  const { push } = useToast()
  const patio = useApi(() => listPatio(), [])
  const [ordenPermanencia, setOrdenPermanencia] = useState(false)

  const celdas = patio.data || []

  const bloques = useMemo(() => {
    const posiciones = Array.from(new Set(celdas.map((c) => c.posicion))).sort((a, b) => a - b)
    return posiciones.map((p) => ({
      posicion: p,
      niveles: celdas.filter((c) => c.posicion === p).sort((a, b) => b.nivel - a.nivel),
      bloqueada: celdas.filter((c) => c.posicion === p).some((c) => c.bloqueada === 1),
    }))
  }, [celdas])

  const inventario = useMemo(() => {
    const ocupadas = celdas.filter((c) => c.contenedor_id)
    if (ordenPermanencia) return [...ocupadas].sort((a, b) => b.permanencia_min - a.permanencia_min)
    return ocupadas.sort((a, b) => a.posicion - b.posicion || a.nivel - b.nivel)
  }, [celdas, ordenPermanencia])

  const toggleBloqueo = async (c: CeldaPatio) => {
    try {
      if (c.bloqueada === 1) {
        await liberarPosicion(c.posicion)
        push('exito', `Posicion ${c.posicion} liberada.`)
      } else {
        await bloquearPosicion(c.posicion)
        push('exito', `Posicion ${c.posicion} bloqueada.`)
      }
      patio.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo cambiar el bloqueo')
    }
  }

  const columnas: Columna<CeldaPatio>[] = [
    { clave: 'cont', encabezado: 'Contenedor', render: (c) => <MonoId className="text-ink">{c.contenedor_id}</MonoId> },
    { clave: 'nav', encabezado: 'Naviera', render: (c) => c.naviera_id },
    {
      clave: 'pos',
      encabezado: 'Posicion / Nivel',
      render: (c) => (
        <MonoId>
          P{c.posicion} N{c.nivel}
        </MonoId>
      ),
    },
    { clave: 'peso', encabezado: 'Peso declarado', ocultaEn: 'mobile', render: (c) => <span className="font-mono">{fmtKg(c.peso_declarado_g)}</span> },
    { clave: 'auth', encabezado: 'Autorizacion', render: (c) => (
      <StatusBadge color={c.estado_autorizacion === 'AUTORIZADO' ? 'ok' : 'neutral'}>{c.estado_autorizacion}</StatusBadge>
    )},
    { clave: 'ing', encabezado: 'Ingreso', ocultaEn: 'tablet', render: (c) => <span className="font-mono text-2xs">{fmtFechaHora(c.ingreso_at)}</span> },
    {
      clave: 'perman',
      encabezado: 'Permanencia',
      render: (c) => (
        <span className={`font-mono ${c.permanencia_excesiva ? 'text-danger font-semibold' : 'text-ink'}`}>
          {c.permanencia_str}
          {c.permanencia_excesiva && <span className="ml-1 text-2xs">EXCESIVA</span>}
        </span>
      ),
    },
    { clave: 'rem', encabezado: 'Remociones', render: (c) => <span className="font-mono">{c.remociones}</span> },
    {
      clave: 'bloq',
      encabezado: 'Estado celda',
      render: (c) => (
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <StatusBadge color={c.bloqueada === 1 ? 'danger' : 'ok'}>{c.bloqueada === 1 ? 'Bloqueada' : 'Disponible'}</StatusBadge>
          <button className="btn-ghost !px-2 !py-1" title={c.bloqueada === 1 ? 'Liberar posicion' : 'Bloquear posicion'} onClick={() => toggleBloqueo(c)}>
            {c.bloqueada === 1 ? <Unlock size={13} /> : <Lock size={13} />}
          </button>
        </div>
      ),
    },
  ]

  const excesivas = inventario.filter((c) => c.permanencia_excesiva).length

  return (
    <div className="space-y-4">
      <Panel
        title="Estado del patio"
        subtitle="Inventario fisico confirmado por el controlador"
        actions={
          <button className="btn-ghost" onClick={patio.reload}>
            Actualizar
          </button>
        }
        bodyClassName="p-4"
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {bloques.map(({ posicion, niveles, bloqueada }) => (
            <div
              key={posicion}
              className={`border rounded p-3 ${bloqueada ? 'border-danger/50 bg-danger-soft' : 'border-line bg-surface2'}`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold font-mono text-ink">POS {posicion}</span>
                <StatusBadge color={bloqueada ? 'danger' : niveles.some((n) => n.contenedor_id) ? 'ok' : 'neutral'}>
                  {bloqueada ? 'Bloqueada' : niveles.some((n) => n.contenedor_id) ? 'Ocupada' : 'Libre'}
                </StatusBadge>
              </div>
              <div className="space-y-1.5">
                {niveles.map((n) => (
                  <div
                    key={n.nivel}
                    className={`flex items-center justify-between border rounded px-2 py-1.5 text-2xs ${
                      n.contenedor_id ? 'border-accent/40 bg-accent-soft' : 'border-line'
                    }`}
                  >
                    <span className="text-inkfaint">Nivel {n.nivel}</span>
                    {n.contenedor_id ? (
                      <span className="font-mono text-ink">{n.contenedor_id}</span>
                    ) : (
                      <span className="text-inkfaint">vacio</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Inventario de contenedores"
        subtitle={`${inventario.length} contenedores en patio${excesivas > 0 ? ` - ${excesivas} con permanencia excesiva (mas de 2 horas)` : ''}`}
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={inventario}
          claveFila={(c) => `${c.posicion}-${c.nivel}`}
          loading={patio.loading}
          error={patio.error}
          onRetry={patio.reload}
          vacio="El patio no tiene contenedores registrados."
          toolbar={
            <>
              <button
                className={`btn-ghost ${ordenPermanencia ? '!border-accent !text-accent' : ''}`}
                onClick={() => setOrdenPermanencia((v) => !v)}
              >
                <ArrowDownWideNarrow size={13} />
                {ordenPermanencia ? 'Ordenado por permanencia' : 'Ordenar por permanencia'}
              </button>
              {excesivas > 0 && <StatusBadge color="danger">{excesivas} con permanencia excesiva</StatusBadge>}
            </>
          }
        />
      </Panel>
    </div>
  )
}
