// Pestaña Reportes: calculo de las ocho metricas de operacion y exportacion CSV
// de la corrida de evaluacion (linea base para la Fase 3).
import { useState } from 'react'
import { Download, FileBarChart } from 'lucide-react'
import { calcularReporte, exportarReporte } from '../../api/endpoints'
import type { Metricas } from '../../types'
import { useToast } from '../../components/Toast'
import { Panel, FormField, MonoId, Spinner } from '../../components/ui'
import { ETIQUETAS_CAUSA, ETIQUETAS_RESOLUCION } from '../../utils/status'
import { fmtSegundos, hoyISO } from '../../utils/format'

interface Resultado {
  metricas: Metricas
  etiqueta: string
  inicio: string
  fin: string
}

function Metrica({ etiqueta, valor, unidad }: { etiqueta: string; valor: string | number; unidad: string }) {
  return (
    <div className="border border-line bg-surface2 rounded p-3">
      <div className="text-2xs uppercase tracking-wider text-inkfaint mb-1.5 leading-tight">{etiqueta}</div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-xl font-semibold font-mono text-ink">{valor}</span>
        <span className="text-2xs text-inkfaint">{unidad}</span>
      </div>
    </div>
  )
}

export default function ReportesPage() {
  const { push } = useToast()
  const [inicio, setInicio] = useState(`${hoyISO()}T00:00`)
  const [fin, setFin] = useState(`${hoyISO()}T23:59`)
  const [etiqueta, setEtiqueta] = useState('Corrida de evaluacion')
  const [cargando, setCargando] = useState(false)
  const [exportando, setExportando] = useState(false)
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generar = async () => {
    setCargando(true)
    setError(null)
    try {
      const ini = inicio ? `${inicio}:00` : undefined
      const finIso = fin ? `${fin}:00` : undefined
      const m = await calcularReporte(ini, finIso)
      setResultado({ metricas: m, etiqueta, inicio, fin })
      push('exito', 'Reporte calculado para el rango seleccionado.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo calcular el reporte')
    } finally {
      setCargando(false)
    }
  }

  const exportar = async () => {
    setExportando(true)
    try {
      const ini = resultado?.inicio ? `${resultado.inicio}:00` : undefined
      const finIso = resultado?.fin ? `${resultado.fin}:00` : undefined
      await exportarReporte(resultado?.etiqueta || etiqueta, ini, finIso)
      push('exito', 'Reporte exportado en formato CSV.')
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo exportar el reporte')
    } finally {
      setExportando(false)
    }
  }

  const m = resultado?.metricas

  return (
    <div className="space-y-4">
      <Panel title="Generar reporte de corrida" subtitle="Las metricas se calculan sobre el rango de fechas y horas seleccionado" bodyClassName="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 items-end">
          <FormField label="Inicio del rango">
            <input
              type="datetime-local"
              className="input"
              value={inicio}
              onChange={(e) => setInicio(e.target.value)}
            />
          </FormField>
          <FormField label="Fin del rango">
            <input type="datetime-local" className="input" value={fin} onChange={(e) => setFin(e.target.value)} />
          </FormField>
          <FormField label="Etiqueta de corrida" hint="Identifica la corrida en el archivo exportado">
            <input
              className="input"
              value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value)}
              placeholder="corrida de evaluacion"
            />
          </FormField>
          <div className="flex gap-2">
            <button className="btn-primary flex-1" onClick={generar} disabled={cargando}>
              {cargando ? <Spinner size={13} /> : <FileBarChart size={13} />}
              {cargando ? 'Calculando...' : 'Generar'}
            </button>
            <button className="btn-ghost" onClick={exportar} disabled={!resultado || exportando} title="Descarga CSV con las metricas y el detalle del periodo">
              {exportando ? <Spinner size={13} /> : <Download size={13} />}
              Exportar
            </button>
          </div>
        </div>
        {error && <p className="text-xs text-danger mt-3">{error}</p>}
      </Panel>

      {m && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-xs text-inkdim">
            <span>
              Etiqueta: <MonoId className="text-accent">{resultado?.etiqueta}</MonoId>
            </span>
            <span className="font-mono text-2xs">
              {resultado?.inicio.replace('T', ' ')} - {resultado?.fin.replace('T', ' ')}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Metrica etiqueta="Remociones por contenedor retirado" valor={m.remociones_por_contenedor_retirado} unidad="rem/retiro" />
            <Metrica etiqueta="Ciclos de grua por operacion completada" valor={m.ciclos_grua_por_operacion} unidad="ciclos/turno" />
            <Metrica etiqueta="Distancia total recorrida por la grua" valor={m.distancia_total_grua_m} unidad="metros" />
            <Metrica etiqueta="Tiempo promedio de camion en la terminal" valor={m.tiempo_promedio_camion_min} unidad={`min (${m.tiempo_promedio_camion_seg}s)`} />
            <Metrica etiqueta="Tiempo promedio de retencion" valor={m.tiempo_promedio_retencion_min} unidad={`min (${m.tiempo_promedio_retencion_seg}s)`} />
            <Metrica etiqueta="Longitud maxima de la fila de espera" valor={m.longitud_maxima_fila_espera} unidad="vehiculos" />
            <Metrica etiqueta="Porcentaje de citas cumplidas en ventana" valor={m.porcentaje_citas_cumplidas_ventana} unidad="%" />
            <Metrica
              etiqueta="Retenciones por causa y resolucion"
              valor={m.retenciones_desglose.reduce((a, d) => a + d.cantidad, 0)}
              unidad="total"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Panel title="Desglose de retenciones" subtitle="Por codigo de causa y tipo de resolucion" bodyClassName="p-4">
              {m.retenciones_desglose.length === 0 ? (
                <p className="text-xs text-inkfaint">Sin retenciones en el rango.</p>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-2xs uppercase tracking-wider text-inkfaint">
                      <th className="pb-2">Causa</th>
                      <th className="pb-2">Resolucion</th>
                      <th className="pb-2 text-right">Cantidad</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.retenciones_desglose.map((d, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="py-1.5">
                          <MonoId className="text-accent">{d.causa}</MonoId>{' '}
                          <span className="text-inkdim">{ETIQUETAS_CAUSA[d.causa] || ''}</span>
                        </td>
                        <td className="py-1.5 text-inkdim">{ETIQUETAS_RESOLUCION[d.resolucion] || d.resolucion}</td>
                        <td className="py-1.5 text-right font-mono text-ink">{d.cantidad}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>

            <Panel title="Conteos del periodo" bodyClassName="p-4">
              <div className="space-y-2 text-xs">
                {[
                  ['Turnos cerrados', m.resumen_conteos.turnos_cerrados],
                  ['Retiros completados', m.resumen_conteos.retiros_completados],
                  ['Ciclos de grua', m.resumen_conteos.total_ciclos_grua],
                  ['Citas totales', m.resumen_conteos.total_citas],
                  ['Citas en ventana', m.resumen_conteos.citas_en_ventana],
                  ['Duracion promedio de ciclo (nota)', fmtSegundos(m.tiempo_promedio_camion_seg)],
                ].map(([k, v]) => (
                  <div key={String(k)} className="flex justify-between border-b border-line pb-1.5">
                    <span className="text-inkfaint">{k}</span>
                    <span className="font-mono text-ink">{v}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </>
      )}

      {!m && (
        <Panel bodyClassName="p-6">
          <p className="text-xs text-inkfaint text-center">
            Seleccione un rango y pulse Generar para calcular las ocho metricas de operacion.
          </p>
        </Panel>
      )}
    </div>
  )
}
