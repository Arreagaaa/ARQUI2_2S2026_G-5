// Rol AUTORIDAD - pestaña Retenciones aduaneras: solo causas RT03 y RT05.
// El servidor ya filtra por rol; aqui se aplican Aclarar y Rechazar (sin Corregir).
import { useMemo, useState } from 'react'
import { Check, X } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { listRetenciones, resolverRetencion } from '../../api/endpoints'
import type { Retencion } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField } from '../../components/ui'
import { ETIQUETAS_CAUSA } from '../../utils/status'
import { fmtFechaHora } from '../../utils/format'

export default function RetencionesAduanerasPage() {
  const { push } = useToast()
  const [filtroEstado, setFiltroEstado] = useState('')
  const [dialogo, setDialogo] = useState<{ ret: Retencion; tipo: 'ACLARAR' | 'RECHAZAR' } | null>(null)
  const [motivo, setMotivo] = useState('')
  const [observacion, setObservacion] = useState('')
  const [errorForm, setErrorForm] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const retenciones = useApi(
    () => listRetenciones({ estado: filtroEstado || undefined }),
    [filtroEstado],
  )

  // El endpoint ya restringe a RT03/RT05 para AUTORIDAD; el filtro doble no hace daño.
  const lista = useMemo(() => (retenciones.data || []).filter((r) => r.causa === 'RT03' || r.causa === 'RT05'), [
    retenciones.data,
  ])
  const abiertas = lista.filter((r) => r.estado === 'ABIERTA')
  const resueltas = lista.filter((r) => r.estado === 'RESUELTA')

  const abrir = (tipo: 'ACLARAR' | 'RECHAZAR', ret: Retencion) => {
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
        observacion: dialogo.tipo === 'ACLARAR' ? observacion.trim() || undefined : undefined,
      })
      if (res.error) throw new Error(res.error)
      push('exito', `Retencion ${dialogo.ret.codigo_retencion} resuelta mediante ${dialogo.tipo === 'ACLARAR' ? 'Aclarar' : 'Rechazar'}.`)
      setDialogo(null)
      retenciones.reload()
    } catch (e) {
      setErrorForm(e instanceof Error ? e.message : 'No se pudo resolver la retencion')
    } finally {
      setEnviando(false)
    }
  }

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
    { clave: 'tiempo', encabezado: 'Duracion', render: (r) => <span className="font-mono">{r.tiempo_retencion_min} min</span> },
    {
      clave: 'est',
      encabezado: 'Estado',
      render: (r) => (
        <div>
          <StatusBadge color={r.estado === 'ABIERTA' ? 'warn' : 'neutral'}>{r.estado}</StatusBadge>
          {r.tipo_resolucion && <div className="text-2xs text-inkfaint mt-0.5">{r.tipo_resolucion}</div>}
        </div>
      ),
    },
    {
      clave: 'acc',
      encabezado: 'Resolucion',
      render: (r) =>
        r.estado === 'ABIERTA' ? (
          <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
            <button
              className="btn-ghost !px-2 !py-1"
              title="Aclarar: libera la plaza y devuelve el turno sin modificar manifiestos"
              onClick={() => abrir('ACLARAR', r)}
            >
              <Check size={13} /> Aclarar
            </button>
            <button
              className="btn-danger !px-2 !py-1"
              title="Rechazar: anula el turno (motivo obligatorio)"
              onClick={() => abrir('RECHAZAR', r)}
            >
              <X size={13} /> Rechazar
            </button>
          </div>
        ) : (
          <span className="text-2xs text-inkfaint">{r.resuelto_por}</span>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      <Panel
        title="Retenciones aduaneras"
        subtitle="Causas RT03 (canal rojo) y RT05 (retencion documental). Corregir peso es exclusivo de TERMINAL."
        actions={
          <div className="flex items-center gap-2">
            <select className="input w-36 !py-1" value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
              <option value="">Todas</option>
              <option value="ABIERTA">Abiertas</option>
              <option value="RESUELTA">Resueltas</option>
            </select>
            <button className="btn-ghost" onClick={retenciones.reload}>
              Actualizar
            </button>
          </div>
        }
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnas}
          filas={abiertas}
          claveFila={(r) => r.id}
          loading={retenciones.loading}
          error={retenciones.error}
          onRetry={retenciones.reload}
          vacio="No hay retenciones aduaneras abiertas."
        />
      </Panel>

      <Panel title="Historial de retenciones aduaneras" bodyClassName="p-4">
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
        title={dialogo ? `${dialogo.tipo === 'ACLARAR' ? 'Aclarar' : 'Rechazar'} - ${dialogo.ret.codigo_retencion}` : ''}
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
            </div>

            {dialogo.tipo === 'ACLARAR' ? (
              <FormField label="Observacion (opcional)">
                <textarea
                  className="input min-h-20"
                  value={observacion}
                  onChange={(e) => setObservacion(e.target.value)}
                  placeholder="Nota sobre la decision tomada"
                />
              </FormField>
            ) : (
              <FormField label="Motivo del rechazo" required error={errorForm}>
                <textarea
                  className="input min-h-20"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  placeholder="Causa por la que no debe continuar la operacion"
                />
              </FormField>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
