// Mapa invariante de colores de estado. El mismo significado en cualquier pestaña:
// verde = activo/autorizado/libre, ambar = en proceso/atencion, rojo = rechazado/
// critico/cerrado malo, gris = inactivo/desconocido, cian = acento de interfaz.
import type { Severidad } from '../types'

export type EstadoColor = 'ok' | 'warn' | 'danger' | 'neutral' | 'accent'

const CLASES: Record<EstadoColor, string> = {
  ok: 'bg-ok-soft text-ok border-ok/30',
  warn: 'bg-warn-soft text-warn border-warn/30',
  danger: 'bg-danger-soft text-danger border-danger/30',
  neutral: 'bg-neutral-soft text-inkdim border-line',
  accent: 'bg-accent-soft text-accent border-accent/30',
}

export function badgeClass(color: EstadoColor): string {
  return `inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-medium ${CLASES[color]}`
}

// Estados de turno (maquina de 10 estados)
export function colorTurno(estado: string): EstadoColor {
  switch (estado) {
    case 'Cerrado':
      return 'ok'
    case 'Retenido':
      return 'warn'
    case 'Anulado':
      return 'danger'
    case 'Programado':
      return 'neutral'
    default:
      return 'accent' // en curso
  }
}

// Estados documentales de manifiesto
export function colorDocumento(estado: string): EstadoColor {
  switch (estado) {
    case 'LEVANTE_OTORGADO':
      return 'ok'
    case 'LEVANTE_RETENIDO':
      return 'danger'
    case 'LEVANTE_SOLICITADO':
      return 'warn'
    case 'ANULADO':
      return 'neutral'
    default:
      return 'accent'
  }
}

export function colorSeveridad(sev: Severidad | string): EstadoColor {
  switch (sev) {
    case 'Critica':
    case 'Alta':
      return 'danger'
    case 'Media':
      return 'warn'
    default:
      return 'neutral'
  }
}

// Elementos del sinoptico
export function colorGarita(estado: string): EstadoColor {
  const e = estado.toLowerCase()
  if (e.includes('rechaz')) return 'danger'
  if (e.includes('valid')) return 'warn'
  if (e.includes('autoriz')) return 'ok'
  return 'neutral'
}

export function colorPuerta(estado: string): EstadoColor {
  const e = estado.toLowerCase()
  if (e.includes('abiert')) return 'ok'
  if (e.includes('movim')) return 'warn'
  return 'neutral'
}

export function colorAguja(estado: string): EstadoColor {
  const e = estado.toLowerCase()
  if (e.includes('parqueo') && !e.includes('liber')) return 'warn'
  if (e.includes('liber')) return 'accent'
  return 'ok' // recta
}

export function colorPesaje(estado: string): EstadoColor {
  const e = estado.toLowerCase()
  if (e.includes('fuera') || e.includes('tolerancia')) return 'danger'
  if (e.includes('mid') || e.includes('medicion')) return 'accent'
  return 'neutral'
}

export function colorCita(estado: string): EstadoColor {
  switch (estado) {
    case 'CUMPLIDA':
      return 'ok'
    case 'VENCIDA':
      return 'danger'
    case 'CANCELADA':
      return 'neutral'
    default:
      return 'accent'
  }
}

export function colorCanal(canal: string | null | undefined): EstadoColor {
  if (canal === 'VERDE') return 'ok'
  if (canal === 'ROJO') return 'danger'
  return 'neutral'
}

export function colorRetencion(estado: string): EstadoColor {
  return estado === 'ABIERTA' ? 'warn' : 'neutral'
}

// Etiquetas legibles en español para identificadores internos
export const ETIQUETAS_ESTADO_TURNO: Record<string, string> = {
  Programado: 'Programado',
  EnGarita: 'En garita',
  EnPesajeEntrada: 'Pesaje entrada',
  EnRuta: 'En ruta',
  EnTransferencia: 'En transferencia',
  EnPesajeSalida: 'Pesaje salida',
  EnSalida: 'En salida',
  Retenido: 'Retenido',
  Cerrado: 'Cerrado',
  Anulado: 'Anulado',
}

export const ETIQUETAS_CAUSA: Record<string, string> = {
  RT01: 'Discrepancia de peso al ingreso',
  RT02: 'Discrepancia de peso a la salida',
  RT03: 'Canal rojo de selectivo',
  RT04: 'Llegada fuera de la ventana asignada',
  RT05: 'Retencion documental',
  RT06: 'Retencion manual operativa',
}

export const ETIQUETAS_RESOLUCION: Record<string, string> = {
  ACLARAR: 'Aclarar',
  CORREGIR: 'Corregir',
  RECHAZAR: 'Rechazar',
}

export const ETIQUETAS_ROL: Record<string, string> = {
  TERMINAL: 'Terminal',
  NAVIERA: 'Naviera',
  AGENTE: 'Agente aduanero',
  AUTORIDAD: 'Autoridad aduanera',
  TRANSPORTISTA: 'Transportista',
}
