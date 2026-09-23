// Consumo del stream SSE /api/stream/events con EventSource nativo.
// El sinoptico se alimenta por suscripcion, jamas por polling a la base de datos.
import { useEffect, useRef, useState } from 'react'
import type { EstadoTerminal, EventoSSE } from '../types'

const ESTADO_INICIAL: EstadoTerminal = {
  modo: 'NORMAL',
  enlace: 'DESCONECTADO',
  ultimo_latido_timestamp: '',
  garita: { estado: 'Libre', vehiculo: null },
  talanquera: 'Cerrada',
  pesaje: { estado: 'Libre', ultimo_valor_kg: 0, resultado: 'Valido' },
  aguja: 'Recta',
  parqueo: {},
  transferencia: { estado: 'Libre', vehiculo: null },
  grua: {
    estado: 'En reposo',
    posicion: 0,
    trabajo_en_curso: null,
    cola_pendientes: 0,
    suspendida: false,
    referenciada: true,
    en_falla: false,
  },
  puerta_salida: 'Cerrada',
  zona_espera: { cantidad_vehiculos: 0 },
}

export interface SinopticoStream {
  estado: EstadoTerminal
  ultimoEvento: EventoSSE | null
  conectado: boolean
  ultimoMensajeEn: Date | null
}

export function useSinopticoStream(): SinopticoStream {
  const [estado, setEstado] = useState<EstadoTerminal>(ESTADO_INICIAL)
  const [ultimoEvento, setUltimoEvento] = useState<EventoSSE | null>(null)
  const [conectado, setConectado] = useState(false)
  const [ultimoMensajeEn, setUltimoMensajeEn] = useState<Date | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const es = new EventSource('/api/stream/events', { withCredentials: true })
    esRef.current = es

    es.onopen = () => setConectado(true)
    es.onerror = () => setConectado(false)

    es.onmessage = (ev: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(ev.data) as EventoSSE
        if (parsed.state) setEstado(parsed.state)
        setUltimoEvento(parsed)
        setUltimoMensajeEn(new Date())
        setConectado(true)
      } catch {
        // keepalive en comentarios SSE no llega a onmessage; si el payload
        // no es JSON valido se ignora sin romper el stream.
      }
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [])

  return { estado, ultimoEvento, conectado, ultimoMensajeEn }
}
