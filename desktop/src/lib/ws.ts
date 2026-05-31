import { useEffect, useRef, useState } from 'react'
import type { ServiceInfo } from './types'
import { getSidecarPort } from './tauri'

export const FALLBACK_WS_BASE = 'ws://127.0.0.1:8765'

let wsBasePromise: Promise<string> | null = null

async function getWsBase(): Promise<string> {
  if (!wsBasePromise) {
    wsBasePromise = getSidecarPort().then((port) => `ws://127.0.0.1:${port}`)
  }
  return wsBasePromise
}

const MAX_LOG_LINES = 1000

/**
 * Live service status feed from `ws://127.0.0.1:8765/ws/status`.
 * Auto-reconnects with exponential backoff.
 */
export function useStatusSocket(): {
  services: ServiceInfo[]
  connected: boolean
} {
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let attempt = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    const connect = async () => {
      if (closed) return
      const base = await getWsBase()
      if (closed) return
      ws = new WebSocket(`${base}/ws/status`)

      ws.onopen = () => {
        attempt = 0
        setConnected(true)
      }

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string)
          if (Array.isArray(data)) {
            setServices(data as ServiceInfo[])
          }
        } catch {
          /* ignore malformed frames */
        }
      }

      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        attempt += 1
        timer = setTimeout(() => void connect(), delay)
      }

      ws.onerror = () => {
        // onclose follows; let it handle reconnection.
        ws?.close()
      }
    }

    void connect()

    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      ws?.close()
    }
  }, [])

  return { services, connected }
}

/**
 * Streamed log feed from `ws://127.0.0.1:8765/ws/logs/{kind}/{name}`.
 * Capped at ~1000 lines. Disconnects when `enabled` is false or on unmount.
 */
export function useLogSocket(
  kind: string,
  name: string,
  enabled: boolean,
): { lines: string[]; connected: boolean } {
  const [lines, setLines] = useState<string[]>([])
  const [connected, setConnected] = useState(false)
  const bufferRef = useRef<string>('')

  useEffect(() => {
    if (!enabled || !kind || !name) {
      setLines([])
      setConnected(false)
      return
    }

    let ws: WebSocket | null = null
    let closed = false
    let attempt = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    setLines([])
    bufferRef.current = ''

    const append = (chunk: string) => {
      bufferRef.current += chunk
      const parts = bufferRef.current.split('\n')
      bufferRef.current = parts.pop() ?? ''
      if (parts.length === 0) return
      setLines((prev) => {
        const next = prev.concat(parts)
        return next.length > MAX_LOG_LINES
          ? next.slice(next.length - MAX_LOG_LINES)
          : next
      })
    }

    const connect = async () => {
      if (closed) return
      const base = await getWsBase()
      if (closed) return
      ws = new WebSocket(
        `${base}/ws/logs/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`,
      )

      ws.onopen = () => {
        attempt = 0
        setConnected(true)
      }

      ws.onmessage = (ev) => {
        append(typeof ev.data === 'string' ? ev.data : '')
      }

      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        attempt += 1
        timer = setTimeout(() => void connect(), delay)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    void connect()

    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      ws?.close()
    }
  }, [kind, name, enabled])

  return { lines, connected }
}
