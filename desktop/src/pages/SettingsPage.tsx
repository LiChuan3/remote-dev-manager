import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Settings as SettingsIcon,
  FileCog,
  RefreshCw,
  BookOpen,
  Power,
  Rocket,
  Github,
  Info,
  Palette,
  Sun,
  Moon,
  Monitor,
  Wrench,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { getSidecarPort, quitApp } from '@/lib/tauri'
import { cn } from '@/lib/utils'
import { useTheme } from '@/components/theme-provider'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { PageHeader } from '@/components/page-header'
import { CopyButton } from '@/components/copy-button'
import { OperationGuide } from '@/components/operation-guide'

const REPO_URL = 'https://github.com/LiChuan3/remote-dev-manager'
const HEALTH_RETRY_COUNT = 20
const healthRetryDelay = (attempt: number) =>
  Math.min(500 + attempt * 500, 2000)

/** Open a URL via the Tauri shell plugin if available, else a new browser tab. */
async function openUrl(url: string): Promise<void> {
  try {
    const shell = await import('@tauri-apps/plugin-shell')
    await shell.open(url)
  } catch {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

function InfoRow({
  label,
  value,
  copy,
}: {
  label: string
  value: ReactNode
  copy?: string
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="min-w-0 text-right font-mono text-xs break-all">
          {value}
        </span>
        {copy ? <CopyButton value={copy} label="" size="icon-xs" /> : null}
      </span>
    </div>
  )
}

const THEME_OPTIONS = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
] as const

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { theme, setTheme } = useTheme()

  const configQuery = useQuery({
    queryKey: ['config'],
    queryFn: () => api.getConfig(),
    staleTime: 10000,
  })
  const versionQuery = useQuery({
    queryKey: ['version'],
    queryFn: () => api.version(),
    staleTime: 60000,
  })
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health(),
    refetchInterval: 5000,
    retry: HEALTH_RETRY_COUNT,
    retryDelay: healthRetryDelay,
  })

  const [reloading, setReloading] = useState(false)

  // --- Sidecar port (Tauri-aware, falls back to default) ---
  const [sidecarPort, setSidecarPort] = useState<number | null>(null)
  useEffect(() => {
    let cancelled = false
    void getSidecarPort().then((p) => {
      if (!cancelled) setSidecarPort(p)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // --- Autostart (Tauri only) ---
  const [autostart, setAutostart] = useState<boolean | null>(null)
  const [autostartSupported, setAutostartSupported] = useState(true)
  const [autostartBusy, setAutostartBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const { isEnabled } = await import('@tauri-apps/plugin-autostart')
        const enabled = await isEnabled()
        if (!cancelled) setAutostart(enabled)
      } catch {
        if (!cancelled) setAutostartSupported(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const toggleAutostart = async (next: boolean) => {
    setAutostartBusy(true)
    try {
      const { enable, disable } = await import('@tauri-apps/plugin-autostart')
      if (next) await enable()
      else await disable()
      setAutostart(next)
      toast.success(next ? '已开启登录时启动' : '已关闭登录时启动')
    } catch (e) {
      toast.error('无法修改登录启动设置', {
        description: e instanceof Error ? e.message : '仅桌面应用支持',
      })
    } finally {
      setAutostartBusy(false)
    }
  }

  const onReload = async () => {
    setReloading(true)
    try {
      await api.reload()
      toast.success('配置已重新加载')
      void queryClient.invalidateQueries({ queryKey: ['config'] })
    } catch (e) {
      toast.error('重新加载失败', {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setReloading(false)
    }
  }

  const onQuit = async () => {
    try {
      await quitApp()
    } catch (e) {
      toast.error('只有桌面应用支持退出操作', {
        description: e instanceof Error ? e.message : undefined,
      })
    }
  }

  const backendStatus = health.isSuccess
    ? 'online'
    : health.isError
      ? 'offline'
      : 'starting'
  const backendLabel =
    backendStatus === 'online'
      ? '在线'
      : backendStatus === 'starting'
        ? '启动中'
        : '离线'
  const config = configQuery.data
  const defaults = config?.defaults
  const version = versionQuery.data?.version
  const docsUrl = `http://127.0.0.1:${sidecarPort ?? 8765}/docs`

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<SettingsIcon />}
        title="设置"
        description="管理应用配置、外观、登录启动和维护操作。"
      />

      <OperationGuide
        title="设置页怎么用"
        steps={[
          "外观用于切换浅色、深色或跟随系统主题。",
          "启动里的登录时启动只在桌面应用中生效，开启后下次登录系统会自动打开。",
          "配置区域展示当前工作区、配置路径和默认代理；点重新加载配置可让后端重新读取配置文件。",
          "后端服务区域可查看当前动态端口和在线状态；关于与操作里可打开 API 文档或退出应用。",
        ]}
      />

      {/* Appearance */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Palette className="text-primary size-4" /> 外观
          </CardTitle>
          <CardDescription>
            选择远程开发管理器的显示主题；跟随系统会使用操作系统主题。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            role="radiogroup"
            aria-label="主题"
            className="bg-muted inline-flex w-fit gap-1 rounded-lg p-1"
          >
            {THEME_OPTIONS.map(({ value, label, icon: Icon }) => {
              const active = theme === value
              return (
                <Button
                  key={value}
                  role="radio"
                  aria-checked={active}
                  size="sm"
                  variant={active ? 'default' : 'ghost'}
                  className={cn(!active && 'text-muted-foreground')}
                  onClick={() => setTheme(value)}
                >
                  <Icon />
                  {label}
                </Button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Startup */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Rocket className="text-primary size-4" /> 启动
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium">登录时启动</p>
              <p className="text-muted-foreground text-xs">
                {autostartSupported
                  ? '登录系统后自动启动远程开发管理器。'
                  : '仅桌面应用支持。'}
              </p>
            </div>
            {autostartSupported ? (
              <Switch
                aria-label="登录时启动"
                checked={autostart === true}
                disabled={autostart === null || autostartBusy}
                onCheckedChange={toggleAutostart}
              />
            ) : (
              <Badge variant="secondary">仅桌面版</Badge>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCog className="text-primary size-4" /> 配置
          </CardTitle>
          <CardDescription>
            查看只读环境信息和默认配置。
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-border divide-y">
          <InfoRow
            label="配置路径"
            value={config?.config_path ?? (configQuery.isLoading ? '—' : 'unknown')}
            copy={config?.config_path}
          />
          <InfoRow
            label="工作区"
            value={config?.workspace ?? (configQuery.isLoading ? '—' : 'unknown')}
            copy={config?.workspace}
          />
          <InfoRow
            label="代理"
            value={defaults?.proxy || (configQuery.isLoading ? '—' : 'none')}
          />
          <InfoRow
            label="Clash 端口"
            value={defaults?.clash_port ?? (configQuery.isLoading ? '—' : '—')}
          />
          <InfoRow
            label="自动重启"
            value={
              defaults ? (
                <Badge variant={defaults.auto_restart ? 'default' : 'secondary'}>
                  {defaults.auto_restart ? '开' : '关'}
                </Badge>
              ) : (
                '—'
              )
            }
          />
          <InfoRow
            label="语言"
            value={defaults?.locale || (configQuery.isLoading ? '—' : '—')}
          />
        </CardContent>
        <CardContent className="pt-0">
          <Button
            variant="outline"
            size="sm"
            onClick={onReload}
            disabled={reloading}
          >
            <RefreshCw className={cn(reloading && 'animate-spin')} />
            重新加载配置
          </Button>
        </CardContent>
      </Card>

      {/* Sidecar */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wrench className="text-primary size-4" /> 后端服务
          </CardTitle>
        </CardHeader>
        <CardContent className="divide-border divide-y">
          <InfoRow label="rdm 版本" value={version ?? '—'} />
          <InfoRow label="端口" value={sidecarPort ?? '—'} />
          <InfoRow
            label="状态"
            value={
              <Badge
                variant="outline"
                className={cn(
                  backendStatus === 'online'
                    ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                    : backendStatus === 'starting'
                      ? 'border-amber-500/30 text-amber-600 dark:text-amber-400'
                      : 'border-rose-500/30 text-rose-600 dark:text-rose-400',
                )}
              >
                {backendLabel}
              </Badge>
            }
          />
        </CardContent>
      </Card>

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="text-primary size-4" /> 关于与操作
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium">远程开发管理器</p>
            <p className="text-muted-foreground text-xs">
              版本 {version ?? '—'} · MIT 许可证
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => void openUrl(docsUrl)}>
              <BookOpen />
              打开 API 文档
            </Button>
            <Button variant="outline" onClick={() => void openUrl(REPO_URL)}>
              <Github />
              在 GitHub 查看
            </Button>
          </div>

          <Separator />

          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium">退出应用</p>
              <p className="text-muted-foreground text-xs">
                停止所有服务并关闭远程开发管理器。
              </p>
            </div>
            <Button variant="destructive" onClick={() => void onQuit()}>
              <Power />
              退出应用
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
