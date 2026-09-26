// Estructura general: cabecera permanente con usuario y rol (requisito del
// enunciado), navegacion de pestañas por rol y area de contenido.
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Activity,
  Anchor,
  BarChart3,
  CalendarClock,
  ClipboardList,
  Container,
  FileCheck2,
  FileText,
  Forklift,
  LayoutGrid,
  LogOut,
  MapPin,
  Search,
  ShieldAlert,
  Ship,
  Truck,
  Warehouse,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useSinopticoStream } from '../hooks/useSinopticoStream'
import { LiveIndicator } from '../components/ui'
import { ETIQUETAS_ROL } from '../utils/status'
import type { Rol } from '../types'
import { ToastProvider } from '../components/Toast'

interface TabDef {
  ruta: string
  etiqueta: string
  icono: LucideIcon
}

const TABS: Record<Rol, TabDef[]> = {
  TERMINAL: [
    { ruta: 'operacion', etiqueta: 'Operacion', icono: Activity },
    { ruta: 'turnos', etiqueta: 'Turnos', icono: ClipboardList },
    { ruta: 'retenciones', etiqueta: 'Retenciones', icono: ShieldAlert },
    { ruta: 'patio', etiqueta: 'Patio', icono: Warehouse },
    { ruta: 'grua', etiqueta: 'Grua', icono: Forklift },
    { ruta: 'alarmas', etiqueta: 'Alarmas', icono: Anchor },
    { ruta: 'citas', etiqueta: 'Citas', icono: CalendarClock },
    { ruta: 'reportes', etiqueta: 'Reportes', icono: BarChart3 },
  ],
  NAVIERA: [
    { ruta: 'manifiestos', etiqueta: 'Manifiestos', icono: FileText },
    { ruta: 'contenedores', etiqueta: 'Mis contenedores', icono: Container },
  ],
  AGENTE: [
    { ruta: 'declaraciones', etiqueta: 'Declaraciones', icono: FileCheck2 },
    { ruta: 'seguimiento', etiqueta: 'Seguimiento', icono: MapPin },
  ],
  AUTORIDAD: [
    { ruta: 'levante', etiqueta: 'Solicitudes de levante', icono: FileCheck2 },
    { ruta: 'retenciones', etiqueta: 'Retenciones aduaneras', icono: ShieldAlert },
    { ruta: 'consulta', etiqueta: 'Consulta de carga', icono: Search },
  ],
  TRANSPORTISTA: [],
}

function Marca() {
  return (
    <div className="flex items-center gap-2 shrink-0">
      <div className="w-7 h-7 rounded bg-accent flex items-center justify-center">
        <Ship size={16} className="text-base" />
      </div>
      <div className="leading-none">
        <div className="text-sm font-bold tracking-widest text-ink">PORTUS</div>
        <div className="text-2xs text-inkfaint tracking-wider">TERMINAL PUERTO QUETZAL</div>
      </div>
    </div>
  )
}

export default function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const stream = useSinopticoStream()

  if (!user) return null
  const tabs = TABS[user.rol] || []

  const salir = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <ToastProvider>
      <div className="min-h-screen flex flex-col">
        {/* Cabecera: usuario y rol siempre visibles */}
        <header className="bg-surface border-b border-line sticky top-0 z-40">
          <div className="flex items-center justify-between gap-4 px-3 sm:px-4 h-13 py-2.5">
            <Marca />
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <span className="hidden lg:block">
                <LiveIndicator conectado={stream.conectado && stream.estado.enlace === 'CONECTADO'} ultimoMensajeEn={stream.ultimoMensajeEn} />
              </span>
              <div className="flex items-center gap-2 min-w-0 border-l border-line pl-2 sm:pl-3">
                <div className="text-right min-w-0 hidden sm:block">
                  <div className="text-xs font-medium text-ink truncate">{user.nombre_completo}</div>
                  <div className="text-2xs text-inkfaint font-mono">@{user.username}</div>
                </div>
                <span className="inline-flex items-center rounded border border-accent/40 bg-accent-soft px-1.5 py-0.5 text-2xs font-semibold text-accent tracking-wide">
                  {ETIQUETAS_ROL[user.rol] || user.rol}
                </span>
                <button
                  type="button"
                  onClick={salir}
                  className="btn-ghost !px-2"
                  title="Cerrar sesion"
                  aria-label="Cerrar sesion"
                >
                  <LogOut size={14} />
                </button>
              </div>
            </div>
          </div>

          {/* Pestañas del rol */}
          {tabs.length > 0 && (
            <nav className="flex overflow-x-auto border-t border-line px-1 sm:px-2" aria-label="Pestañas">
              {tabs.map((t) => {
                const Icono = t.icono
                return (
                  <NavLink
                    key={t.ruta}
                    to={t.ruta}
                    className={({ isActive }) =>
                      `flex items-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                        isActive
                          ? 'border-accent text-accent bg-accent-soft'
                          : 'border-transparent text-inkdim hover:text-ink hover:border-line2'
                      }`
                    }
                  >
                    <Icono size={14} />
                    {t.etiqueta}
                  </NavLink>
                )
              })}
            </nav>
          )}
        </header>

        <main className="flex-1 w-full max-w-[1600px] mx-auto px-3 sm:px-4 py-4">
          <Outlet context={{ stream }} />
        </main>

        <footer className="border-t border-line px-4 py-2 text-2xs text-inkfaint flex justify-between">
          <span>PORTUS Fase 2 - Plataforma de supervision y control</span>
          <span className="font-mono hidden sm:inline">USAC / Arquitectura de Computadoras y Ensambladores 2</span>
        </footer>
      </div>
    </ToastProvider>
  )
}
