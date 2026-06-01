import type {
  AiProxyResult,
  ConfigData,
  Host,
  Mirror,
  MountDiagnostics,
  MountInstallResult,
  RepoInfo,
  ServiceInfo,
  ServiceKind,
  SshConfigHost,
  TestResult,
} from './types'
import { getSidecarPort } from './tauri'

export const FALLBACK_API = 'http://127.0.0.1:8765'

let apiBasePromise: Promise<string> | null = null

async function getApiBase(): Promise<string> {
  if (!apiBasePromise) {
    apiBasePromise = getSidecarPort().then((port) => `http://127.0.0.1:${port}`)
  }
  return apiBasePromise
}

/** Loose record for request bodies that vary by endpoint. */
export type Body = Record<string, unknown>

/** Thrown for any non-2xx response. `message` is the backend `{error}` text. */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: Body,
): Promise<T> {
  let res: Response
  try {
    const base = await getApiBase()
    res = await fetch(`${base}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    throw new ApiError(
      e instanceof Error ? e.message : 'Network request failed',
      0,
    )
  }

  const text = await res.text()
  let data: unknown = undefined
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    const msg =
      data && typeof data === 'object' && 'error' in data
        ? String((data as { error: unknown }).error)
        : data && typeof data === 'object' && 'detail' in data
          ? String((data as { detail: unknown }).detail)
        : typeof data === 'string' && data
          ? data
          : `Request failed (${res.status})`
    throw new ApiError(msg, res.status)
  }

  return data as T
}

const enc = encodeURIComponent

export const api = {
  // --- System ---
  health: () => request<{ ok: boolean } & Record<string, unknown>>('GET', '/api/health'),
  version: () => request<{ version: string } & Record<string, unknown>>('GET', '/api/version'),
  getConfig: () => request<ConfigData>('GET', '/api/config'),
  reload: () => request<{ ok: boolean } & Record<string, unknown>>('POST', '/api/reload'),
  shutdown: () => request<{ ok: boolean }>('POST', '/api/shutdown'),

  // --- Hosts ---
  listHosts: () => request<Host[]>('GET', '/api/hosts'),
  listSshConfigHosts: () =>
    request<SshConfigHost[]>('GET', '/api/hosts/ssh-config'),
  addHost: (b: Body) => request<Host>('POST', '/api/hosts', b),
  updateHost: (name: string, b: Body) =>
    request<Host>('PUT', `/api/hosts/${enc(name)}`, b),
  removeHost: (name: string) =>
    request<{ ok: boolean }>('DELETE', `/api/hosts/${enc(name)}`),
  testHost: (name: string) =>
    request<TestResult>('POST', `/api/hosts/${enc(name)}/test`),
  browseHost: async (name: string, opts: { path?: string; depth?: number }) => {
    const data = await request<RepoInfo[] | { repos: RepoInfo[] }>(
      'POST',
      `/api/hosts/${enc(name)}/browse`,
      {
        path: opts.path,
        depth: opts.depth,
      },
    )
    return Array.isArray(data) ? data : data.repos ?? []
  },

  // --- Services ---
  listServices: () => request<ServiceInfo[]>('GET', '/api/services'),
  startService: (kind: ServiceKind, name: string) =>
    request<ServiceInfo>('POST', `/api/services/${enc(kind)}/${enc(name)}/start`),
  stopService: (kind: ServiceKind, name: string) =>
    request<ServiceInfo>('POST', `/api/services/${enc(kind)}/${enc(name)}/stop`),
  restartService: (kind: ServiceKind, name: string) =>
    request<ServiceInfo>('POST', `/api/services/${enc(kind)}/${enc(name)}/restart`),
  setServiceProxy: (kind: ServiceKind, name: string, proxy: string) =>
    request<ServiceInfo>('PATCH', `/api/services/${enc(kind)}/${enc(name)}/proxy`, {
      proxy,
    }),
  getServiceLog: (kind: ServiceKind, name: string, tail = 200) =>
    request<{ lines: string[] }>(
      'GET',
      `/api/services/${enc(kind)}/${enc(name)}/log?tail=${tail}`,
    ),

  // --- Tunnels ---
  addTunnel: (b: Body) => request<unknown>('POST', '/api/tunnels', b),
  removeTunnel: (name: string) =>
    request<{ ok: boolean }>('DELETE', `/api/tunnels/${enc(name)}`),

  // --- Mounts ---
  mountDiagnostics: () =>
    request<MountDiagnostics>('GET', '/api/mounts/diagnostics'),
  installMountDependencies: () =>
    request<MountInstallResult>('POST', '/api/mounts/install-dependencies'),
  addMount: (b: Body) => request<unknown>('POST', '/api/mounts', b),
  removeMount: (name: string) =>
    request<{ ok: boolean }>('DELETE', `/api/mounts/${enc(name)}`),

  // --- Reverse proxies ---
  addReverseProxy: (b: Body) => request<unknown>('POST', '/api/reverse_proxies', b),
  removeReverseProxy: (name: string) =>
    request<{ ok: boolean }>('DELETE', `/api/reverse_proxies/${enc(name)}`),

  // --- Mirrors ---
  listMirrors: () => request<Mirror[]>('GET', '/api/mirrors'),
  addMirror: (b: Body) => request<Mirror>('POST', '/api/mirrors', b),
  removeMirror: (name: string) =>
    request<{ ok: boolean }>('DELETE', `/api/mirrors/${enc(name)}`),
  pullMirror: (name: string, dry_run = false) =>
    request<unknown>('POST', `/api/mirrors/${enc(name)}/pull?dry_run=${dry_run}`),
  pushMirror: (name: string, dry_run = false) =>
    request<unknown>('POST', `/api/mirrors/${enc(name)}/push?dry_run=${dry_run}`),
  mirrorStatus: (name: string) =>
    request<unknown>('GET', `/api/mirrors/${enc(name)}/status`),
  fetchFile: (b: Body) => request<unknown>('POST', '/api/fetch-file', b),

  // --- AI proxy ---
  aiProxySetup: (b: Body) =>
    request<AiProxyResult>('POST', '/api/ai-proxy/setup', b),
  aiProxyTeardown: (host: string) =>
    request<unknown>('POST', '/api/ai-proxy/teardown', { host }),
  aiProxyStatus: (host: string) =>
    request<unknown>('GET', `/api/ai-proxy/status?host=${enc(host)}`),
}

export type Api = typeof api
