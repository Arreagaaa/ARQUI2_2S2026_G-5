// Componentes base reutilizados en las 15 pantallas.
import { useEffect, type ReactNode } from 'react'
import { X, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { badgeClass, type EstadoColor } from '../utils/status'

// ---------------------------------------------------------------- Panel
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = '',
  bodyClassName = '',
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`bg-surface border border-line rounded shadow-panel ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink truncate">{title}</h2>}
            {subtitle && <p className="text-2xs text-inkfaint mt-0.5 truncate">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName || 'p-4'}>{children}</div>
    </section>
  )
}

// ---------------------------------------------------------------- Badge de estado
export function StatusBadge({ color, children }: { color: EstadoColor; children: ReactNode }) {
  return <span className={badgeClass(color)}>{children}</span>
}

// ---------------------------------------------------------------- Identificador tecnico
export function MonoId({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-xs ${className}`}>{children}</span>
}

// ---------------------------------------------------------------- Carga
export function Skeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-busy="true" aria-label="Cargando">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-8 bg-surface2 border border-line rounded animate-pulse" />
      ))}
    </div>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block border-2 border-line border-t-accent rounded-full animate-spin"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Cargando"
    />
  )
}

// ---------------------------------------------------------------- Estados vacios / error
export function EmptyState({ mensaje, icon }: { mensaje: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <div className="text-inkfaint mb-2">{icon || <Info size={22} />}</div>
      <p className="text-xs text-inkdim max-w-sm">{mensaje}</p>
    </div>
  )
}

export function ErrorState({ mensaje, onRetry }: { mensaje: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
      <AlertTriangle size={22} className="text-danger" />
      <p className="text-xs text-inkdim max-w-md">{mensaje}</p>
      {onRetry && (
        <button type="button" className="btn-ghost" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Modal
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 'max-w-lg',
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  width?: string
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:p-8">
      <div
        className={`w-full ${width} bg-surface border border-line2 rounded shadow-modal`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-inkfaint hover:text-ink transition-colors"
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </header>
        <div className="p-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- Formulario
export function FormField({
  label,
  error,
  hint,
  required,
  children,
}: {
  label: string
  error?: string | null
  hint?: string
  required?: boolean
  children: ReactNode
}) {
  return (
    <div>
      <label className="label">
        {label}
        {required && <span className="text-danger ml-0.5">*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-2xs text-inkfaint mt-1">{hint}</p>}
      {error && <p className="text-2xs text-danger mt-1">{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------- Indicador de conexion en vivo
export function LiveIndicator({
  conectado,
  ultimoMensajeEn,
  etiqueta = 'Enlace',
}: {
  conectado: boolean
  ultimoMensajeEn: Date | null
  etiqueta?: string
}) {
  const hora = ultimoMensajeEn
    ? ultimoMensajeEn.toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    : 'sin eventos'
  return (
    <div
      className={`flex items-center gap-1.5 border rounded px-2 py-1 text-2xs font-medium ${
        conectado ? 'border-ok/30 text-ok bg-ok-soft' : 'border-danger/30 text-danger bg-danger-soft'
      }`}
      title={`${etiqueta}: ${conectado ? 'conectado' : 'desconectado'} - ultimo mensaje ${hora}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${conectado ? 'bg-ok animate-pulse' : 'bg-danger'}`} />
      <span className="hidden sm:inline">{conectado ? 'En vivo' : 'Sin enlace'}</span>
      <span className="font-mono text-2xs text-inkdim hidden md:inline">{hora}</span>
    </div>
  )
}

// ---------------------------------------------------------------- Banner de resultado
export function AlertBanner({
  tipo,
  mensaje,
  onCerrar,
}: {
  tipo: 'exito' | 'error' | 'info'
  mensaje: string
  onCerrar: () => void
}) {
  useEffect(() => {
    const t = setTimeout(onCerrar, 5000)
    return () => clearTimeout(t)
  }, [onCerrar])

  const estilo =
    tipo === 'exito'
      ? 'border-ok/40 text-ok bg-ok-soft'
      : tipo === 'error'
        ? 'border-danger/40 text-danger bg-danger-soft'
        : 'border-accent/40 text-accent bg-accent-soft'
  const Icono = tipo === 'exito' ? CheckCircle2 : tipo === 'error' ? AlertTriangle : Info

  return (
    <div className={`flex items-start gap-2 border rounded px-3 py-2 text-xs ${estilo}`} role="status">
      <Icono size={14} className="mt-0.5 shrink-0" />
      <span className="flex-1">{mensaje}</span>
      <button type="button" onClick={onCerrar} className="opacity-60 hover:opacity-100" aria-label="Cerrar aviso">
        <X size={13} />
      </button>
    </div>
  )
}
