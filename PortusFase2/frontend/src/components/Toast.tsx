// Sistema de avisos temporales (exito / error / info) para respuestas de acciones.
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { AlertBanner } from './ui'

type TipoToast = 'exito' | 'error' | 'info'
interface Toast {
  id: number
  tipo: TipoToast
  mensaje: string
}

interface ToastContextValue {
  push: (tipo: TipoToast, mensaje: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let contador = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((tipo: TipoToast, mensaje: string) => {
    const id = ++contador
    setToasts((prev) => [...prev.slice(-2), { id, tipo, mensaje }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000)
  }, [])

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[min(420px,calc(100vw-2rem))]">
        {toasts.map((t) => (
          <AlertBanner
            key={t.id}
            tipo={t.tipo}
            mensaje={t.mensaje}
            onCerrar={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast debe usarse dentro de ToastProvider')
  return ctx
}
