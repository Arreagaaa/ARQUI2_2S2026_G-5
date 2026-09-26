// Consumo del stream SSE /api/stream/events con EventSource nativo.
// El sinoptico se alimenta por suscripcion, jamas por polling a la base de datos.
import { useEffect, useRef, useState } from 'react'
import type { EstadoTerminal, EventoSSE } from '../types'

const ESTADO_INICIAL: EstadoTerminal = {
  modo: 'DESCONOCIDO',
  enlace: 'DESCONECTADO',
  ultimo_latido_timestamp: '',
  garita: { estado: 'Libre', vehiculo: null },
  talanquera: 'Cerrada',
  pesaje: { estado: 'Libre', ultimo_valor_kg: null, resultado: 'Sin confirmar' },
  aguja: 'Recta',
  parqueo: {},
  transferencia: { estado: 'Libre', vehiculo: null },
  grua: {
    estado: 'Sin confirmar',
    posicion: null,
    trabajo_en_curso: null,
    cola_pendientes: null,
    suspendida: false,
    referenciada: null,
    en_falla: false,
  },
  puerta_salida: 'Cerrada',
  zona_espera: { cantidad_vehiculos: null },
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
        if (parsed.state) setEstado((previous) => ({ ...previous, ...parsed.state }))
        if (parsed.data?.tipo !== 'PesajeEnVivo' && parsed.data?.tipo !== 'Latido') window.dispatchEvent(new Event('portus:refresh'))
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
