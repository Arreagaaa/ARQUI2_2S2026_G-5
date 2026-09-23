// Pestaña Alarmas: activas e historicas con reconocimiento individual y masivo.
// Una alarma no desaparece al cesar la condicion: permanece activa hasta reconocerse.
import { useMemo, useState } from 'react'
import { Check, CheckCheck } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { listAlarmas, reconocerAlarma, reconocerTodas } from '../../api/endpoints'
import type { Alarma } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField } from '../../components/ui'
import { colorSeveridad, ETIQUETAS_ROL } from '../../utils/status'
import { fmtFechaHora } from '../../utils/format'

export default function AlarmasPage() {
  const { push } = useToast()
  const [filtroSev, setFiltroSev] = useState('')
  const [reconociendo, setReconociendo] = useState<Alarma | null>(null)
  const [comentario, setComentario] = useState('')
  const [enviando, setEnviando] = useState(false)

  const alarmas = useApi(() => listAlarmas(filtroSev || undefined), [filtroSev])

  const activas = alarmas.data?.activas || []
  const historicas = alarmas.data?.historicas || []

  const conteoSev = useMemo(() => {
    const c: Record<string, number> = { Critica: 0, Alta: 0, Media: 0, Baja: 0 }
    for (const a of activas) c[a.severidad] = (c[a.severidad] || 0) + 1
    return c
  }, [activas])

  const columnas = (conAcciones: boolean): Columna<Alarma>[] => [
    { clave: 'cod', encabezado: 'Codigo', render: (a) => <MonoId className="text-ink">{a.codigo}</MonoId> },
    { clave: 'ts', encabezado: 'Aparicion', render: (a) => <span className="font-mono text-2xs">{fmtFechaHora(a.timestamp)}</span> },
    {
      clave: 'sev',
      encabezado: 'Severidad',
      render: (a) => <StatusBadge color={colorSeveridad(a.severidad)}>{a.severidad}</StatusBadge>,
    },
    { clave: 'origen', encabezado: 'Origen', render: (a) => <span className="text-2xs">{a.origen}</span>, ocultaEn: 'mobile' },
    { clave: 'desc', encabezado: 'Descripcion', render: (a) => <span className="text-ink">{a.descripcion}</span> },
    {
      clave: 'estado',
      encabezado: 'Reconocimiento',
      render: (a) =>
        a.reconocida === 1 ? (
          <div className="text-2xs">
            <StatusBadge color="neutral">Reconocida</StatusBadge>
            <div className="text-inkfaint mt-0.5">
              {a.reconocida_por} - {fmtFechaHora(a.reconocida_en)}
            </div>
          </div>
        ) : (
          <StatusBadge color="warn">Activa</StatusBadge>
        ),
      ocultaEn: 'tablet',
    },
    ...(conAcciones
      ? [
          {
            clave: 'acc',
            encabezado: 'Accion',
            render: (a: Alarma) => (
              <button
                className="btn-ghost !px-2 !py-1"
                title="Reconocer alarma"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation()
                  setComentario('')
                  setReconociendo(a)
                }}
              >
                <Check size={13} /> Reconocer
              </button>
            ),
          },
        ]
      : []),
  ]

  const confirmarReconocimiento = async () => {
    if (!reconociendo) return
    setEnviando(true)
    try {
      await reconocerAlarma(reconociendo.id, comentario.trim() || undefined)
      push('exito', `Alarma ${reconociendo.codigo} reconocida.`)
      setReconociendo(null)
      alarmas.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'No se pudo reconocer la alarma')
    } finally {
      setEnviando(false)
    }
  }

  const reconocerTodasBajaMedia = async () => {
    try {
      const res = await reconocerTodas()
      push('exito', `${res.reconocidas} alarmas de baja/media severidad reconocidas.`)
      alarmas.reload()
    } catch (e) {
      push('error', e instanceof Error ? e.message : 'Error en el reconocimiento masivo')
    }
  }

  const filtros = (
    <>
      <div>
        <label className="label">Severidad</label>
        <select className="input w-40" value={filtroSev} onChange={(e) => setFiltroSev(e.target.value)}>
          <option value="">Todas</option>
          <option value="Critica">Critica</option>
          <option value="Alta">Alta</option>
          <option value="Media">Media</option>
          <option value="Baja">Baja</option>
        </select>
      </div>
      <div className="ml-auto flex gap-2 self-end">
        <button className="btn-ghost" onClick={alarmas.reload}>
          Actualizar
        </button>
        <button
          className="btn-ghost"
          onClick={reconocerTodasBajaMedia}
          title="Reconoce todas las alarmas activas de severidad baja y media. No aplica a criticas ni altas."
        >
          <CheckCheck size={13} /> Reconocer todas (baja/media)
        </button>
      </div>
    </>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <StatusBadge color="danger">Criticas: {conteoSev.Critica}</StatusBadge>
        <StatusBadge color="danger">Altas: {conteoSev.Alta}</StatusBadge>
        <StatusBadge color="warn">Medias: {conteoSev.Media}</StatusBadge>
        <StatusBadge color="neutral">Bajas: {conteoSev.Baja}</StatusBadge>
      </div>

      <Panel title="Alarmas activas" subtitle="Permanecen hasta reconocimiento explicito del operador" bodyClassName="p-4">
        <DataTable
          columnas={columnas(true)}
          filas={activas}
          claveFila={(a) => a.id}
          loading={alarmas.loading}
          error={alarmas.error}
          onRetry={alarmas.reload}
          toolbar={filtros}
          vacio="Sin alarmas activas. El sistema opera sin condiciones anormales."
        />
      </Panel>

      <Panel title="Alarmas historicas" subtitle="Reconocidas hasta 100 registros" bodyClassName="p-4">
        <DataTable
          columnas={columnas(false)}
          filas={historicas}
          claveFila={(a) => a.id}
          loading={alarmas.loading}
          error={alarmas.error}
          onRetry={alarmas.reload}
          vacio="Sin alarmas reconocidas todavia."
        />
      </Panel>

      <Modal
        open={reconociendo !== null}
        onClose={() => setReconociendo(null)}
        title={reconociendo ? `Reconocer ${reconociendo.codigo}` : ''}
        footer={
          <>
            <button className="btn-ghost" onClick={() => setReconociendo(null)}>
              Cancelar
            </button>
            <button className="btn-primary" disabled={enviando} onClick={confirmarReconocimiento}>
              {enviando ? 'Registrando...' : 'Reconocer'}
            </button>
          </>
        }
      >
        {reconociendo && (
          <div className="space-y-3">
            <div className="bg-surface2 border border-line rounded p-3 text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-inkfaint">Descripcion</span>
                <span className="text-right">{reconociendo.descripcion}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-inkfaint">Severidad</span>
                <StatusBadge color={colorSeveridad(reconociendo.severidad)}>{reconociendo.severidad}</StatusBadge>
              </div>
              <div className="flex justify-between">
                <span className="text-inkfaint">Origen</span>
                <span>{ETIQUETAS_ROL[reconociendo.origen] || reconociendo.origen}</span>
              </div>
              {reconociendo.datos_asociados && (
                <div className="pt-1 border-t border-line">
                  <span className="text-inkfaint text-2xs">Datos asociados</span>
                  <MonoId className="block text-inkfaint break-all">{reconociendo.datos_asociados}</MonoId>
                </div>
              )}
            </div>
            <FormField label="Comentario (opcional)">
              <textarea
                className="input min-h-16"
                value={comentario}
                onChange={(e) => setComentario(e.target.value)}
                placeholder="Accion tomada frente a esta condicion"
              />
            </FormField>
          </div>
        )}
      </Modal>
    </div>
  )
}
