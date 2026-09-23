// Rutas de la SPA. Proteccion por rol en cliente; el servidor sigue aplicando
// la matriz de permisos real sobre cada endpoint.
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import { Spinner } from './components/ui'
import AppShell from './layout/AppShell'
import LoginPage from './pages/LoginPage'
import OperacionPage from './pages/terminal/OperacionPage'
import TurnosPage from './pages/terminal/TurnosPage'
import RetencionesPage from './pages/terminal/RetencionesPage'
import PatioPage from './pages/terminal/PatioPage'
import GruaPage from './pages/terminal/GruaPage'
import AlarmasPage from './pages/terminal/AlarmasPage'
import CitasPage from './pages/terminal/CitasPage'
import ReportesPage from './pages/terminal/ReportesPage'
import ManifiestosPage from './pages/naviera/ManifiestosPage'
import MisContenedoresPage from './pages/naviera/MisContenedoresPage'
import DeclaracionesPage from './pages/agente/DeclaracionesPage'
import SeguimientoPage from './pages/agente/SeguimientoPage'
import LevantePage from './pages/autoridad/LevantePage'
import RetencionesAduanerasPage from './pages/autoridad/RetencionesAduanerasPage'
import ConsultaCargaPage from './pages/autoridad/ConsultaCargaPage'

const RUTA_POR_ROL: Record<string, string> = {
  TERMINAL: '/terminal/operacion',
  NAVIERA: '/naviera/manifiestos',
  AGENTE: '/agente/declaraciones',
  AUTORIDAD: '/autoridad/levante',
}

function Protegida({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const { user, cargando } = useAuth()
  const location = useLocation()

  if (cargando) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-base">
        <Spinner size={26} />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (!roles.includes(user.rol)) return <Navigate to={RUTA_POR_ROL[user.rol] || '/login'} replace />
  return <>{children}</>
}

export default function App() {
  const { user, cargando } = useAuth()

  if (cargando) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-base">
        <Spinner size={26} />
      </div>
    )
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to={RUTA_POR_ROL[user.rol] || '/'} replace /> : <LoginPage />}
      />

      <Route
        path="/terminal"
        element={
          <Protegida roles={['TERMINAL']}>
            <AppShell />
          </Protegida>
        }
      >
        <Route index element={<Navigate to="operacion" replace />} />
        <Route path="operacion" element={<OperacionPage />} />
        <Route path="turnos" element={<TurnosPage />} />
        <Route path="retenciones" element={<RetencionesPage />} />
        <Route path="patio" element={<PatioPage />} />
        <Route path="grua" element={<GruaPage />} />
        <Route path="alarmas" element={<AlarmasPage />} />
        <Route path="citas" element={<CitasPage />} />
        <Route path="reportes" element={<ReportesPage />} />
      </Route>

      <Route
        path="/naviera"
        element={
          <Protegida roles={['NAVIERA']}>
            <AppShell />
          </Protegida>
        }
      >
        <Route index element={<Navigate to="manifiestos" replace />} />
        <Route path="manifiestos" element={<ManifiestosPage />} />
        <Route path="contenedores" element={<MisContenedoresPage />} />
      </Route>

      <Route
        path="/agente"
        element={
          <Protegida roles={['AGENTE']}>
            <AppShell />
          </Protegida>
        }
      >
        <Route index element={<Navigate to="declaraciones" replace />} />
        <Route path="declaraciones" element={<DeclaracionesPage />} />
        <Route path="seguimiento" element={<SeguimientoPage />} />
      </Route>

      <Route
        path="/autoridad"
        element={
          <Protegida roles={['AUTORIDAD']}>
            <AppShell />
          </Protegida>
        }
      >
        <Route index element={<Navigate to="levante" replace />} />
        <Route path="levante" element={<LevantePage />} />
        <Route path="retenciones" element={<RetencionesAduanerasPage />} />
        <Route path="consulta" element={<ConsultaCargaPage />} />
      </Route>

      <Route path="*" element={<Navigate to={user ? RUTA_POR_ROL[user.rol] || '/' : '/login'} replace />} />
    </Routes>
  )
}
