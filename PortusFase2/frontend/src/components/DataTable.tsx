// Tabla de datos compacta con estados de carga, error y vacio.
// Los filtros los maneja cada pantalla y se pasan via `toolbar`.
import type { ReactNode } from 'react'
import { EmptyState, ErrorState, Skeleton } from './ui'

export interface Columna<T> {
  clave: string
  encabezado: string
  render: (fila: T) => ReactNode
  className?: string
  ocultaEn?: 'mobile' | 'tablet' // oculta en pantallas chicas
}

export function DataTable<T>({
  columnas,
  filas,
  claveFila,
  loading,
  error,
  onRetry,
  toolbar,
  vacio = 'No hay registros para mostrar.',
  onFilaClick,
  filaActiva,
}: {
  columnas: Columna<T>[]
  filas: T[]
  claveFila: (fila: T) => string | number
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  toolbar?: ReactNode
  vacio?: string
  onFilaClick?: (fila: T) => void
  filaActiva?: (fila: T) => boolean
}) {
  if (loading) return <Skeleton rows={5} />
  if (error) return <ErrorState mensaje={error} onRetry={onRetry} />
  if (filas.length === 0) return <div className="space-y-3">{toolbar}<EmptyState mensaje={vacio} /></div>

  const claseCol = (c: Columna<T>) =>
    `${c.className || ''} ${c.ocultaEn === 'mobile' ? 'hidden sm:table-cell' : ''} ${
      c.ocultaEn === 'tablet' ? 'hidden md:table-cell' : ''
    }`

  return (
    <div className="space-y-3">
      {toolbar && <div className="flex flex-wrap items-end gap-2">{toolbar}</div>}
      <div className="border border-line rounded overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-surface2 text-left">
                {columnas.map((c) => (
                  <th key={c.clave} className={`px-3 py-2 font-medium text-inkfaint uppercase text-2xs tracking-wider ${claseCol(c)}`}>
                    {c.encabezado}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr
                  key={claveFila(f)}
                  onClick={onFilaClick ? () => onFilaClick(f) : undefined}
                  className={`border-t border-line transition-colors ${
                    onFilaClick ? 'cursor-pointer hover:bg-surface2' : ''
                  } ${filaActiva?.(f) ? 'bg-accent-soft' : ''}`}
                >
                  {columnas.map((c) => (
                    <td key={c.clave} className={`px-3 py-2 text-inkdim align-middle ${claseCol(c)}`}>
                      {c.render(f)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
