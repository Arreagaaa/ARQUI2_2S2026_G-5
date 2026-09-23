// Tipos espejo de los payloads que devuelve el backend Flask (server/app.py,
// database.py y managers). Se mantienen sincronizados con el contrato JSON real.

export type Rol = 'TERMINAL' | 'NAVIERA' | 'AGENTE' | 'AUTORIDAD' | 'TRANSPORTISTA'

export interface Usuario {
  id: number
  username: string
  nombre_completo: string
  rol: Rol
}

export interface Manifiesto {
  id: string
  contenedor_id: string
  naviera_id: string
  tipo_operacion: 'DEPOSITO' | 'RETIRO'
  peso_declarado_g: number
  tolerancia_pct: number
  transportista_id: string
  observaciones: string | null
  estado_documental: EstadoDocumental
  canal_selectivo: 'VERDE' | 'ROJO' | null
  historial_pesos: string
  created_at: string
  updated_at: string
}

export type EstadoDocumental =
  | 'CREADO'
  | 'DECLARADO'
  | 'LEVANTE_SOLICITADO'
  | 'LEVANTE_OTORGADO'
  | 'LEVANTE_RETENIDO'
  | 'CERRADO'
  | 'ANULADO'

export interface Declaracion {
  id: number
  numero_declaracion: string
  manifiesto_id: string
  agente_id: string
  regimen: string
  descripcion_mercancia: string
  valor_declarado: number
  observaciones: string | null
  created_at: string
}

export type EstadoTurno =
  | 'Programado'
  | 'EnGarita'
  | 'EnPesajeEntrada'
  | 'EnRuta'
  | 'EnTransferencia'
  | 'EnPesajeSalida'
  | 'EnSalida'
  | 'Retenido'
  | 'Cerrado'
  | 'Anulado'

export interface Turno {
  id: number
  codigo_turno: string
  placa_vehiculo: string
  transportista_id: string
  contenedor_id: string
  manifiesto_id: string | null
  cita_id: number | null
  tipo_operacion: 'DEPOSITO' | 'RETIRO'
  estado_actual: EstadoTurno
  estado_previo_retencion: string | null
  estacion_actual: string
  peso_declarado_g: number | null
  peso_medido_entrada_g: number | null
  peso_medido_salida_g: number | null
  posicion_patio_asignada: number | null
  nivel_patio_asignado: number | null
  tiempo_inicio: string
  tiempo_fin: string | null
  tiempo_total_seg: number
  tiempo_transcurrido_min: number
}

export interface EventoTimeline {
  id: number
  turno_id: number
  timestamp: string
  origen: 'controlador' | 'servidor' | 'usuario'
  descripcion: string
  valores_asociados: string | null
}

export type CausaRetencion = 'RT01' | 'RT02' | 'RT03' | 'RT04' | 'RT05' | 'RT06'

export interface Retencion {
  id: number
  codigo_retencion: string
  turno_id: number
  vehiculo_placa: string
  contenedor_id: string
  causa: CausaRetencion
  estacion: string
  plaza_numero: number
  tiempo_inicio: string
  tiempo_resolucion: string | null
  tiempo_retencion_seg: number
  estado: 'ABIERTA' | 'RESUELTA'
  peso_declarado_g: number | null
  peso_medido_g: number | null
  diferencia_abs_g: number | null
  diferencia_pct: number | null
  rol_facultado: Rol
  tipo_resolucion: 'ACLARAR' | 'CORREGIR' | 'RECHAZAR' | null
  motivo_rechazo: string | null
  observacion: string | null
  resuelto_por: string | null
  codigo_turno: string
  placa_vehiculo: string
  transportista_id: string
  tiempo_retencion_min: number
}

export interface CeldaPatio {
  posicion: number
  nivel: number
  contenedor_id: string | null
  naviera_id: string | null
  peso_declarado_g: number | null
  estado_autorizacion: string
  bloqueada: number
  ingreso_at: string | null
  remociones: number
  permanencia_min: number
  permanencia_str: string
  permanencia_excesiva: boolean
}

export interface CicloGrua {
  id: number
  turno_id: number | null
  tipo_trabajo: string
  posicion_origen: number
  posicion_destino: number
  tiempo_ciclo_seg: number
  distancia_recorrida_mm: number
  exitoso: number
  evento_falla: string | null
  timestamp: string
}

export type Severidad = 'Critica' | 'Alta' | 'Media' | 'Baja'

export interface Alarma {
  id: number
  codigo: string
  severidad: Severidad
  descripcion: string
  origen: string
  datos_asociados: string | null
  reconocida: number
  reconocida_por: string | null
  reconocida_en: string | null
  comentario_reconocimiento: string | null
  timestamp: string
}

export interface AlarmasResponse {
  activas: Alarma[]
  historicas: Alarma[]
}

export interface Cita {
  id: number
  transportista_id: string
  contenedor_id: string
  manifiesto_id: string
  fecha: string
  hora_inicio: string
  hora_fin: string
  estado: 'PROGRAMADA' | 'CUMPLIDA' | 'VENCIDA' | 'CANCELADA'
  cumplida_en_ventana: number
  created_at: string
}

export interface Metricas {
  remociones_por_contenedor_retirado: number
  ciclos_grua_por_operacion: number
  distancia_total_grua_m: number
  tiempo_promedio_camion_seg: number
  tiempo_promedio_camion_min: number
  tiempo_promedio_retencion_seg: number
  tiempo_promedio_retencion_min: number
  longitud_maxima_fila_espera: number
  porcentaje_citas_cumplidas_ventana: number
  retenciones_desglose: { causa: string; resolucion: string; cantidad: number }[]
  resumen_conteos: {
    turnos_cerrados: number
    retiros_completados: number
    total_ciclos_grua: number
    total_citas: number
    citas_en_ventana: number
  }
}

// Estado general de la maqueta que llega embebido en cada evento SSE
// (campo "state" de app.py: terminal_state).
export interface EstadoTerminal {
  modo: string
  enlace: string
  ultimo_latido_timestamp: string
  garita: { estado: string; vehiculo: string | null }
  talanquera: string
  pesaje: { estado: string; ultimo_valor_kg: number; resultado: string }
  aguja: string
  parqueo: Record<string, unknown>
  transferencia: { estado: string; vehiculo: string | null }
  grua: {
    estado: string
    posicion: number
    trabajo_en_curso: string | null
    cola_pendientes: number
    suspendida: boolean
    referenciada: boolean
    en_falla: boolean
  }
  puerta_salida: string
  zona_espera: { cantidad_vehiculos: number }
}

export interface EventoSSE {
  topic: string
  data?: {
    id?: string
    timestamp?: string
    origen?: string
    tipo?: string
    datos?: Record<string, unknown>
    comando?: string
    parametros?: Record<string, unknown>
  }
  state: EstadoTerminal
}

export interface CatalogoContenedor {
  id: string
  tipo: string
  tara_g: number
}

export interface TransportistaInfo {
  username: string
  nombre_completo: string
}
