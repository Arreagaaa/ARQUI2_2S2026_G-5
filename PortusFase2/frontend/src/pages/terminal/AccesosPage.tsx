import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Panel } from '../../components/ui'

type Acceso = { id: number; timestamp: string; rfid_uid: string; placa_leida: string; placa_esperada: string; confianza: number; resultado: string; foto: string | null; usuario_decision: string | null }
type Vehiculo = { placa: string; rfid_uid: string; transportista_id: string; tara_g: number; activo: number }

export default function AccesosPage() {
  const [rows, setRows] = useState<Acceso[]>([])
  const [vehicles, setVehicles] = useState<Vehiculo[]>([])
  const [plate, setPlate] = useState('')
  const [uid, setUid] = useState('')
  const [owner, setOwner] = useState('')
  const [tare, setTare] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const refresh = async () => {
    try {
      setRows(await api.get('/api/fase3/accesos'))
      setVehicles(await api.get('/api/fase3/vehiculos'))
    } catch (e) { setError(String(e)) }
  }
  useEffect(() => {
    void refresh()
    const update = () => { void refresh() }
    window.addEventListener('portus:refresh', update)
    return () => window.removeEventListener('portus:refresh', update)
  }, [])
  const decide = async (row: Acceso, decision: string) => {
    const motivo = window.prompt(`Motivo para ${decision.toLowerCase()} (minimo 10 caracteres)`)
    if (motivo == null) return
    try { await api.post(`/api/fase3/accesos/${row.id}/decision`, { decision, motivo }); setError(''); await refresh() }
    catch (e) { setError(String(e)) }
  }
  const addVehicle = async () => {
    try {
      await api.post('/api/fase3/vehiculos', { placa: plate, rfid_uid: uid, transportista_id: owner, tara_g: Number(tare), motivo: reason })
      setPlate(''); setUid(''); setOwner(''); setTare(''); setReason(''); setError(''); await refresh()
    } catch (e) { setError(String(e)) }
  }
  const editVehicle = async (vehicle: Vehiculo) => {
    const next = window.prompt('Nueva placa C123ABC', vehicle.placa)
    if (next == null) return
    const nextUid = window.prompt('Nuevo UID hexadecimal', vehicle.rfid_uid)
    if (nextUid == null) return
    const why = window.prompt('Motivo de al menos 10 caracteres')
    if (why == null) return
    try { await fetch(`/api/fase3/vehiculos/${encodeURIComponent(vehicle.placa)}`, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ placa: next, rfid_uid: nextUid, motivo: why }) }).then(async r => { if (!r.ok) throw new Error((await r.json()).error) }); setError(''); await refresh() }
    catch (e) { setError(String(e)) }
  }
  const deactivate = async (vehicle: Vehiculo) => {
    const why = window.prompt(`Motivo para desactivar ${vehicle.placa} (minimo 10 caracteres)`)
    if (why == null) return
    try { await fetch(`/api/fase3/vehiculos/${encodeURIComponent(vehicle.placa)}`, { method: 'DELETE', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ motivo: why }) }).then(async r => { if (!r.ok) throw new Error((await r.json()).error) }); setError(''); await refresh() }
    catch (e) { setError(String(e)) }
  }
  return <div className="space-y-4"><Panel title="Accesos y lecturas de placa" bodyClassName="p-4 space-y-3">
    <button className="btn-ghost" onClick={refresh}>Actualizar historial</button>
    {error && <p role="alert" className="text-danger">{error}</p>}
    <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th>Hora</th><th>RFID</th><th>Placa leida</th><th>Esperada</th><th>Confianza</th><th>Resultado</th><th>Accion</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.id} className="border-t border-line"><td>{r.timestamp}</td><td>{r.rfid_uid}</td><td>{r.placa_leida || '—'}</td><td>{r.placa_esperada || '—'}</td><td>{r.confianza ?? '—'}</td><td>{r.resultado}</td><td>{r.foto && <a className="text-accent" href={`/api/fase3/accesos/${r.id}/foto`} target="_blank" rel="noreferrer"><img src={`/api/fase3/accesos/${r.id}/foto`} alt={`Ingreso ${r.id}`} className="w-24 h-16 object-cover" /></a>}{['VERIFICACION MANUAL', 'MODO DEGRADADO'].includes(r.resultado) && <div className="flex gap-1"><button className="btn-ghost" onClick={() => decide(r, 'CONFIRMAR')}>Confirmar</button><button className="btn-ghost" onClick={() => decide(r, 'RECHAZAR')}>Rechazar</button></div>}</td></tr>)}</tbody></table></div>
  </Panel>
  <Panel title="Catalogo de vehiculos" bodyClassName="p-4 space-y-3">
    <div className="flex flex-wrap gap-2">
      <input className="input" aria-label="Nueva placa" placeholder="C123ABC" value={plate} onChange={e => setPlate(e.target.value)} />
      <input className="input" aria-label="UID RFID" placeholder="UID RFID hex" value={uid} onChange={e => setUid(e.target.value)} />
      <input className="input" aria-label="Transportista" placeholder="Transportista" value={owner} onChange={e => setOwner(e.target.value)} />
      <input className="input" aria-label="Tara gramos" type="number" placeholder="Tara g" value={tare} onChange={e => setTare(e.target.value)} />
      <input className="input flex-1" aria-label="Motivo alta" placeholder="Motivo de al menos 10 caracteres" value={reason} onChange={e => setReason(e.target.value)} />
      <button className="btn-primary" onClick={addVehicle}>Agregar camion</button>
    </div>
    <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th>Placa</th><th>RFID</th><th>Transportista</th><th>Tara g</th><th>Estado</th><th>Acciones</th></tr></thead>
    <tbody>{vehicles.map(v => <tr key={v.placa} className="border-t border-line"><td>{v.placa}</td><td>{v.rfid_uid}</td><td>{v.transportista_id}</td><td>{v.tara_g}</td><td>{v.activo ? 'Activo' : 'Inactivo'}</td><td>{v.activo ? <div className="flex gap-1"><button className="btn-ghost" onClick={() => editVehicle(v)}>Editar</button><button className="btn-ghost" onClick={() => deactivate(v)}>Desactivar</button></div> : '—'}</td></tr>)}</tbody></table></div>
  </Panel></div>
}
