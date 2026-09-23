// Endpoints REST del backend Flask. Cada funcion corresponde a una ruta
// existente en PortusFase2/server/app.py (los GET /api/me, /api/transportistas,
// /api/catalogo/contenedores y /api/declaraciones se agregaron de forma aditiva).
import { api, downloadFile } from './client'
import type {
  AlarmasResponse,
  CausaRetencion,
  CatalogoContenedor,
  CicloGrua,
  Cita,
  Declaracion,
  EstadoTurno,
  EventoTimeline,
  Manifiesto,
  Metricas,
  Retencion,
  CeldaPatio,
  TransportistaInfo,
  Turno,
  Usuario,
} from '../types'

// Auth
export const login = (username: string, password: string) =>
  api.post<{ success: boolean; user: Usuario }>('/api/login', { username, password })

export const logout = () =>
  fetch('/api/logout', {
    credentials: 'include',
    headers: { Accept: 'application/json' },
    redirect: 'manual',
  })

export const me = () => api.get<{ user: Usuario | null }>('/api/me')

// Catalogos
export const listTransportistas = () => api.get<{ transportistas: TransportistaInfo[] }>('/api/transportistas')
export const listCatalogoContenedores = () => api.get<{ contenedores: CatalogoContenedor[] }>('/api/catalogo/contenedores')

// Manifiestos
export const listManifiestos = () => api.get<Manifiesto[]>('/api/manifiestos')
export const createManifiesto = (data: {
  contenedor_id: string
  tipo_operacion: string
  peso_declarado: number
  tolerancia?: number
  transportista_id: string
  observaciones?: string
}) => api.post<{ success: boolean; id: string; message: string }>('/api/manifiestos', data)
export const anularManifiesto = (id: string) =>
  api.post<{ success: boolean; message: string }>(`/api/manifiestos/${id}/anular`)

// Declaraciones
export const listDeclaraciones = (manifiestoId?: string) =>
  api.get<Declaracion[]>(`/api/declaraciones${manifiestoId ? `?manifiesto_id=${manifiestoId}` : ''}`)
export const createDeclaracion = (data: {
  manifiesto_id: string
  numero_declaracion: string
  regimen: string
  descripcion_mercancia: string
  valor_declarado: number
  observaciones?: string
}) => api.post<{ success: boolean; message: string }>('/api/declaraciones', data)
export const solicitarLevante = (manifiesto_id: string) =>
  api.post<{ success: boolean; message: string }>('/api/declaraciones/solicitar-levante', { manifiesto_id })
export const resolverLevante = (data: {
  manifiesto_id: string
  decision: 'OTORGAR' | 'RETENER'
  canal?: 'VERDE' | 'ROJO'
  motivo?: string
}) => api.post<{ success: boolean; message: string }>('/api/autoridad/resolver-levante', data)

// Turnos
export const listTurnos = (params?: { estado?: string; tipo?: string; q?: string }) => {
  const qs = new URLSearchParams()
  if (params?.estado) qs.set('estado', params.estado)
  if (params?.tipo) qs.set('tipo', params.tipo)
  if (params?.q) qs.set('q', params.q)
  const suffix = qs.toString() ? `?${qs}` : ''
  return api.get<Turno[]>(`/api/turnos${suffix}`)
}
export const getTimeline = (turnoId: number) => api.get<EventoTimeline[]>(`/api/turnos/${turnoId}/timeline`)
export const retenerTurno = (turnoId: number, observacion?: string) =>
  api.post<{ success: boolean; retencion: unknown; message: string }>(
    `/api/turnos/${turnoId}/retener-manual`,
    { observacion },
  )
export const anularTurno = (turnoId: number) =>
  api.post<{ success: boolean; message: string }>(`/api/turnos/${turnoId}/anular`)

// Retenciones
export const listRetenciones = (params?: { estado?: string; causa?: CausaRetencion }) => {
  const qs = new URLSearchParams()
  if (params?.estado) qs.set('estado', params.estado)
  if (params?.causa) qs.set('causa', params.causa)
  const suffix = qs.toString() ? `?${qs}` : ''
  return api.get<Retencion[]>(`/api/retenciones${suffix}`)
}
export const resolverRetencion = (
  id: number,
  data: { resolucion: 'ACLARAR' | 'CORREGIR' | 'RECHAZAR'; motivo_rechazo?: string; observacion?: string },
) => api.post<{ success?: boolean; error?: string; plaza_liberada?: number }>(`/api/retenciones/${id}/resolver`, data)

// Patio y grua
export const listPatio = () => api.get<CeldaPatio[]>('/api/patio')
export const bloquearPosicion = (pos: number) => api.post<{ success: boolean }>(`/api/patio/posicion/${pos}/bloquear`)
export const liberarPosicion = (pos: number) => api.post<{ success: boolean }>(`/api/patio/posicion/${pos}/liberar`)
export const historialGrua = (limit = 50) => api.get<CicloGrua[]>(`/api/grua/historial?limit=${limit}`)

// Alarmas
export const listAlarmas = (severidad?: string) =>
  api.get<AlarmasResponse>(`/api/alarmas${severidad ? `?severidad=${severidad}` : ''}`)
export const reconocerAlarma = (id: number, comentario?: string) =>
  api.post<{ success: boolean }>(`/api/alarmas/${id}/reconocer`, { comentario })
export const reconocerTodas = () => api.post<{ success: boolean; reconocidas: number }>('/api/alarmas/reconocer-todas')

// Citas
export const listCitas = (fecha: string) => api.get<Cita[]>(`/api/citas?fecha=${fecha}`)

// Comandos remotos
export const comandoRemoto = (comando: string, parametros: Record<string, unknown> = {}) =>
  api.post<{ success: boolean; message: string }>('/api/cmd/remote', { comando, parametros })

// Reportes
export const calcularReporte = (inicio?: string, fin?: string) => {
  const qs = new URLSearchParams()
  if (inicio) qs.set('inicio', inicio)
  if (fin) qs.set('fin', fin)
  const suffix = qs.toString() ? `?${qs}` : ''
  return api.get<Metricas>(`/api/reportes/calcular${suffix}`)
}
export const exportarReporte = (etiqueta: string, inicio?: string, fin?: string) =>
  downloadFile('/api/reportes/exportar-csv', { etiqueta, inicio, fin }, 'reporte_corrida.csv')

// Vinculacion de transportista
export const generarCodigoVinculacion = (transportista_id: string) =>
  api.post<{ success: boolean; codigo: string; expira_en_minutos: number }>(
    '/api/transportista/generar-codigo',
    { transportista_id },
  )

export type { Turno, Manifiesto, Retencion, Cita, Declaracion, Metricas }
export type EstadoTurnoT = EstadoTurno
