// Shared SSE invalidation for every role and every mounted REST view.
import { useCallback, useEffect, useRef, useState } from 'react'

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const fetchRef = useRef(fetcher)
  fetchRef.current = fetcher
  const reloadRef = useRef<() => void>(() => {})
  const reload = useCallback(() => reloadRef.current(), [])
  useEffect(() => {
    let disposed = false, running = false, dirty = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const run = async () => {
      timer = undefined
      if (running) { dirty = true; return }
      running = true
      try {
        const result = await fetchRef.current()
        if (!disposed) { setData(result); setError(null) }
      } catch (err) {
        if (!disposed) setError(err instanceof Error ? err.message : 'No se pudo cargar la informacion')
      } finally {
        running = false
        if (!disposed) {
          setLoading(false)
          if (dirty) { dirty = false; schedule() }
        }
      }
    }
    const schedule = () => {
      if (!disposed && timer === undefined) timer = setTimeout(run, 400)
    }
    reloadRef.current = schedule
    setLoading(true)
    void run()
    window.addEventListener('portus:refresh', schedule)
    return () => {
      disposed = true
      clearTimeout(timer)
      window.removeEventListener('portus:refresh', schedule)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, loading, error, reload }
}
