import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Panel } from '../../components/ui'

type Restriccion = { placa: string; motivo: string; usuario_alta: string; alta_at: string; baja_at: string | null }

export default function PlacasRestringidasPage() {
  const [rows, setRows] = useState<Restriccion[]>([])
  const [placa, setPlaca] = useState('')
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState('')
  const refresh = async () => { try { setRows(await api.get('/api/fase3/placas')) } catch (e) { setError(String(e)) } }
  useEffect(() => { void refresh() }, [])
  const add = async () => {
    try { await api.post('/api/fase3/placas', { placa, motivo }); setPlaca(''); setMotivo(''); setError(''); await refresh() }
    catch (e) { setError(String(e)) }
  }
  const remove = async (item: Restriccion) => {
    const why = window.prompt(`Motivo para liberar ${item.placa} (minimo 10 caracteres)`)
    if (why == null) return
    try { await api.post(`/api/fase3/placas/${encodeURIComponent(item.placa)}/liberar`, { motivo: why }); setError(''); await refresh() }
    catch (e) { setError(String(e)) }
  }
  return <div className="space-y-4">
    <Panel title="Placas restringidas" bodyClassName="p-4 space-y-3">
      <div className="flex flex-wrap gap-2">
        <input className="input" aria-label="Placa" placeholder="C123ABC" value={placa} onChange={e => setPlaca(e.target.value)} />
        <input className="input flex-1" aria-label="Motivo" placeholder="Motivo de al menos 10 caracteres" value={motivo} onChange={e => setMotivo(e.target.value)} />
        <button className="btn-primary" onClick={add}>Restringir</button>
      </div>
      {error && <p role="alert" className="text-danger">{error}</p>}
      <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th>Placa</th><th>Motivo</th><th>Autoridad</th><th>Alta</th><th>Estado</th><th>Accion</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.placa} className="border-t border-line"><td>{r.placa}</td><td>{r.motivo}</td><td>{r.usuario_alta}</td><td>{r.alta_at}</td><td>{r.baja_at ? 'Liberada' : 'Activa'}</td><td>{!r.baja_at && <button className="btn-ghost" onClick={() => remove(r)}>Liberar</button>}</td></tr>)}</tbody></table></div>
    </Panel>
  </div>
}
