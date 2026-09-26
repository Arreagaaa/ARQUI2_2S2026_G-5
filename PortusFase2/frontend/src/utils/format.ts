// Helpers de formato compartidos por todas las pantallas.

export function fmtFechaHora(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('es-GT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    return iso
  }
}

export function fmtHora(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  } catch {
    return iso
  }
}

export function fmtSegundos(seg: number | null | undefined): string {
  if (seg == null) return '-'
  const s = Math.max(0, Math.floor(seg))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${r}s`
  return `${r}s`
}

export function fmtMinutos(min: number | null | undefined): string {
  if (min == null) return '-'
  const abs = Math.abs(min)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function fmtKg(gramos: number | null | undefined): string {
  if (gramos == null) return '-'
  return `${(gramos / 1000).toFixed(2)} kg`
}

export function fmtPesoCrudo(gramos: number | null | undefined): string {
  if (gramos == null) return '-'
  return `${gramos.toLocaleString('es-GT')} g`
}

export function hoyISO(): string {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
}

export function minutosATexto(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
