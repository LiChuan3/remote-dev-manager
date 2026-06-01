import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Server,
  Activity,
  AlertTriangle,
  Zap,
  Play,
  Square,
  RotateCw,
  ArrowRight,
  ServerCog,
  Wifi,
  WifiOff,
  LayoutDashboard,
  Network,
  HardDrive,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useStatusSocket } from '@/lib/ws'
import { prettyKind } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ServiceInfo, ServiceKind } from '@/lib/types'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { PageHeader } from '@/components/page-header'
import { StatusBadge } from '@/components/status-badge'
import { EmptyState } from '@/components/empty-state'
import { OperationGuide } from '@/components/operation-guide'

interface StatCardProps {
  icon: ReactNode
  label: string
  value: ReactNode
  accent: string
}

function StatCard({ icon, label, value, accent }: StatCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4">
        <div
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-lg [&_svg]:size-5',
            accent,
          )}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {label}
          </p>
          <p className="mt-0.5 truncate text-2xl font-semibold tabular-nums">
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

function ServiceRow({ svc }: { svc: ServiceInfo }) {
  const [busy, setBusy] = useState<null | 'start' | 'stop' | 'restart'>(null)
  const actionLabel = {
    start: '启动',
    stop: '停止',
    restart: '重启',
  }

  const run = async (
    action: 'start' | 'stop' | 'restart',
    fn: (kind: ServiceKind, name: string) => Promise<unknown>,
  ) => {
    setBusy(action)
    try {
      await fn(svc.kind, svc.name)
      toast.success(`${svc.name}: 已请求${actionLabel[action]}`)
    } catch (e) {
      toast.error(`${actionLabel[action]} ${svc.name} 失败`, {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setBusy(null)
    }
  }

  const running = svc.status === 'RUNNING'

  return (
    <TableRow>
      <TableCell className="font-medium">{svc.name}</TableCell>
      <TableCell>
        <Badge variant="outline">{prettyKind(svc.kind)}</Badge>
      </TableCell>
      <TableCell>
        <StatusBadge status={svc.status} />
      </TableCell>
      <TableCell className="text-muted-foreground font-mono text-xs">
        {svc.proxy || '—'}
      </TableCell>
      <TableCell className="text-muted-foreground font-mono text-xs">
        {svc.pid ?? '—'}
      </TableCell>
      <TableCell className="text-muted-foreground">{svc.uptime || '—'}</TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="启动"
                disabled={running || busy !== null}
                onClick={() => run('start', api.startService)}
              >
                <Play />
              </Button>
            </TooltipTrigger>
            <TooltipContent>启动</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="停止"
                disabled={!running || busy !== null}
                onClick={() => run('stop', api.stopService)}
              >
                <Square />
              </Button>
            </TooltipTrigger>
            <TooltipContent>停止</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="重启"
                disabled={busy !== null}
                onClick={() => run('restart', api.restartService)}
              >
                <RotateCw />
              </Button>
            </TooltipTrigger>
            <TooltipContent>重启</TooltipContent>
          </Tooltip>
        </div>
      </TableCell>
    </TableRow>
  )
}

interface QuickActionProps {
  to: string
  icon: ReactNode
  title: string
  desc: string
}

function QuickAction({ to, icon, title, desc }: QuickActionProps) {
  return (
    <Link
      to={to}
      className="group bg-card text-card-foreground hover:border-primary/40 ring-foreground/10 hover:ring-primary/30 flex items-center gap-3 rounded-xl p-4 ring-1 transition-colors"
    >
      <div className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-lg [&_svg]:size-[18px]">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-muted-foreground truncate text-xs">{desc}</p>
      </div>
      <ArrowRight className="text-muted-foreground group-hover:text-primary size-4 transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}

export default function DashboardPage() {
  const { services, connected } = useStatusSocket()

  const configQuery = useQuery({
    queryKey: ['config'],
    queryFn: () => api.getConfig(),
    staleTime: 10000,
  })

  const config = configQuery.data
  const hosts = config?.hosts ?? []
  const tunnelCount = config?.tunnels?.length ?? 0
  const mountCount = config?.mounts?.length ?? 0
  const mirrorCount = config?.mirrors?.length ?? 0

  const runningCount = useMemo(
    () => services.filter((s) => s.status === 'RUNNING').length,
    [services],
  )
  const failedCount = useMemo(
    () => services.filter((s) => s.status === 'FAILED').length,
    [services],
  )

  const aiActive = useMemo(
    () =>
      services.filter(
        (s) => s.kind === 'reverse_proxy' && s.status === 'RUNNING',
      ).length,
    [services],
  )
  const noConfig = !configQuery.isLoading && hosts.length === 0

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<LayoutDashboard />}
        title="远程开发管理器"
        description="集中管理远程开发主机的端口转发、目录挂载、同步镜像和 AI 代理。"
      />

      <OperationGuide
        title="仪表盘怎么用"
        steps={[
          "先看顶部统计，确认主机数量、运行中服务和失败服务是否正常。",
          "常用入口在快捷操作区，可直接跳到主机、端口转发、目录挂载、同步镜像或 AI 代理。",
          "服务表会实时展示运行状态，可直接启动、停止或重启已有服务。",
          "如果服务失败，进入对应功能页打开日志查看原因。",
        ]}
      />

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={<Server className="text-primary" />}
          label="主机"
          value={configQuery.isLoading ? '—' : hosts.length}
          accent="bg-primary/10"
        />
        <StatCard
          icon={<Activity className="text-emerald-500" />}
          label="运行中"
          value={runningCount}
          accent="bg-emerald-500/10"
        />
        <StatCard
          icon={<AlertTriangle className="text-rose-500" />}
          label="失败"
          value={failedCount}
          accent="bg-rose-500/10"
        />
        <StatCard
          icon={<Zap className="text-violet-500" />}
          label="AI 代理"
          value={aiActive > 0 ? `${aiActive} 个活跃` : '空闲'}
          accent="bg-violet-500/10"
        />
      </div>

      {/* Secondary config counts */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          icon={<Network className="text-sky-500" />}
          label="端口转发"
          value={configQuery.isLoading ? '—' : tunnelCount}
          accent="bg-sky-500/10"
        />
        <StatCard
          icon={<HardDrive className="text-amber-500" />}
          label="目录挂载"
          value={configQuery.isLoading ? '—' : mountCount}
          accent="bg-amber-500/10"
        />
        <StatCard
          icon={<ServerCog className="text-teal-500" />}
          label="同步镜像"
          value={configQuery.isLoading ? '—' : mirrorCount}
          accent="bg-teal-500/10"
        />
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <QuickAction
          to="/hosts"
          icon={<Server />}
          title="管理主机"
          desc="添加、测试并浏览 SSH 主机"
        />
        <QuickAction
          to="/tunnels"
          icon={<Network />}
          title="端口转发"
          desc="从远程主机转发端口"
        />
        <QuickAction
          to="/mounts"
          icon={<HardDrive />}
          title="目录挂载"
          desc="把远程目录挂载到本机"
        />
        <QuickAction
          to="/mirror"
          icon={<ServerCog />}
          title="同步镜像"
          desc="同步远程目录到本机"
        />
        <QuickAction
          to="/ai-proxy"
          icon={<Zap />}
          title="AI 代理"
          desc="为远程主机配置 Claude / Codex"
        />
      </div>

      {/* Live services */}
      <Card className="py-0">
        <CardHeader className="flex flex-row items-center justify-between border-b py-4">
          <div className="space-y-1">
            <CardTitle>服务</CardTitle>
            <CardDescription>通过 WebSocket 实时查看状态</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {services.length > 0 && (
              <Badge variant="secondary">{services.length} 个</Badge>
            )}
            <Badge
              variant="outline"
              className={cn(
                'gap-1.5',
                connected
                  ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                  : 'border-amber-500/30 text-amber-600 dark:text-amber-400',
              )}
            >
              {connected ? (
                <Wifi className="size-3" />
              ) : (
                <WifiOff className="size-3" />
              )}
              {connected ? '已连接' : '连接中…'}
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="px-0 pb-0">
          {noConfig ? (
            <EmptyState
              icon={<Server />}
              title="还没有主机，先添加一台开始使用"
              description="添加远程主机后，就可以基于它创建端口转发、目录挂载或 AI 代理。"
              action={
                <Button asChild>
                  <Link to="/hosts">
                    <Server />
                    添加主机
                  </Link>
                </Button>
              }
            />
          ) : services.length === 0 ? (
            <EmptyState
              icon={<Activity />}
              title="还没有配置服务"
              description="创建端口转发、目录挂载或反向代理后，这里会显示实时状态。"
              action={
                <div className="flex gap-2">
                  <Button variant="outline" asChild>
                    <Link to="/tunnels">新建端口转发</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/mounts">新建目录挂载</Link>
                  </Button>
                </div>
              }
            />
          ) : (
            <TooltipProvider>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>代理</TableHead>
                    <TableHead>PID</TableHead>
                    <TableHead>运行时长</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {services.map((svc) => (
                    <ServiceRow key={`${svc.kind}:${svc.name}`} svc={svc} />
                  ))}
                </TableBody>
              </Table>
            </TooltipProvider>
          )}
        </CardContent>
      </Card>

      {configQuery.isError && (
        <p className="text-muted-foreground text-center text-xs">
          无法加载配置。{' '}
          <button
            className="text-destructive underline-offset-4 hover:underline"
            onClick={() => {
              void configQuery.refetch()
              toast.info('正在重试…')
            }}
          >
            重试
          </button>
        </p>
      )}
    </div>
  )
}
