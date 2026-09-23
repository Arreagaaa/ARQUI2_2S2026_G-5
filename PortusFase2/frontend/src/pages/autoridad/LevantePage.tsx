// Rol AUTORIDAD - pestaña Solicitudes de levante: otorgar con canal selectivo
// o retener con motivo. El efecto fisico: sin levante la talanquera no abre;
// canal rojo envia el vehiculo al parqueo tras el pesaje de entrada.
import { useMemo, useState } from 'react'
import { Check, Eye, X } from 'lucide-react'
import { useApi } from '../../hooks/useApi'
import { useToast } from '../../components/Toast'
import { listDeclaraciones, listManifiestos, resolverLevante } from '../../api/endpoints'
import type { Declaracion, Manifiesto } from '../../types'
import { DataTable, type Columna } from '../../components/DataTable'
import { Modal, Panel, MonoId, StatusBadge, FormField, Spinner } from '../../components/ui'
import { colorDocumento } from '../../utils/status'
import { fmtFechaHora, fmtPesoCrudo } from '../../utils/format'

type Fila = Manifiesto & { declaracion: Declaracion | null }

export default function LevantePage() {
  const { push } = useToast()
  const [porResolver, setPorResolver] = useState<{ manif: Manifiesto; decision: 'OTORGAR' | 'RETENER' } | null>(null)
  const [canal, setCanal] = useState<'VERDE' | 'ROJO'>('VERDE')
  const [motivo, setMotivo] = useState('')
  const [errorForm, setErrorForm] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [verDeclaracion, setVerDeclaracion] = useState<{ manif: Manifiesto; decl: Declaracion | null } | null>(null)

  const manifiestosQ = useApi(() => listManifiestos(), [])
  const declaracionesQ = useApi(() => listDeclaraciones(), [])

  const pendientes = useMemo<Fila[]>(() => {
    const decls = declaracionesQ.data || []
    return (manifiestosQ.data || [])
      .filter((m) => m.estado_documental === 'LEVANTE_SOLICITADO')
      .map((m) => ({
        ...m,
        declaracion: decls.find((d) => d.manifiesto_id === m.id) || null,
      }))
  }, [manifiestosQ.data, declaracionesQ.data])

  const resueltas = useMemo(() => {
    return (manifiestosQ.data || []).filter(
      (m) => m.estado_documental === 'LEVANTE_OTORGADO' || m.estado_documental === 'LEVANTE_RETENIDO',
    )
  }, [manifiestosQ.data])

  const resolver = async () => {
    if (!porResolver) return
    if (porResolver.decision === 'RETENER' && !motivo.trim()) {
      setErrorForm('Debe registrar el motivo de la retencion del levante.')
      return
    }
    setEnviando(true)
    setErrorForm(null)
    try {
      const res = await resolverLevante({
        manifiesto_id: porResolver.manif.id,
        decision: porResolver.decision,
        canal: porResolver.decision === 'OTORGAR' ? canal : undefined,
        motivo: porResolver.decision === 'RETENER' ? motivo.trim() : undefined,
      })
      push('exito', res.message)
      setPorResolver(null)
      setMotivo('')
      manifiestosQ.reload()
    } catch (e) {
      setErrorForm(e instanceof Error ? e.message : 'No se pudo resolver el levante')
    } finally {
      setEnviando(false)
    }
  }

  const abrir = (manif: Manifiesto, decision: 'OTORGAR' | 'RETENER') => {
    setCanal('VERDE')
    setMotivo('')
    setErrorForm(null)
    setPorResolver({ manif, decision })
  }

  const columnasPendientes: Columna<Fila>[] = [
    { clave: 'man', encabezado: 'Manifiesto', render: (m) => <MonoId className="text-ink">{m.id}</MonoId> },
    { clave: 'cont', encabezado: 'Contenedor', render: (m) => <MonoId>{m.contenedor_id}</MonoId> },
    { clave: 'nav', encabezado: 'Naviera', render: (m) => <span className="text-2xs">{m.naviera_id}</span> },
    { clave: 'ag', encabezado: 'Agente', render: (m) => <span className="text-2xs">{m.declaracion?.agente_id || '-'}</span>, ocultaEn: 'mobile' },
    { clave: 'decl', encabezado: 'Declaracion', render: (m) => <MonoId>{m.declaracion?.numero_declaracion || 'sin registro'}</MonoId>, ocultaEn: 'tablet' },
    { clave: 'peso', encabezado: 'Peso declarado', render: (m) => <span className="font-mono">{fmtPesoCrudo(m.peso_declarado_g)}</span>, ocultaEn: 'mobile' },
    { clave: 'est', encabezado: 'Estado', render: (m) => <StatusBadge color={colorDocumento(m.estado_documental)}>{m.estado_documental}</StatusBadge> },
    {
      clave: 'acc',
      encabezado: 'Acciones',
      render: (m) => (
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button
            className="btn-ghost !px-2 !py-1"
            title="Ver declaracion de mercancias"
            onClick={() => setVerDeclaracion({ manif: m, decl: m.declaracion })}
          >
            <Eye size={13} /> Ver declaracion
          </button>
          <button className="btn-ok !px-2 !py-1" title="Otorgar levante (obliga a elegir canal)" onClick={() => abrir(m, 'OTORGAR')}>
            <Check size={13} /> Otorgar
          </button>
          <button className="btn-danger !px-2 !py-1" title="Retener levante con motivo registrado" onClick={() => abrir(m, 'RETENER')}>
            <X size={13} /> Retener
          </button>
        </div>
      ),
    },
  ]

  const columnasResueltas: Columna<Manifiesto>[] = [
    { clave: 'man', encabezado: 'Manifiesto', render: (m) => <MonoId className="text-ink">{m.id}</MonoId> },
    { clave: 'cont', encabezado: 'Contenedor', render: (m) => <MonoId>{m.contenedor_id}</MonoId> },
    { clave: 'nav', encabezado: 'Naviera', render: (m) => <span className="text-2xs">{m.naviera_id}</span> },
    { clave: 'est', encabezado: 'Decision', render: (m) => <StatusBadge color={colorDocumento(m.estado_documental)}>{m.estado_documental}</StatusBadge> },
    {
      clave: 'canal',
      encabezado: 'Canal',
      render: (m) =>
        m.canal_selectivo ? (
          <StatusBadge color={m.canal_selectivo === 'VERDE' ? 'ok' : 'danger'}>{m.canal_selectivo}</StatusBadge>
        ) : (
          <span className="text-inkfaint">-</span>
        ),
    },
    {
      clave: 'motivo',
      encabezado: 'Motivo / Observaciones',
      render: (m) => <span className="text-2xs">{m.observaciones || '-'}</span>,
      ocultaEn: 'tablet',
    },
    { clave: 'act', encabezado: 'Actualizado', ocultaEn: 'tablet', render: (m) => <span className="font-mono text-2xs">{fmtFechaHora(m.updated_at)}</span> },
  ]

  const reload = () => {
    manifiestosQ.reload()
    declaracionesQ.reload()
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Solicitudes de levante pendientes"
        subtitle="Otorgar exige canal selectivo; retener exige motivo registrado"
        actions={<button className="btn-ghost" onClick={reload}>Actualizar</button>}
        bodyClassName="p-4"
      >
        <DataTable
          columnas={columnasPendientes}
          filas={pendientes}
          claveFila={(m) => m.id}
          loading={manifiestosQ.loading || declaracionesQ.loading}
          error={manifiestosQ.error || declaracionesQ.error}
          onRetry={reload}
          vacio="No hay solicitudes de levante pendientes de resolucion."
        />
      </Panel>

      <Panel title="Levantes resueltos" subtitle="Decisiones ya tomadas por la autoridad" bodyClassName="p-4">
        <DataTable
          columnas={columnasResueltas}
          filas={resueltas}
          claveFila={(m) => m.id}
          loading={manifiestosQ.loading}
          error={manifiestosQ.error}
          onRetry={reload}
          vacio="Sin levantes resueltos todavia."
        />
      </Panel>

      {/* Resolver levante */}
      <Modal
        open={porResolver !== null}
        onClose={() => setPorResolver(null)}
        title={
          porResolver
            ? `${porResolver.decision === 'OTORGAR' ? 'Otorgar levante' : 'Retener levante'} - ${porResolver.manif.id}`
            : ''
        }
        footer={
          <>
            <button className="btn-ghost" onClick={() => setPorResolver(null)}>
              Cancelar
            </button>
            <button
              className={porResolver?.decision === 'RETENER' ? 'btn-danger' : 'btn-primary'}
              disabled={enviando}
              onClick={resolver}
            >
              {enviando ? <Spinner size={13} /> : null}
              {enviando ? 'Registrando...' : 'Confirmar decision'}
            </button>
          </>
        }
      >
        {porResolver && (
          <div className="space-y-3">
            <div className="bg-surface2 border border-line rounded p-3 text-xs grid grid-cols-2 gap-2">
              <div>
                <span className="text-inkfaint">Contenedor: </span>
                <MonoId className="text-ink">{porResolver.manif.contenedor_id}</MonoId>
              </div>
              <div>
                <span className="text-inkfaint">Naviera: </span>
                <span>{porResolver.manif.naviera_id}</span>
              </div>
              <div>
                <span className="text-inkfaint">Peso: </span>
                <span className="font-mono">{fmtPesoCrudo(porResolver.manif.peso_declarado_g)}</span>
              </div>
              <div>
                <span className="text-inkfaint">Operacion: </span>
                <span>{porResolver.manif.tipo_operacion}</span>
              </div>
            </div>

            {porResolver.decision === 'OTORGAR' ? (
              <>
                <FormField label="Canal de selectivo" required hint="Verde: ingreso normal. Rojo: el vehiculo va al parqueo tras el pesaje de entrada.">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className={`btn flex-1 ${canal === 'VERDE' ? 'bg-ok text-base' : 'bg-surface2 text-inkdim border border-line'}`}
                      onClick={() => setCanal('VERDE')}
                    >
                      Canal VERDE
                    </button>
                    <button
                      type="button"
                      className={`btn flex-1 ${canal === 'ROJO' ? 'bg-danger text-white' : 'bg-surface2 text-inkdim border border-line'}`}
                      onClick={() => setCanal('ROJO')}
                    >
                      Canal ROJO
                    </button>
                  </div>
                </FormField>
                <p className="text-2xs text-inkfaint">
                  Con levante otorgado la talanquera podra abrirse. El transportista recibira la notificacion con el
                  canal asignado.
                </p>
              </>
            ) : (
              <FormField label="Motivo de la retencion" required error={errorForm}>
                <textarea
                  className="input min-h-20"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  placeholder="Causa documental que impide el retiro o deposito"
                />
              </FormField>
            )}
            {errorForm && porResolver.decision === 'OTORGAR' && (
              <p className="text-xs text-danger">{errorForm}</p>
            )}
          </div>
        )}
      </Modal>

      {/* Ver declaracion */}
      <Modal
        open={verDeclaracion !== null}
        onClose={() => setVerDeclaracion(null)}
        title={verDeclaracion ? `Declaracion - ${verDeclaracion.manif.id}` : ''}
      >
        {verDeclaracion && (
          <div className="space-y-2 text-xs">
            {verDeclaracion.decl ? (
              <>
                <div className="flex justify-between border-b border-line pb-1.5">
                  <span className="text-inkfaint">Numero</span>
                  <MonoId className="text-ink">{verDeclaracion.decl.numero_declaracion}</MonoId>
                </div>
                <div className="flex justify-between border-b border-line pb-1.5">
                  <span className="text-inkfaint">Regimen</span>
                  <span>{verDeclaracion.decl.regimen}</span>
                </div>
                <div className="flex justify-between border-b border-line pb-1.5">
                  <span className="text-inkfaint">Agente</span>
                  <span>{verDeclaracion.decl.agente_id}</span>
                </div>
                <div className="flex justify-between border-b border-line pb-1.5">
                  <span className="text-inkfaint">Valor declarado</span>
                  <span className="font-mono">USD {verDeclaracion.decl.valor_declarado.toLocaleString('es-GT')}</span>
                </div>
                <div>
                  <span className="text-inkfaint">Descripcion de la mercancia</span>
                  <p className="text-ink mt-1">{verDeclaracion.decl.descripcion_mercancia}</p>
                </div>
                {verDeclaracion.decl.observaciones && (
                  <div>
                    <span className="text-inkfaint">Observaciones del agente</span>
                    <p className="text-ink mt-1">{verDeclaracion.decl.observaciones}</p>
                  </div>
                )}
                <div className="text-inkfaint text-2xs">Presentada: {fmtFechaHora(verDeclaracion.decl.created_at)}</div>
              </>
            ) : (
              <p className="text-inkdim">
                Este manifiesto no tiene declaracion de mercancias registrada. El agente aduanero debe presentarla
                antes de poder resolver el levante.
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
