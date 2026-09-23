// Carga generica de datos REST con estados de carga y error para cada pantalla.
import { useCallback, useEffect, useState } from 'react'

interface UseApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): UseApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    setError(null)
    fetcher()
      .then((res) => {
        if (!cancelado) setData(res)
      })
      .catch((err: Error) => {
        if (!cancelado) setError(err.message || 'No se pudo cargar la informacion')
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, loading, error, reload }
}
