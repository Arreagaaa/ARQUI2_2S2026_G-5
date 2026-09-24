// Rol NAVIERA - pestaña Manifiestos: declaracion, consulta y anulacion.
// El servidor aislа los manifiestos por naviera en sesion (GET /api/manifiestos).
import { useMemo, useState } from 'react'
import { Eye, FilePlus2, Trash2 } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../hooks/useAuth'
import {
  anularManifiesto,
  createManifiesto,
  listCatalogoContenedores,
  listManifiestos,
  listTransportistas,
} from '../../api/endpoints'
import type { Manifiesto } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField, Spinner } from '../../components/ui'
import { colorDocumento, colorCanal } from '../../utils/status'
import { fmtFechaHora, fmtPesoCrudo } from '../../utils/format'

interface FormManifiesto {
  contenedor_id: string
  tipo_operacion: string
  peso_declarado: string
  tolerancia: string
  transportista_id: string
  observaciones: string
}

const FORM_VACIO: FormManifiesto = {
  contenedor_id: '',
  tipo_operacion: 'DEPOSITO',
  peso_declarado: '',
  tolerancia: '',
  transportista_id: '',
  observaciones: '',
}

export default function ManifiestosPage() {
  const { push } = useToast()
  const { user } = useAuth()
  const [filtroEstado, setFiltroEstado] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [nuevoAbierto, setNuevoAbierto] = useState(false)
  const [detalle, setDetalle] = useState<Manifiesto | null>(null)
  const [porAnular, setPorAnular] = useState<Manifiesto | null>(null)
  const [form, setForm] = useState<FormManifiesto>(FORM_VACIO)
  const [errores, setErrores] = useState<Partial<Record<keyof FormManifiesto, string>>>({})
  const [enviando, setEnviando] = useState(false)

  const manifiestos = useApi(() => listManifiestos(), [])
  const transportistas = useApi(() => listTransportistas(), [])
  const catalogo = useApi(() => listCatalogoContenedores(), [])

  const filtrados = useMemo(() => {
    let lista = manifiestos.data || []
    if (filtroEstado) lista = lista.filter((m) => m.estado_documental === filtroEstado)
    if (busqueda.trim()) {
      const q = busqueda.trim().toLowerCase()
      lista = lista.filter(
        (m) => m.id.toLowerCase().includes(q) || m.contenedor_id.toLowerCase().includes(q),
      )
    }
    return lista
  }, [manifiestos.data, filtroEstado, busqueda])

  const validar = (): boolean => {
    const e: Partial<Record<keyof FormManifiesto, string>> = {}
    if (!form.contenedor_id.trim()) e.contenedor_id = 'El contenedor es obligatorio.'
    if (!form.tipo_operacion) e.tipo_operacion = 'Seleccione el tipo de operacion.'
    const peso = Number(form.peso_declarado)
    if (!form.peso_declarado || Number.isNaN(peso) || peso <= 0) e.peso_declarado = 'Debe ser un entero mayor que cero (gramos).'
    if (!form.transportista_id) e.transportista_id = 'Seleccione el transportista asignado.'
    if (form.tolerancia && (Number.isNaN(Number(form.tolerancia)) || Number(form.tolerancia) < 0))
      e.tolerancia = 'La tolerancia debe ser un porcentaje valido.'
    setErrores(e)
    return Object.keys(e).length === 0
  }

  const crear = async () => {
    if (!validar()) return
    setEnviando(true)
    try {
      const res = await createManifiesto({
        contenedor_id: form.contenedor_id.trim().toUpperCase(),
        tipo_operacion: form.tipo_operacion,
        peso_declarado: Number(form.peso_declarado),
        tolerancia: form.tolerancia ? Number(form.tolerancia) : undefined,
        transportista_id: form.transportista_id,
        observaciones: form.observaciones || undefined,
      })
      push('exito', `Manifiesto ${res.id} declarado correctamente.`)
      setNuevoAbierto(false)
      setForm(FORM_VACIO)
      setErrores({})
      manifiestos.reload()
    } catch (err) {
      push('error', err instanceof Error ? err.message : 'No se pudo crear el manifiesto')
    } finally {
      setEnviando(false)
    }
  }

  const anular = async () => {
    if (!porAnular) return
    try {
      const res = await anularManifiesto(porAnular.id)
      push('exito', res.message)
      setPorAnular(null)
      manifiestos.reload()
    } catch (err) {
      push('error', err instanceof Error ? err.message : 'No se pudo anular')
    }
  }

  const columnas: Columna<Manifiesto>[] = [
    { clave: 'id', encabezado: 'Manifiesto', render: (m) => <MonoId className="text-ink">{m.id}</MonoId> },
    { clave: 'cont', encabezado: 'Contenedor', render: (m) => <MonoId>{m.contenedor_id}</MonoId> },
    { clave: 'tipo', encabezado: 'Operacion', render: (m) => <span className="text-2xs uppercase">{m.tipo_operacion}</span> },
    { clave: 'peso', encabezado: 'Peso declarado', render: (m) => <span className="font-mono">{fmtPesoCrudo(m.peso_declarado_g)}</span>, ocultaEn: 'mobile' },
    { clave: 'tol', encabezado: 'Tolerancia', ocultaEn: 'tablet', render: (m) => <span className="font-mono">{m.tolerancia_pct}%</span> },
    { clave: 'trans', encabezado: 'Transportista', ocultaEn: 'tablet', render: (m) => <span className="text-2xs">{m.transportista_id}</span> },
    { clave: 'doc', encabezado: 'Estado documental', render: (m) => <StatusBadge color={colorDocumento(m.estado_documental)}>{m.estado_documental}</StatusBadge> },
    { clave: 'canal', encabezado: 'Canal', render: (m) => (m.canal_selectivo ? <StatusBadge color={colorCanal(m.canal_selectivo)}>{m.canal_selectivo}</StatusBadge> : <span className="text-inkfaint">-</span>) },
    { clave: 'op', encabezado: 'Estado operativo', ocultaEn: 'tablet', render: (m) => <span className="text-2xs text-inkfaint">{m.observaciones ? m.observaciones.slice(0, 40) : 'sin observaciones'}</span> },
    {
      clave: 'acc',
      encabezado: 'Acciones',
      render: (m) => (
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button className="btn-ghost !px-2 !py-1" title="Ver detalle" onClick={() => setDetalle(m)}>
            <Eye size={13} />
          </button>
          <button
            className="btn-ghost !px-2 !py-1"
            title="Anular manifiesto sin turno asociado"
            onClick={() => setPorAnular(m)}
          >
            <Trash2 size={13} />
          </button>
        </div>
      ),
    },
  ]

  const historial = (() => {
    if (!detalle) return []
    try {
      return JSON.parse(detalle.historial_pesos || '[]') as {
        fecha: string
        peso_anterior_g: number
        peso_nuevo_g: number
        corregido_por: string
      }[]
    } catch {
      return []
    }
  })()

  return (
    <div className="space-y-4">
      <Panel
        title="Manifiestos declarados"
        subtitle={`Naviera en sesion: ${user?.nombre_completo || user?.username} - solo se muestran los propios`}
        actions={
          <>
            <button className="btn-ghost" onClick={manifiestos.reload}>
              Actualizar
            </button>
            <button className="btn-primary" onClick={() => setNuevoAbierto(true)}>
              <FilePlus2 size={13} /> Nuevo manifiesto
            </button>
          </>
        }
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={filtrados}
          claveFila={(m) => m.id}
          loading={manifiestos.loading}
          error={manifiestos.error}
          onRetry={manifiestos.reload}
          vacio="No hay manifiestos declarados con los filtros aplicados."
          onFilaClick={(m) => setDetalle(m)}
          toolbar={
            <>
              <div>
                <label className="label">Estado documental</label>
                <select className="input w-52" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
                  <option value="">Todos</option>
                  <option value="CREADO">Creado</option>
                  <option value="DECLARADO">Declarado</option>
                  <option value="LEVANTE_SOLICITADO">Levante solicitado</option>
                  <option value="LEVANTE_OTORGADO">Levante otorgado</option>
                  <option value="LEVANTE_RETENIDO">Levante retenido</option>
                  <option value="ANULADO">Anulado</option>
                </select>
              </div>
              <div className="flex-1 min-w-44">
                <label className="label">Busqueda</label>
                <input
                  className="input"
                  placeholder="ID de manifiesto o contenedor"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                />
              </div>
            </>
          }
        />
      </Panel>

      {/* Formulario de nuevo manifiesto */}
      <Modal
        open={nuevoAbierto}
        onClose={() => setNuevoAbierto(false)}
        title="Declarar manifiesto"
        width="max-w-xl"
        footer={
          <>
            <button className="btn-ghost" onClick={() => setNuevoAbierto(false)}>
              Cancelar
            </button>
            <button className="btn-primary" onClick={crear} disabled={enviando}>
              {enviando ? <Spinner size={13} /> : null}
              {enviando ? 'Declarando...' : 'Declarar manifiesto'}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormField label="Identificador del contenedor" required error={errores.contenedor_id} hint="Debe existir en el catalogo de la maqueta">
            <input
              className="input font-mono uppercase"
              list="catalogo-contenedores"
              value={form.contenedor_id}
              onChange={(e) => setForm({ ...form, contenedor_id: e.target.value })}
              placeholder="MSKU1001"
            />
            <datalist id="catalogo-contenedores">
              {(catalogo.data || []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.tipo}
                </option>
              ))}
            </datalist>
          </FormField>
          <FormField label="Tipo de operacion" required error={errores.tipo_operacion}>
            <select
              className="input"
              value={form.tipo_operacion}
              onChange={(e) => setForm({ ...form, tipo_operacion: e.target.value })}
            >
              <option value="DEPOSITO">Deposito</option>
              <option value="RETIRO">Retiro</option>
            </select>
          </FormField>
          <FormField label="Peso declarado (gramos)" required error={errores.peso_declarado}>
            <input
              className="input font-mono"
              type="number"
              min={1}
              value={form.peso_declarado}
              onChange={(e) => setForm({ ...form, peso_declarado: e.target.value })}
              placeholder="22000"
            />
          </FormField>
          <FormField label="Tolerancia (%)" error={errores.tolerancia} hint="Si se omite se aplica 5%">
            <input
              className="input font-mono"
              type="number"
              step="0.1"
              min="0"
              value={form.tolerancia}
              onChange={(e) => setForm({ ...form, tolerancia: e.target.value })}
              placeholder="5"
            />
          </FormField>
          <FormField label="Transportista asignado" required error={errores.transportista_id}>
            {transportistas.loading ? (
              <Spinner size={14} />
            ) : (
              <select
                className="input"
                value={form.transportista_id}
                onChange={(e) => setForm({ ...form, transportista_id: e.target.value })}
              >
                <option value="">Seleccione...</option>
                {(transportistas.data || []).map((t) => (
                  <option key={t.username} value={t.username}>
                    {t.nombre_completo} ({t.username})
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="Observaciones">
            <input
              className="input"
              value={form.observaciones}
              onChange={(e) => setForm({ ...form, observaciones: e.target.value })}
              placeholder="Indicaciones adicionales"
            />
          </FormField>
        </div>
        <p className="text-2xs text-inkfaint mt-3">
          Un contenedor no puede tener dos manifiestos pendientes al mismo tiempo: el servidor rechaza la
          declaracion duplicada.
        </p>
      </Modal>

      {/* Detalle */}
      <Modal open={detalle !== null} onClose={() => setDetalle(null)} title={detalle ? `Manifiesto ${detalle.id}` : ''} width="max-w-xl">
        {detalle && (
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="label">Contenedor</div>
                <MonoId className="text-ink">{detalle.contenedor_id}</MonoId>
              </div>
              <div>
                <div className="label">Operacion</div>
                <span>{detalle.tipo_operacion}</span>
              </div>
              <div>
                <div className="label">Peso declarado</div>
                <span className="font-mono">{fmtPesoCrudo(detalle.peso_declarado_g)}</span>
              </div>
              <div>
                <div className="label">Tolerancia</div>
                <span className="font-mono">{detalle.tolerancia_pct}%</span>
              </div>
              <div>
                <div className="label">Transportista</div>
                <span>{detalle.transportista_id}</span>
              </div>
              <div>
                <div className="label">Estado documental</div>
                <StatusBadge color={colorDocumento(detalle.estado_documental)}>{detalle.estado_documental}</StatusBadge>
              </div>
              <div>
                <div className="label">Canal selectivo</div>
                {detalle.canal_selectivo ? (
                  <StatusBadge color={colorCanal(detalle.canal_selectivo)}>{detalle.canal_selectivo}</StatusBadge>
                ) : (
                  <span>-</span>
                )}
              </div>
              <div>
                <div className="label">Declarado</div>
                <span className="font-mono text-inkfaint">{fmtFechaHora(detalle.created_at)}</span>
              </div>
            </div>
            {detalle.observaciones && (
              <div>
                <div className="label">Observaciones</div>
                <p className="text-inkdim">{detalle.observaciones}</p>
              </div>
            )}
            <div>
              <div className="label">Historial de pesos</div>
              {historial.length === 0 ? (
                <p className="text-inkfaint">Sin correcciones de peso registradas.</p>
              ) : (
                <ul className="space-y-1">
                  {historial.map((h, i) => (
                    <li key={i} className="border border-line rounded px-2 py-1.5 flex flex-wrap justify-between gap-2">
                      <span className="font-mono text-2xs text-inkfaint">{fmtFechaHora(h.fecha)}</span>
                      <span className="font-mono">
                        {h.peso_anterior_g} g -&gt; {h.peso_nuevo_g} g
                      </span>
                      <span className="text-inkfaint">por {h.corregido_por}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </Modal>

      {/* Anular */}
      <Modal
        open={porAnular !== null}
        onClose={() => setPorAnular(null)}
        title={porAnular ? `Anular manifiesto ${porAnular.id}` : ''}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setPorAnular(null)}>
              Volver
            </button>
            <button className="btn-danger" onClick={anular}>
              Confirmar anulacion
            </button>
          </>
        }
      >
        <p className="text-xs text-inkdim">
          Solo se pueden anular manifiestos sin turno asociado. El contenedor quedara disponible para una nueva
          declaracion.
        </p>
      </Modal>
    </div>
  )
}
