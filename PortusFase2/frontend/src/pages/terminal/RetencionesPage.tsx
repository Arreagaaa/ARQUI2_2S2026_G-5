// Pestaña Retenciones: bandeja de trabajo del operador con las tres resoluciones.
// Los botones de resolucion solo aparecen para el rol facultado segun la causa;
// el servidor vuelve a validar la restriccion al ejecutar.
import { useMemo, useState } from 'react'
import { Check, X, PencilLine } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../hooks/useAuth'
import { listRetenciones, resolverRetencion, listTurnos } from '../../api/endpoints'
import type { Retencion } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField } from '../../components/ui'
import {
  colorRetencion,
  ETIQUETAS_CAUSA,
  ETIQUETAS_RESOLUCION,
} from '../../utils/status'
import { fmtFechaHora, fmtPesoCrudo } from '../../utils/format'

type TipoResolucion = 'ACLARAR' | 'CORREGIR' | 'RECHAZAR'

export default function RetencionesPage() {
  const { push } = useToast()
  const turnos = useApi(() => listTurnos(), [])
  const fisicos = (turnos.data || []).filter((t) => t.hardware_key && !['Cerrado','Anulado'].includes(t.estado_actual) && (t.retenido_fisico || t.estado_actual==='Retenido'))
  const { user } = useAuth()
  const [filtroCausa, setFiltroCausa] = useState('')
  const [filtroEstado, setFiltroEstado] = useState('')
  const [dialogo, setDialogo] = useState<{ ret: Retencion; tipo: TipoResolucion } | null>(null)
  const [motivo, setMotivo] = useState('')
  const [observacion, setObservacion] = useState('')
  const [errorForm, setErrorForm] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const retenciones = useApi(
    () => listRetenciones({ estado: filtroEstado || undefined, causa: (filtroCausa || undefined) as never }),
    [filtroEstado, filtroCausa],
  )

  const { abiertas, resueltas } = useMemo(() => {
    const lista = retenciones.data || []
    return {
      abiertas: lista.filter((r) => r.estado === 'ABIERTA'),
      resueltas: lista.filter((r) => r.estado === 'RESUELTA'),
    }
  }, [retenciones.data])

  const puedeResolver = (r: Retencion, tipo: TipoResolucion): boolean => {
    if (!user) return false
    if (r.rol_facultado !== user.rol) return false
    if (tipo === 'CORREGIR' && user.rol !== 'TERMINAL') return false
    return true
  }

  const evidenciaPeso = (r: Retencion) =>
    r.causa === 'RT01' || r.causa === 'RT02' ? (
      <div className="font-mono text-2xs leading-relaxed">
        <div>decl: {fmtPesoCrudo(r.peso_declarado_g)}</div>
        <div>medido: {fmtPesoCrudo(r.peso_medido_g)}</div>
        <div className="text-warn">
          dif: {r.diferencia_abs_g ?? '-'} g ({r.diferencia_pct ?? '-'}%)
        </div>
      </div>
    ) : (
      <span className="text-inkfaint">-</span>
    )

  const columnas: Columna<Retencion>[] = [
    { clave: 'cod', encabezado: 'Retencion', render: (r) => <MonoId className="text-ink">{r.codigo_retencion}</MonoId> },
    { clave: 'turno', encabezado: 'Turno / Vehiculo', render: (r) => (
      <div>
        <MonoId>{r.codigo_turno}</MonoId>
        <div className="text-2xs text-inkfaint">
          <MonoId>{r.placa_vehiculo}</MonoId> / {r.contenedor_id}
        </div>
      </div>
    )},
    { clave: 'causa', encabezado: 'Causa', render: (r) => (
      <div>
        <MonoId className="text-accent">{r.causa}</MonoId>
        <div className="text-2xs text-inkfaint">{ETIQUETAS_CAUSA[r.causa]}</div>
      </div>
    )},
    { clave: 'momento', encabezado: 'Momento', ocultaEn: 'tablet', render: (r) => (
      <div className="text-2xs">
        <div>{r.estacion}</div>
        <div className="font-mono text-inkfaint">{fmtFechaHora(r.tiempo_inicio)}</div>
      </div>
    )},
    { clave: 'plaza', encabezado: 'Plaza', render: (r) => <MonoId>P{r.plaza_numero}</MonoId> },
    { clave: 'tiempo', encabezado: 'Duracion', render: (r) => (
      <span className="font-mono">{r.tiempo_retencion_min} min</span>
    )},
    { clave: 'evid', encabezado: 'Evidencia de peso', ocultaEn: 'tablet', render: evidenciaPeso },
    { clave: 'rol', encabezado: 'Rol facultado', ocultaEn: 'mobile', render: (r) => (
      <StatusBadge color={r.rol_facultado === user?.rol ? 'accent' : 'neutral'}>{r.rol_facultado}</StatusBadge>
    )},
    {
      clave: 'acciones',
      encabezado: 'Resolucion',
      render: (r) => {
        if (r.estado === 'RESUELTA') {
          return (
            <StatusBadge color="neutral">
              {r.tipo_resolucion ? ETIQUETAS_RESOLUCION[r.tipo_resolucion] : 'Resuelta'}
            </StatusBadge>
          )
        }
        return (
          <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
            <button
              className="btn-ghost !px-2 !py-1"
              title={puedeResolver(r, 'ACLARAR') ? 'Aclarar: reanuda el turno sin modificar el manifiesto' : 'Rol no facultado para esta causa'}
              disabled={!puedeResolver(r, 'ACLARAR')}
              onClick={() => abrir('ACLARAR', r)}
            >
              <Check size={13} /> Aclarar
            </button>
            <button
              className="btn-ghost !px-2 !py-1"
              title={puedeResolver(r, 'CORREGIR') ? 'Corregir: sustituye el peso declarado por el medido' : 'Corregir es exclusivo del rol TERMINAL'}
              disabled={!puedeResolver(r, 'CORREGIR')}
              onClick={() => abrir('CORREGIR', r)}
            >
              <PencilLine size={13} /> Corregir
            </button>
            <button
              className="btn-danger !px-2 !py-1"
              title={puedeResolver(r, 'RECHAZAR') ? 'Rechazar: anula el turno (motivo obligatorio)' : 'Rol no facultado para esta causa'}
              disabled={!puedeResolver(r, 'RECHAZAR')}
              onClick={() => abrir('RECHAZAR', r)}
            >
              <X size={13} /> Rechazar
            </button>
          </div>
        )
      },
    },
  ]

  const abrir = (tipo: TipoResolucion, ret: Retencion) => {
    setMotivo('')
    setObservacion('')
    setErrorForm(null)
    setDialogo({ ret, tipo })
  }

  const resolver = async () => {
    if (!dialogo) return
    if (dialogo.tipo === 'RECHAZAR' && !motivo.trim()) {
      setErrorForm('La resolucion Rechazar exige un motivo.')
      return
    }
    setEnviando(true)
    setErrorForm(null)
    try {
      const res = await resolverRetencion(dialogo.ret.id, {
        resolucion: dialogo.tipo,
        motivo_rechazo: dialogo.tipo === 'RECHAZAR' ? motivo.trim() : undefined,
        observacion: observacion.trim() || undefined,
      })
      if (res.error) throw new Error(res.error)
      push('exito', `Retencion ${dialogo.ret.codigo_retencion} resuelta mediante ${ETIQUETAS_RESOLUCION[dialogo.tipo]}.`)
      setDialogo(null)
      retenciones.reload()
    } catch (e) {
      setErrorForm(e instanceof Error ? e.message : 'No se pudo resolver la retencion')
    } finally {
      setEnviando(false)
    }
  }

  const toolbar = (
    <>
      <div>
        <label className="label">Causa</label>
        <select className="input w-64" value={filtroCausa} onChange={(e) => setFiltroCausa(e.target.value)}>
          <option value="">Todas</option>
          {Object.entries(ETIQUETAS_CAUSA).map(([cod, nombre]) => (
            <option key={cod} value={cod}>
              {cod} - {nombre}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="label">Estado</label>
        <select className="input w-36" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
          <option value="">Todas</option>
          <option value="ABIERTA">Abiertas</option>
          <option value="RESUELTA">Resueltas</option>
        </select>
      </div>
      <div className="ml-auto self-end">
        <button className="btn-ghost" onClick={retenciones.reload}>
          Actualizar
        </button>
      </div>
    </>
  )

  return (
    <div className="space-y-4">
      {fisicos.length > 0 && <Panel title="Incidencias fisicas de Fase1" bodyClassName="p-4"><p className="text-xs">Ramal o espera local; no equivalen a una plaza administrativa asignada.</p>{fisicos.map((t) => <div key={t.id} className="text-xs text-warn py-2">{t.placa_vehiculo} · {t.contenedor_id} · {t.estacion_actual} · {t.estado_actual}</div>)}</Panel>}
      <Panel
        title="Retenciones abiertas"
        subtitle={`${abiertas.length} retenciones administrativas abiertas - rol en sesion: ${user?.rol}`}
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={abiertas}
          claveFila={(r) => r.id}
          loading={retenciones.loading}
          error={retenciones.error}
          onRetry={retenciones.reload}
          toolbar={toolbar}
          vacio="No hay retenciones administrativas abiertas. Las incidencias fisicas se muestran por separado."
        />
      </Panel>

      <Panel title="Retenciones resueltas" subtitle={`${resueltas.length} decisiones tomadas`} bodyClassName="p-4">
        <DataTable
          columnas={columnas}
          filas={resueltas}
          claveFila={(r) => r.id}
          loading={retenciones.loading}
          error={retenciones.error}
          onRetry={retenciones.reload}
          vacio="Sin resoluciones registradas."
        />
      </Panel>

      <Modal
        open={dialogo !== null}
        onClose={() => setDialogo(null)}
        title={
          dialogo
            ? `${ETIQUETAS_RESOLUCION[dialogo.tipo]} - ${dialogo.ret.codigo_retencion}`
            : ''
        }
        footer={
          <>
            <button className="btn-ghost" onClick={() => setDialogo(null)}>
              Cancelar
            </button>
            <button
              className={dialogo?.tipo === 'RECHAZAR' ? 'btn-danger' : 'btn-primary'}
              disabled={enviando}
              onClick={resolver}
            >
              {enviando ? 'Aplicando...' : 'Confirmar resolucion'}
            </button>
          </>
        }
      >
        {dialogo && (
          <div className="space-y-3">
            <div className="bg-surface2 border border-line rounded p-3 text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-inkfaint">Causa</span>
                <span>
                  <MonoId className="text-accent">{dialogo.ret.causa}</MonoId> - {ETIQUETAS_CAUSA[dialogo.ret.causa]}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-inkfaint">Vehiculo</span>
                <MonoId>{dialogo.ret.placa_vehiculo}</MonoId>
              </div>
              <div className="flex justify-between">
                <span className="text-inkfaint">Contenedor</span>
                <MonoId>{dialogo.ret.contenedor_id}</MonoId>
              </div>
              <div className="flex justify-between">
                <span className="text-inkfaint">Plaza</span>
                <MonoId>P{dialogo.ret.plaza_numero}</MonoId>
              </div>
              {(dialogo.ret.causa === 'RT01' || dialogo.ret.causa === 'RT02') && (
                <div className="flex justify-between">
                  <span className="text-inkfaint">Diferencia</span>
                  <span className="font-mono text-warn">
                    {dialogo.ret.diferencia_abs_g} g ({dialogo.ret.diferencia_pct}%)
                  </span>
                </div>
              )}
            </div>

            {dialogo.tipo === 'ACLARAR' && (
              <p className="text-xs text-inkdim">
                La causa se resuelve sin modificar el manifiesto. La plaza se libera y el turno regresa al estado
                anterior a la retencion.
              </p>
            )}
            {dialogo.tipo === 'CORREGIR' && (
              <p className="text-xs text-inkdim">
                El peso declarado del manifiesto se sustituira por el peso realmente medido. El valor anterior se
                conserva en el historial y el turno continua su operacion.
              </p>
            )}
            {dialogo.tipo === 'RECHAZAR' && (
              <p className="text-xs text-danger">
                El turno pasara a Anulado, el vehiculo saldra sin completar la operacion y el inventario conservara
                su estado fisico real. El transportista recibira el aviso con el motivo.
              </p>
            )}

            <FormField label="Motivo del rechazo" required={dialogo.tipo === 'RECHAZAR'} error={errorForm}>
              <textarea
                className="input min-h-20"
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder={dialogo.tipo === 'RECHAZAR' ? 'Detalle por que no debe continuar la operacion' : 'Motivo (solo aplica si rechaza)'}
              />
            </FormField>

            {dialogo.tipo !== 'RECHAZAR' && (
              <FormField label="Observacion (opcional)">
                <textarea
                  className="input min-h-16"
                  value={observacion}
                  onChange={(e) => setObservacion(e.target.value)}
                  placeholder="Nota interna sobre la decision"
                />
              </FormField>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
