// TypeScript types mirroring the backend JSON shapes.

export interface Host {
  name: string
  user: string
  host: string
  port: number
  identity: string
}

export interface SshConfigHost {
  name: string
  user: string
  host: string
  hostname: string
  port: number
  identity: string
  proxy_jump: string
  proxy_command: string
  source: string
}

export type ServiceKind = 'tunnel' | 'mount' | 'reverse_proxy'

export type ServiceStatus = 'STOPPED' | 'STARTING' | 'RUNNING' | 'FAILED'

export interface ServiceInfo {
  name: string
  kind: ServiceKind
  status: ServiceStatus
  proxy: string
  pid: number | null
  uptime: string
  last_error: string | null
  started_at: number | null
}

export interface Mirror {
  name: string
  host: string
  remote_path: string
  local_path: string
  direction: string
  auto_exclude: boolean
  max_file_size: string
  exclude: string[]
  include: string[]
  delete: boolean
}

export interface MountDiagnostics {
  platform: string
  ready: boolean
  sshfs_found: boolean
  sshfs_path: string
  sshfs_version: string
  sshfs_win_found: boolean
  sshfs_win_path: string
  winfsp_found: boolean
  winfsp_path: string
  missing: string[]
}

export interface MountInstallResult {
  ok: boolean
  started: boolean
  message: string
  script_path: string
}

export interface ConfigDefaults {
  proxy: string
  clash_port: number
  auto_restart: boolean
  workspace: string
  locale: string
}

export interface ConfigData {
  config_path: string
  workspace: string
  defaults: ConfigDefaults
  hosts: Host[]
  // The following lists are loosely typed in the backend config.
  tunnels: any[]
  mounts: any[]
  reverse_proxies: any[]
  mirrors: Mirror[]
}

export interface TestResult {
  ok: boolean
  latency_ms: number | null
  message: string
  whoami: string | null
  hostname: string | null
  os: string | null
}

export interface RepoInfo {
  path: string
  rel_path: string
  markers: string[]
  size: number | string
  type: string
}

export interface AiProxyStep {
  name: string
  ok: boolean
  detail: string
}

export interface AiProxyLaunchEntry {
  command: string
  tool: string
  note: string
}

export interface AiProxyResult {
  ok: boolean
  tunnel: ServiceInfo | null
  setup: {
    ok: boolean
    steps: AiProxyStep[]
    proxy_url: string
    env_file: string
    remote_port: number
  }
  launch: {
    claude: AiProxyLaunchEntry
    codex: AiProxyLaunchEntry
  }
}
