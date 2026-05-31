import type { ServiceStatus, ServiceKind } from './types'

type ClassValue = string | number | false | null | undefined

/** clsx-like class joiner. */
export function cn(...classes: ClassValue[]): string {
  return classes.filter(Boolean).join(' ')
}

/** Human-friendly label for a service kind. */
export function prettyKind(kind: ServiceKind | string): string {
  switch (kind) {
    case 'tunnel':
      return '端口转发'
    case 'mount':
      return '目录挂载'
    case 'reverse_proxy':
      return '反向代理'
    default:
      return String(kind)
  }
}

/** Tailwind text color class for a service status. */
export function statusColor(status: ServiceStatus | string): string {
  switch (status) {
    case 'RUNNING':
      return 'text-emerald-500'
    case 'STARTING':
      return 'text-amber-500'
    case 'FAILED':
      return 'text-rose-500'
    case 'STOPPED':
    default:
      return 'text-zinc-500'
  }
}

/** Background dot color class for a service status. */
export function statusDotColor(status: ServiceStatus | string): string {
  switch (status) {
    case 'RUNNING':
      return 'bg-emerald-500'
    case 'STARTING':
      return 'bg-amber-500'
    case 'FAILED':
      return 'bg-rose-500'
    case 'STOPPED':
    default:
      return 'bg-zinc-500'
  }
}

/** Format a byte count, preserving human-sized strings returned by remote tools. */
export function fmtBytes(n: number | string | null | undefined): string {
  if (typeof n === 'string') {
    const s = n.trim()
    if (!s) return '—'
    const parsed = Number(s)
    if (!Number.isNaN(parsed)) return fmtBytes(parsed)
    return s
  }
  if (n == null) return '—'
  if (!Number.isFinite(n) || n < 0) return '—'
  if (n === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1)
  const value = n / Math.pow(1024, i)
  const fixed = value >= 100 || i === 0 ? value.toFixed(0) : value.toFixed(1)
  return `${fixed} ${units[i]}`
}
