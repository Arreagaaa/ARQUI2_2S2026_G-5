import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Panel } from '../../components/ui'

const LABELS: Record<string, string> = {
  SegundosLecturaEstacion: 'Lectura estacion (s)', SegundosLatidoEstacion: 'Latido estacion (s)',
  MinutosSinLluviaReanudar: 'Reanudacion sin lluvia (min)', UmbralLuzEncendido: 'Luz: encender (<)',
  UmbralLuzApagado: 'Luz: apagar (>)', ConfianzaMinimaOCR: 'Confianza OCR (%)',
  IntentosOCR: 'Intentos OCR', SegundosEsperaVerificacion: 'Espera garita (s)',
  SegundosConteoCola: 'Periodo conteo (s)', UmbralCola: 'Umbral congestion (vehiculos)',
}

export default function ParametrosFase3Page() {
  const [values, setValues] = useState<Record<string, number>>({})
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => { void api.get<Record<string, number>>('/api/fase3/parametros').then(setValues).catch(e => setError(String(e))) }, [])
  const save = async () => {
    try { setValues(await api.put('/api/fase3/parametros', values)); setError(''); setMessage('Parametros guardados') }
    catch (e) { setError(String(e)); setMessage('') }
  }
  return <Panel title="Parametros de Fase 3" bodyClassName="p-4 space-y-3">
    <p className="text-xs text-inkdim">Los umbrales de luz deben estar separados por al menos cinco unidades.</p>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(LABELS).map(([key, label]) => <label key={key} className="text-xs">
      {label}<input className="input block mt-1 w-full" type="number" value={values[key] ?? ''}
        onChange={e => setValues(previous => ({ ...previous, [key]: Number(e.target.value) }))} />
    </label>)}</div>
    <button className="btn-primary" onClick={save}>Guardar parametros</button>
    {error && <p role="alert" className="text-danger text-xs">{error}</p>}
    {message && <p role="status" className="text-ok text-xs">{message}</p>}
  </Panel>
}
