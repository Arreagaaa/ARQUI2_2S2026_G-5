// Wrapper delgado sobre fetch nativo. Sesiones por cookie de Flask, por eso
// credentials: 'include' en todas las llamadas.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })

  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('application/json')) {
    if (!res.ok) throw new ApiError(res.status, `Error ${res.status} del servidor`)
    return (await res.text()) as unknown as T
  }

  const body = await res.json()
  if (!res.ok) {
    throw new ApiError(res.status, body?.error || `Error ${res.status}`)
  }
  return body as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(data ?? {}) }),
}

// Descarga de archivo (CSV de reportes): el backend devuelve text/csv.
export async function downloadFile(path: string, data?: unknown, fallbackName = 'reporte.csv') {
  const res = await fetch(path, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data ?? {}),
  })
  if (!res.ok) {
    let msg = `Error ${res.status}`
    try {
      const j = await res.json()
      msg = j.error || msg
    } catch {
      /* el cuerpo no es JSON */
    }
    throw new ApiError(res.status, msg)
  }
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') || ''
  const match = cd.match(/filename="?([^"]+)"?/)
  const name = match ? match[1] : fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
