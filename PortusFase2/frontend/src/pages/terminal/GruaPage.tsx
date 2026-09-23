// Pestaña Grúa: estado en vivo (SSE), cola, grafica de tiempos de ciclo e historial de fallas.
// La exportacion CSV se arma en cliente desde el historial que devuelve el servidor.
import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Download } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useApi } from '../../hooks/useApi'
import { historialGrua } from '../../api/endpoints'
import type { CicloGrua } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Panel, MonoId, StatusBadge } from '../../components/ui'
import { fmtFechaHora } from '../../utils/format'
import type { SinopticoStream } from '../../hooks/useSinopticoStream'

export default function GruaPage() {
  const { stream } = useOutletContext<{ stream: SinopticoStream }>()
  const [rango, setRango] = useState(50)
  const grua = stream.estado.grua

  // Recarga cuando llegan eventos de grua o patio desde el stream.
  const topic = stream.ultimoEvento?.topic
  const historial = useApi(() => historialGrua(rango), [rango, topic])

  const ciclos = useMemo(() => {
    const lista = historial.data || []
    // La grafica muestra los ultimos N en orden cronologico ascendente.
    return [...lista].reverse().map((c, i) => ({
      indice: i + 1,
      tiempo: c.tiempo_ciclo_seg,
      falla: c.exitoso === 0,
    }))
  }, [historial.data])

  const fallas = useMemo(() => (historial.data || []).filter((c) => c.exitoso === 0 || c.evento_falla), [historial.data])

  const stats = useMemo(() => {
    const lista = historial.data || []
    const exitosos = lista.filter((c) => c.exitoso === 1)
    const promedio = exitosos.length
      ? exitosos.reduce((acc, c) => acc + c.tiempo_ciclo_seg, 0) / exitosos.length
      : 0
    return { total: lista.length, promedio: promedio.toFixed(1) }
  }, [historial.data])

  const exportarCSV = () => {
    const lista = historial.data || []
    const filas = [
      ['id', 'turno', 'tipo_trabajo', 'origen', 'destino', 'tiempo_ciclo_seg', 'distancia_mm', 'exitoso', 'evento_falla', 'timestamp'],
      ...lista.map((c) => [
        String(c.id),
        String(c.turno_id ?? ''),
        c.tipo_trabajo,
        String(c.posicion_origen),
        String(c.posicion_destino),
        String(c.tiempo_ciclo_seg),
        String(c.distancia_recorrida_mm),
        String(c.exitoso),
        c.evento_falla ?? '',
        c.timestamp,
      ]),
    ]
    const csv = filas.map((f) => f.map((x) => (x.includes(',') ? `"${x}"` : x)).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `historial_grua_${rango}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const columnas: Columna<CicloGrua>[] = [
    { clave: 'id', encabezado: '#', render: (c) => <MonoId>{c.id}</MonoId> },
    { clave: 'ts', encabezado: 'Momento', render: (c) => <span className="font-mono text-2xs">{fmtFechaHora(c.timestamp)}</span> },
    { clave: 'tipo', encabezado: 'Trabajo', render: (c) => <span className="text-2xs uppercase">{c.tipo_trabajo}</span> },
    { clave: 'ruta', encabezado: 'Origen -> Destino', render: (c) => (
      <MonoId>
        P{c.posicion_origen} -&gt; P{c.posicion_destino}
      </MonoId>
    )},
    { clave: 'ciclo', encabezado: 'Ciclo', render: (c) => <span className="font-mono">{c.tiempo_ciclo_seg}s</span> },
    { clave: 'dist', encabezado: 'Distancia', ocultaEn: 'mobile', render: (c) => <span className="font-mono">{c.distancia_recorrida_mm} mm</span> },
    {
      clave: 'res',
      encabezado: 'Resultado',
      render: (c) => (
        <StatusBadge color={c.exitoso === 1 ? 'ok' : 'danger'}>
          {c.exitoso === 1 ? 'Exitoso' : c.evento_falla || 'Falla'}
        </StatusBadge>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* Estado en vivo */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Panel title="Estado actual" bodyClassName="p-3 space-y-2">
          <StatusBadge color={grua.en_falla ? 'danger' : grua.suspendida ? 'warn' : 'ok'}>{grua.estado}</StatusBadge>
          <div className="text-xs text-inkdim space-y-1">
            <div className="flex justify-between">
              <span className="text-inkfaint">Posicion</span>
              <span className="font-mono text-ink">{grua.posicion}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-inkfaint">Referenciada</span>
              <span>{grua.referenciada ? 'si' : 'no'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-inkfaint">Suspendida</span>
              <span>{grua.suspendida ? 'si' : 'no'}</span>
            </div>
          </div>
        </Panel>
        <Panel title="Trabajo en curso" bodyClassName="p-3">
          <p className="text-xs text-ink font-mono">{grua.trabajo_en_curso || 'Sin trabajo asignado'}</p>
        </Panel>
        <Panel title="Cola de trabajos" bodyClassName="p-3">
          <span className="text-3xl font-semibold font-mono text-accent">{grua.cola_pendientes}</span>
          <span className="text-xs text-inkfaint ml-2">pendientes</span>
        </Panel>
        <Panel title="Resumen del rango" bodyClassName="p-3 space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-inkfaint">Ciclos</span>
            <span className="font-mono text-ink">{stats.total}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-inkfaint">Tiempo promedio</span>
            <span className="font-mono text-ink">{stats.promedio}s</span>
          </div>
        </Panel>
      </div>

      {/* Grafica de ciclos */}
      <Panel
        title="Tiempo de ciclo de operaciones"
        subtitle={`Ultimas ${rango} operaciones registradas`}
        actions={
          <>
            <select className="input w-40 !py-1" value={rango} onChange={(e) => setRango(Number(e.target.value))}>
              <option value={50}>Ultimas 50</option>
              <option value={100}>Ultimas 100</option>
              <option value={200}>Ultimas 200</option>
            </select>
            <button className="btn-ghost" onClick={exportarCSV}>
              <Download size={13} /> Exportar
            </button>
          </>
        }
        bodyClassName="p-4 h-72"
      >
        {historial.loading ? (
          <div className="h-full flex items-center justify-center text-xs text-inkfaint">Cargando historial...</div>
        ) : ciclos.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-inkfaint">
            Sin ciclos de grua registrados todavia.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ciclos} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
              <CartesianGrid stroke="#263344" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="indice" stroke="#5E7189" fontSize={10} tickLine={false} />
              <YAxis stroke="#5E7189" fontSize={10} tickLine={false} unit="s" />
              <Tooltip
                contentStyle={{
                  background: '#111823',
                  border: '1px solid #31415A',
                  borderRadius: 4,
                  fontSize: 12,
                }}
                labelStyle={{ color: '#94A3B8' }}
                formatter={(v: number) => [`${v} s`, 'Tiempo de ciclo']}
                labelFormatter={(l) => `Operacion #${l}`}
              />
              <Bar dataKey="tiempo" fill="#0EA5E9" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Panel>

      {/* Historial de fallas */}
      <Panel title="Historial de eventos de falla" subtitle="Perdida de referencia, agarre no confirmado, movimiento abortado y perdida de carga" bodyClassName="p-4">
        {fallas.length === 0 ? (
          <p className="text-xs text-inkfaint py-4 text-center">No se registran fallas en el rango seleccionado.</p>
        ) : (
          <ul className="space-y-1.5">
            {fallas.map((f) => (
              <li key={f.id} className="flex items-center gap-3 text-xs border border-line rounded px-3 py-2">
                <StatusBadge color="danger">{f.evento_falla || 'FALLA'}</StatusBadge>
                <MonoId>{fmtFechaHora(f.timestamp)}</MonoId>
                <span className="text-inkdim">
                  P{f.posicion_origen} -&gt; P{f.posicion_destino}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Historial completo de ciclos" bodyClassName="p-4">
        <DataTable
          columnas={columnas}
          filas={historial.data || []}
          claveFila={(c) => c.id}
          loading={historial.loading}
          error={historial.error}
          onRetry={historial.reload}
          vacio="Sin ciclos registrados."
        />
      </Panel>
    </div>
  )
}
