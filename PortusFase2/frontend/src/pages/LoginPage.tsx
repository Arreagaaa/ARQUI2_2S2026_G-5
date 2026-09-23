// Pantalla de acceso. POST /api/login con la sesion por cookie de Flask.
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Anchor, Lock, User } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { FormField, Spinner } from '../components/ui'

const RUTA_POR_ROL: Record<string, string> = {
  TERMINAL: '/terminal/operacion',
  NAVIERA: '/naviera/manifiestos',
  AGENTE: '/agente/declaraciones',
  AUTORIDAD: '/autoridad/levante',
}

export default function LoginPage() {
  const { user, cargando, login, error } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [errorLocal, setErrorLocal] = useState<string | null>(null)

  if (cargando) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-base">
        <Spinner size={26} />
      </div>
    )
  }
  if (user) return <Navigate to={RUTA_POR_ROL[user.rol] || '/'} replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setErrorLocal('Ingrese usuario y contrasena.')
      return
    }
    setEnviando(true)
    setErrorLocal(null)
    try {
      const u = await login(username.trim(), password)
      navigate(RUTA_POR_ROL[u.rol] || '/', { replace: true })
    } catch (err) {
      setErrorLocal(err instanceof Error ? err.message : 'No se pudo iniciar sesion.')
    } finally {
      setEnviando(false)
    }
  }

  const mensajeError = errorLocal || error

  return (
    <div className="min-h-screen bg-base flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        {/* Marca */}
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 rounded bg-accent flex items-center justify-center mb-3">
            <Anchor size={26} className="text-base" />
          </div>
          <h1 className="text-xl font-bold tracking-[0.25em] text-ink">PORTUS</h1>
          <p className="text-xs text-inkfaint mt-1 tracking-wider">TERMINAL PORTUARIA - FASE 2</p>
        </div>

        <form
          onSubmit={onSubmit}
          className="bg-surface border border-line rounded p-5 shadow-panel space-y-4"
        >
          <div className="border-b border-line pb-3">
            <h2 className="text-sm font-semibold text-ink">Inicio de sesion</h2>
            <p className="text-2xs text-inkfaint mt-0.5">Acceso exclusivo para operadores de la terminal.</p>
          </div>

          <FormField label="Usuario" required>
            <div className="relative">
              <User size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-inkfaint" />
              <input
                className="input pl-8 font-mono"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                placeholder="operador1"
              />
            </div>
          </FormField>

          <FormField label="Contrasena" required>
            <div className="relative">
              <Lock size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-inkfaint" />
              <input
                className="input pl-8"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="********"
              />
            </div>
          </FormField>

          {mensajeError && (
            <div className="border border-danger/40 bg-danger-soft text-danger text-xs rounded px-3 py-2" role="alert">
              {mensajeError}
            </div>
          )}

          <button type="submit" className="btn-primary w-full !py-2" disabled={enviando}>
            {enviando ? <Spinner size={14} /> : null}
            {enviando ? 'Verificando...' : 'Ingresar'}
          </button>
        </form>

        <p className="text-2xs text-inkfaint text-center mt-4 leading-relaxed">
          El rol TRANSPORTISTA opera exclusivamente desde el canal de mensajeria
          <br />y no posee acceso a esta aplicacion.
        </p>
      </div>
    </div>
  )
}
