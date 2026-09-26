import { api } from '../../api/client'
// Rol AGENTE - pestaña Declaraciones: presentar declaracion de mercancias y
// solicitar levante ante la autoridad aduanera.
import { useMemo, useState } from 'react'
import { FileCheck2, Send, FileText } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import {
  createDeclaracion,
  listDeclaraciones,
  listManifiestos,
  solicitarLevante,
} from '../../api/endpoints'
import type { Manifiesto } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField, Spinner } from '../../components/ui'
import { colorDocumento } from '../../utils/status'
import { fmtPesoCrudo } from '../../utils/format'

interface FormDeclaracion {
  numero_declaracion: string
  regimen: string
  descripcion_mercancia: string
  valor_declarado: string
  observaciones: string
}

const VACIO: FormDeclaracion = {
  numero_declaracion: '',
  regimen: 'Importacion definitiva',
  descripcion_mercancia: '',
  valor_declarado: '',
  observaciones: '',
}

// Estados en los que el manifiesto aun no cuenta con levante resuelto.
const SIN_LEVANTE = new Set(['CREADO', 'DECLARADO', 'LEVANTE_SOLICITADO', 'LEVANTE_RETENIDO'])

export default function DeclaracionesPage() {
  const { push } = useToast()
  const [declarando, setDeclarando] = useState<Manifiesto | null>(null)
  const [form, setForm] = useState<FormDeclaracion>(VACIO)
  const [errores, setErrores] = useState<Partial<Record<keyof FormDeclaracion, string>>>({})
  const [enviando, setEnviando] = useState(false)
  const [observando, setObservando] = useState<Manifiesto | null>(null)
  const [obsTexto, setObsTexto] = useState('')

  const manifiestos = useApi(() => listManifiestos(), [])
  const declaraciones = useApi(() => listDeclaraciones(), [])

  const pendientes = useMemo(
    () => (manifiestos.data || []).filter((m) => SIN_LEVANTE.has(m.estado_documental)),
    [manifiestos.data],
  )

  const tieneDeclaracion = (manifId: string) =>
    (declaraciones.data || []).some((d) => d.manifiesto_id === manifId)

  const validar = (): boolean => {
    const e: Partial<Record<keyof FormDeclaracion, string>> = {}
    if (!form.numero_declaracion.trim()) e.numero_declaracion = 'El numero de declaracion es obligatorio y unico.'
    if (!form.regimen) e.regimen = 'Seleccione el regimen.'
    if (form.descripcion_mercancia.trim().length < 10) e.descripcion_mercancia = 'Minimo 10 caracteres.'
    const v = Number(form.valor_declarado)
    if (!form.valor_declarado || Number.isNaN(v) || v <= 0) e.valor_declarado = 'Debe ser mayor que cero.'
    setErrores(e)
    return Object.keys(e).length === 0
  }

  const presentar = async () => {
    if (!declarando || !validar()) return
    setEnviando(true)
    try {
      const res = await createDeclaracion({
        manifiesto_id: declarando.id,
        numero_declaracion: form.numero_declaracion.trim(),
        regimen: form.regimen,
        descripcion_mercancia: form.descripcion_mercancia.trim(),
        valor_declarado: Number(form.valor_declarado),
        observaciones: form.observaciones || undefined,
      })
      push('exito', res.message)
      setDeclarando(null)
      setForm(VACIO)
      setErrores({})
      manifiestos.reload()
      declaraciones.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo presentar la declaracion')
    } finally {
      setEnviando(false)
    }
  }

  const solicitar = async (m: Manifiesto) => {
    try {
      const res = await solicitarLevante(m.id)
      push('exito', res.message)
      manifiestos.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo solicitar el levante')
    }
  }

  const adjuntarObservacion = async () => {
    if (!observando) return
    try {
      await api.post('/api/declaraciones/observacion', { manifiesto_id: observando.id, observacion: obsTexto })
      push('exito', 'Observacion guardada')
      setObservando(null)
      setObsTexto('')
    } catch (e) { push('error', e instanceof Error ? e.message : 'No se pudo guardar') }
  }

  const columnas: Columna<Manifiesto>[] = [
    { clave: 'id', encabezado: 'Manifiesto', render: (m) => <MonoId className="text-ink">{m.id}</MonoId> },
    { clave: 'cont', encabezado: 'Contenedor', render: (m) => <MonoId>{m.contenedor_id}</MonoId> },
    { clave: 'nav', encabezado: 'Naviera', render: (m) => <span className="text-2xs">{m.naviera_id}</span> },
    { clave: 'tipo', encabezado: 'Operacion', render: (m) => <span className="text-2xs uppercase">{m.tipo_operacion}</span>, ocultaEn: 'mobile' },
    { clave: 'peso', encabezado: 'Peso declarado', render: (m) => <span className="font-mono">{fmtPesoCrudo(m.peso_declarado_g)}</span>, ocultaEn: 'tablet' },
    { clave: 'est', encabezado: 'Estado documental', render: (m) => <StatusBadge color={colorDocumento(m.estado_documental)}>{m.estado_documental}</StatusBadge> },
    {
      clave: 'acc',
      encabezado: 'Acciones',
      render: (m) => {
        const decl = tieneDeclaracion(m.id)
        return (
          <div className="flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
            <button
              className="btn-ghost !px-2 !py-1"
              title="Presentar declaracion de mercancias"
              disabled={decl}
              onClick={() => {
                setForm(VACIO)
                setErrores({})
                setDeclarando(m)
              }}
            >
              <FileCheck2 size={13} /> Presentar
            </button>
            <button
              className="btn-primary !px-2 !py-1"
              title={decl ? 'Enviar solicitud a la autoridad aduanera' : 'Primero presente la declaracion'}
              disabled={!decl || m.estado_documental !== 'DECLARADO'}
              onClick={() => solicitar(m)}
            >
              <Send size={13} /> Solicitar levante
            </button>
            <button
              className="btn-ghost !px-2 !py-1"
              title="Adjuntar nota documental visible para la autoridad"
              onClick={() => {
                setObsTexto('')
                setObservando(m)
              }}
            >
              <FileText size={13} /> Observacion
            </button>
          </div>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <Panel
        title="Manifiestos sin levante"
        subtitle="Declare la mercancia y solicite el levante ante la autoridad aduanera"
        actions={
          <button
            className="btn-ghost"
            onClick={() => {
              manifiestos.reload()
              declaraciones.reload()
            }}
          >
            Actualizar
          </button>
        }
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={pendientes}
          claveFila={(m) => m.id}
          loading={manifiestos.loading || declaraciones.loading}
          error={manifiestos.error || declaraciones.error}
          onRetry={() => {
            manifiestos.reload()
            declaraciones.reload()
          }}
          vacio="Todos los manifiestos cuentan con levante resuelto o no hay declaraciones pendientes."
        />
      </Panel>

      {/* Formulario de declaracion */}
      <Modal
        open={declarando !== null}
        onClose={() => setDeclarando(null)}
        title={declarando ? `Declaracion de mercancias - ${declarando.id}` : ''}
        width="max-w-xl"
        footer={
          <>
            <button className="btn-ghost" onClick={() => setDeclarando(null)}>
              Cancelar
            </button>
            <button className="btn-primary" onClick={presentar} disabled={enviando}>
              {enviando ? <Spinner size={13} /> : <FileCheck2 size={13} />}
              {enviando ? 'Presentando...' : 'Presentar declaracion'}
            </button>
          </>
        }
      >
        {declarando && (
          <div className="space-y-3">
            <div className="bg-surface2 border border-line rounded p-3 text-xs flex flex-wrap gap-4">
              <span>
                Contenedor: <MonoId className="text-ink">{declarando.contenedor_id}</MonoId>
              </span>
              <span>
                Naviera: <span className="text-ink">{declarando.naviera_id}</span>
              </span>
              <span>
                Peso: <span className="font-mono">{fmtPesoCrudo(declarando.peso_declarado_g)}</span>
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FormField label="Numero de declaracion" required error={errores.numero_declaracion}>
                <input
                  className="input font-mono"
                  value={form.numero_declaracion}
                  onChange={(e) => setForm({ ...form, numero_declaracion: e.target.value })}
                  placeholder="DEC-2026-001"
                />
              </FormField>
              <FormField label="Regimen" required error={errores.regimen}>
                <select
                  className="input"
                  value={form.regimen}
                  onChange={(e) => setForm({ ...form, regimen: e.target.value })}
                >
                  <option value="Importacion definitiva">Importacion definitiva</option>
                  <option value="Deposito temporal">Deposito temporal</option>
                </select>
              </FormField>
            </div>
            <FormField label="Descripcion de la mercancia" required error={errores.descripcion_mercancia} hint="Minimo 10 caracteres">
              <textarea
                className="input min-h-20"
                value={form.descripcion_mercancia}
                onChange={(e) => setForm({ ...form, descripcion_mercancia: e.target.value })}
                placeholder="Componentes electronicos para ensamble industrial"
              />
            </FormField>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FormField label="Valor declarado (USD)" required error={errores.valor_declarado}>
                <input
                  className="input font-mono"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={form.valor_declarado}
                  onChange={(e) => setForm({ ...form, valor_declarado: e.target.value })}
                  placeholder="15000.00"
                />
              </FormField>
              <FormField label="Observaciones (opcional)">
                <input
                  className="input"
                  value={form.observaciones}
                  onChange={(e) => setForm({ ...form, observaciones: e.target.value })}
                />
              </FormField>
            </div>
          </div>
        )}
      </Modal>

      {/* Observacion */}
      <Modal
        open={observando !== null}
        onClose={() => setObservando(null)}
        title={observando ? `Observacion documental - ${observando.id}` : ''}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setObservando(null)}>
              Cancelar
            </button>
            <button className="btn-primary" onClick={adjuntarObservacion}>
              Adjuntar
            </button>
          </>
        }
      >
        <FormField label="Nota visible para la autoridad">
          <textarea
            className="input min-h-24"
            value={obsTexto}
            onChange={(e) => setObsTexto(e.target.value)}
            placeholder="Detalle documental complementario"
          />
        </FormField>
      </Modal>
    </div>
  )
}
