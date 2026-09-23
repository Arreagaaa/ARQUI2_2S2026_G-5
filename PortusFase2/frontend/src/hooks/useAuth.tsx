// Sesion de la aplicacion. La validez de la sesion vive en la cookie de Flask;
// aqui solo se refleja el usuario devuelto por /api/me o /api/login.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { login as apiLogin, logout as apiLogout, me as apiMe } from '../api/endpoints'
import type { Usuario } from '../types'

interface AuthContextValue {
  user: Usuario | null
  cargando: boolean
  error: string | null
  login: (username: string, password: string) => Promise<Usuario>
  logout: () => Promise<void>
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiMe()
      .then((res) => setUser(res.user))
      .catch(() => setUser(null))
      .finally(() => setCargando(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setError(null)
    const res = await apiLogin(username, password)
    setUser(res.user)
    return res.user
  }, [])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, cargando, error, login, logout, clearError: () => setError(null) }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider')
  return ctx
}
