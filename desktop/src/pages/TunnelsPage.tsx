import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Cable,
  Plus,
  Play,
  Square,
  RotateCw,
  Trash2,
  ScrollText,
  Network,
  X,
  Loader2,
} from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useStatusSocket, useLogSocket } from '@/lib/ws'
import type { Host, ServiceInfo, ServiceStatus } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { PageHeader } from '@/components/page-header'
import { StatusBadge } from '@/components/status-badge'
import { EmptyState } from '@/components/empty-state'

type ForwardType = 'local' | 'remote' | 'dynamic'

interface ForwardRow {
  type: ForwardType
  local_port: string
  remote_host: string
  remote_port: string
}

interface ForwardDef {
  type?: string
  local_port?: number
  remote_host?: string
  remote_port?: number
}

interface TunnelDef {
  name: string
  host?: string
  proxy?: string
  forwards?: ForwardDef[]
}

interface MergedTunnel {
  name: string
  def: TunnelDef | undefined
  svc: ServiceInfo | undefined
}

type TunnelBody = {
  name: string
  host: string
  proxy: string
  forwards: ForwardDef[]
}

const newForward = (): ForwardRow => ({
  type: 'local',
  local_port: '',
  remote_host: '127.0.0.1',
  remote_port: '',
})

function forwardSummary(def: TunnelDef | undefined): string {
  const fwds = def?.forwards ?? []
  if (fwds.length === 0) return '无转发规则'
  return fwds
    .map((f) => {
      if (f.type === 'dynamic') return `D:${f.local_port ?? '?'}`
      const prefix = f.type === 'remote' ? 'R' : 'L'
      return `${prefix} ${f.local_port ?? '?'} → ${f.remote_host ?? '127.0.0.1'}:${f.remote_port ?? '?'}`
    })
    .join(', ')
}

// -------------------------------------------------------------------------
// Add tunnel dialog
// -------------------------------------------------------------------------

interface AddTunnelDialogProps {
  open: boolean
  hosts: Host[]
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (body: TunnelBody) => void
}

function AddTunnelDialog({
  open,
  hosts,
  submitting,
  onOpenChange,
  onSubmit,
}: AddTunnelDialogProps) {
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [proxy, setProxy] = useState('direct')
  const [forwards, setForwards] = useState<ForwardRow[]>([newForward()])

  // Re-seed when the dialog opens.
  const [wasOpen, setWasOpen] = useState(false)
  if (open && !wasOpen) {
    setWasOpen(true)
    setName('')
    setHost(hosts[0]?.name ?? '')
    setProxy('direct')
    setForwards([newForward()])
  }
  if (!open && wasOpen) setWasOpen(false)

  const setRow = (i: number, patch: Partial<ForwardRow>) =>
    setForwards((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  const proxyOptions = useMemo(() => {
    const base = ['direct', 'clash']
    hosts.forEach((h) => base.push(`jump:${h.name}`))
    return base
  }, [hosts])

  const valid = Boolean(name.trim() && host)

  const submit = () => {
    const body: TunnelBody = {
      name: name.trim(),
      host,
      proxy,
      forwards: forwards
        .filter((r) => r.local_port.trim())
        .map<ForwardDef>((r) =>
          r.type === 'dynamic'
            ? { type: r.type, local_port: Number(r.local_port) }
            : {
                type: r.type,
                local_port: Number(r.local_port),
                remote_host: r.remote_host.trim() || '127.0.0.1',
                remote_port: Number(r.remote_port) || 0,
              },
        ),
    }
    onSubmit(body)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>添加端口转发</DialogTitle>
          <DialogDescription>通过 SSH 连接转发端口。</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tunnel-name">名称</Label>
            <Input
              id="tunnel-name"
              placeholder="db-forward"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="tunnel-host">主机</Label>
              <Select value={host} onValueChange={setHost}>
                <SelectTrigger id="tunnel-host" className="w-full">
                  <SelectValue
                    placeholder={hosts.length === 0 ? '还没有配置主机' : '选择主机'}
                  />
                </SelectTrigger>
                <SelectContent>
                  {hosts.map((h) => (
                    <SelectItem key={h.name} value={h.name}>
                      {h.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tunnel-proxy">代理</Label>
              <Select value={proxy} onValueChange={setProxy}>
                <SelectTrigger id="tunnel-proxy" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {proxyOptions.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>转发规则</Label>
            <div className="space-y-2">
              {forwards.map((row, i) => (
                <div
                  key={i}
                  className="flex items-end gap-2 rounded-lg border bg-muted/30 p-2"
                >
                  <Select
                    value={row.type}
                    onValueChange={(v) => setRow(i, { type: v as ForwardType })}
                  >
                    <SelectTrigger className="w-28 shrink-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="local">本地</SelectItem>
                      <SelectItem value="remote">远程</SelectItem>
                      <SelectItem value="dynamic">动态</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    className="w-20 shrink-0"
                    type="number"
                    placeholder="lport"
                    value={row.local_port}
                    onChange={(e) => setRow(i, { local_port: e.target.value })}
                  />
                  {row.type !== 'dynamic' && (
                    <>
                      <Input
                        className="flex-1"
                        placeholder="127.0.0.1"
                        value={row.remote_host}
                        onChange={(e) => setRow(i, { remote_host: e.target.value })}
                      />
                      <Input
                        className="w-20 shrink-0"
                        type="number"
                        placeholder="rport"
                        value={row.remote_port}
                        onChange={(e) => setRow(i, { remote_port: e.target.value })}
                      />
                    </>
                  )}
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    title="删除转发规则"
                    disabled={forwards.length === 1}
                    onClick={() =>
                      setForwards((prev) => prev.filter((_, idx) => idx !== i))
                    }
                  >
                    <X />
                    <span className="sr-only">删除转发规则</span>
                  </Button>
                </div>
              ))}
              <Button
                size="sm"
                variant="outline"
                onClick={() => setForwards((prev) => [...prev, newForward()])}
              >
                <Plus />
                添加转发规则
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button disabled={!valid || submitting} onClick={submit}>
            {submitting && <Loader2 className="animate-spin" />}
            创建端口转发
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// -------------------------------------------------------------------------
// Live log sheet
// -------------------------------------------------------------------------

function LogSheet({
  tunnel,
  onClose,
}: {
  tunnel: string | null
  onClose: () => void
}) {
  const open = tunnel !== null
  const { lines, connected } = useLogSocket('tunnel', tunnel ?? '', open)
  const [seed, setSeed] = useState<string[]>([])
  const viewportRef = useRef<HTMLDivElement>(null)

  // Seed with the recent tail when the sheet opens.
  useEffect(() => {
    if (!tunnel) {
      setSeed([])
      return
    }
    let cancelled = false
    void api
      .getServiceLog('tunnel', tunnel, 200)
      .then((res) => {
        if (!cancelled) setSeed(res.lines ?? [])
      })
      .catch(() => {
        if (!cancelled) setSeed([])
      })
    return () => {
      cancelled = true
    }
  }, [tunnel])

  const allLines = seed.length > 0 ? [...seed, ...lines] : lines

  // Auto-scroll to bottom on new output.
  useEffect(() => {
    const vp = viewportRef.current
    if (vp) vp.scrollTop = vp.scrollHeight
  }, [allLines])

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <ScrollText className="size-4" />
            {tunnel ? `日志 · ${tunnel}` : '日志'}
          </SheetTitle>
          <SheetDescription className="flex items-center gap-1.5">
            <span
              className={
                connected ? 'size-1.5 rounded-full bg-emerald-500' : 'size-1.5 rounded-full bg-muted-foreground/60'
              }
            />
            {connected ? '实时输出' : '连接中…'}
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="mx-4 mb-4 flex-1 rounded-lg border bg-muted/30">
          <div
            ref={viewportRef}
            className="max-h-[calc(100vh-9rem)] overflow-auto p-3 font-mono text-xs leading-relaxed text-muted-foreground"
          >
            {allLines.length > 0 ? (
              <pre className="whitespace-pre-wrap break-all">{allLines.join('\n')}</pre>
            ) : (
              '等待日志输出…'
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

// -------------------------------------------------------------------------
// Row
// -------------------------------------------------------------------------

interface TunnelRowProps {
  tunnel: MergedTunnel
  hosts: Host[]
  onLog: () => void
  onDelete: () => void
}

function IconButton({
  label,
  busy,
  disabled,
  onClick,
  children,
}: {
  label: string
  busy?: boolean
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          size="icon-sm"
          variant="ghost"
          disabled={disabled}
          onClick={onClick}
        >
          {busy ? <Loader2 className="animate-spin" /> : children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

function TunnelRow({ tunnel, hosts, onLog, onDelete }: TunnelRowProps) {
  const [busy, setBusy] = useState<string | null>(null)
  const actionLabel: Record<string, string> = {
    proxy: '切换代理',
    start: '启动',
    stop: '停止',
    restart: '重启',
  }
  const status: ServiceStatus = tunnel.svc?.status ?? 'STOPPED'
  const running = status === 'RUNNING'
  const proxy = tunnel.svc?.proxy || tunnel.def?.proxy || 'direct'

  const proxyOptions = useMemo(() => {
    const base = ['direct', 'clash']
    hosts.forEach((h) => base.push(`jump:${h.name}`))
    return base
  }, [hosts])

  const run = async (action: string, fn: () => Promise<unknown>, msg: string) => {
    setBusy(action)
    try {
      await fn()
      toast.success(msg)
    } catch (e) {
      toast.error(`${actionLabel[action] ?? action}失败`, {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setBusy(null)
    }
  }

  const setProxy = (next: string) =>
    run(
      'proxy',
      () => api.setServiceProxy('tunnel', tunnel.name, next),
      `${tunnel.name} 代理已切换到 ${next}`,
    )

  return (
    <TableRow>
      <TableCell>
        <StatusBadge status={status} />
      </TableCell>
      <TableCell className="font-medium">{tunnel.name}</TableCell>
      <TableCell>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline" disabled={busy !== null} className="gap-1">
              <Network className="size-3.5" />
              {busy === 'proxy' ? <Loader2 className="animate-spin" /> : proxy}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-40">
            {proxyOptions.map((p) => (
              <DropdownMenuItem key={p} onSelect={() => setProxy(p)} disabled={p === proxy}>
                {p}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
      <TableCell className="max-w-xs">
        <p className="truncate font-mono text-xs text-muted-foreground" title={forwardSummary(tunnel.def)}>
          {forwardSummary(tunnel.def)}
        </p>
        {tunnel.svc?.last_error && (
          <p className="mt-0.5 truncate text-xs text-rose-500" title={tunnel.svc.last_error}>
            {tunnel.svc.last_error}
          </p>
        )}
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {tunnel.svc?.pid != null ? `pid ${tunnel.svc.pid}` : '—'}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {tunnel.svc?.uptime || '—'}
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-0.5">
          <IconButton
            label="启动"
            busy={busy === 'start'}
            disabled={running || busy !== null}
            onClick={() =>
              run('start', () => api.startService('tunnel', tunnel.name), `${tunnel.name} 已启动`)
            }
          >
            <Play />
          </IconButton>
          <IconButton
            label="停止"
            busy={busy === 'stop'}
            disabled={!running || busy !== null}
            onClick={() =>
              run('stop', () => api.stopService('tunnel', tunnel.name), `${tunnel.name} 已停止`)
            }
          >
            <Square />
          </IconButton>
          <IconButton
            label="重启"
            busy={busy === 'restart'}
            disabled={busy !== null}
            onClick={() =>
              run(
                'restart',
                () => api.restartService('tunnel', tunnel.name),
                `${tunnel.name} 正在重启`,
              )
            }
          >
            <RotateCw />
          </IconButton>
          <IconButton label="日志" onClick={onLog}>
            <ScrollText />
          </IconButton>
          <IconButton label="删除" onClick={onDelete}>
            <Trash2 className="text-rose-500" />
          </IconButton>
        </div>
      </TableCell>
    </TableRow>
  )
}

// -------------------------------------------------------------------------
// Page
// -------------------------------------------------------------------------

export default function TunnelsPage() {
  const qc = useQueryClient()
  const { services } = useStatusSocket()

  const configQuery = useQuery({
    queryKey: ['config'],
    queryFn: () => api.getConfig(),
    staleTime: 10000,
  })

  const [addOpen, setAddOpen] = useState(false)
  const [logName, setLogName] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  const hosts = configQuery.data?.hosts ?? []
  const defs = (configQuery.data?.tunnels ?? []) as TunnelDef[]

  const merged: MergedTunnel[] = useMemo(() => {
    const svcByName = new Map<string, ServiceInfo>()
    services
      .filter((s) => s.kind === 'tunnel')
      .forEach((s) => svcByName.set(s.name, s))

    const names = new Set<string>()
    defs.forEach((d) => names.add(d.name))
    svcByName.forEach((_, n) => names.add(n))

    return Array.from(names)
      .sort()
      .map((name) => ({
        name,
        def: defs.find((d) => d.name === name),
        svc: svcByName.get(name),
      }))
  }, [defs, services])

  const addMut = useMutation({
    mutationFn: (body: TunnelBody) => api.addTunnel(body),
    onSuccess: (_d, vars) => {
      toast.success(`端口转发 "${vars.name}" 已创建`)
      setAddOpen(false)
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
    onError: (e) =>
      toast.error('无法创建端口转发', {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  const deleteMut = useMutation({
    mutationFn: (name: string) => api.removeTunnel(name),
    onSuccess: () => {
      toast.success('端口转发已删除')
      setDeleting(null)
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
    onError: (e) =>
      toast.error('无法删除端口转发', {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Cable />}
        title="端口转发"
        description="通过 SSH 转发端口，并支持实时状态与单项代理控制。"
        actions={
          <Button onClick={() => setAddOpen(true)}>
            <Plus />
            添加端口转发
          </Button>
        }
      />

      <Card className="py-0">
        <CardContent className="px-0">
          {configQuery.isLoading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : merged.length === 0 ? (
            <EmptyState
              icon={<Cable />}
              title="还没有端口转发"
              description="创建端口转发，把远程主机上的端口映射到需要的位置。"
              action={
                <Button onClick={() => setAddOpen(true)}>
                  <Plus />
                  添加端口转发
                </Button>
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>状态</TableHead>
                  <TableHead>名称</TableHead>
                  <TableHead>代理</TableHead>
                  <TableHead>转发规则</TableHead>
                  <TableHead>PID</TableHead>
                  <TableHead>运行时长</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {merged.map((t) => (
                  <TunnelRow
                    key={t.name}
                    tunnel={t}
                    hosts={hosts}
                    onLog={() => setLogName(t.name)}
                    onDelete={() => setDeleting(t.name)}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AddTunnelDialog
        open={addOpen}
        hosts={hosts}
        submitting={addMut.isPending}
        onOpenChange={setAddOpen}
        onSubmit={(body) => addMut.mutate(body)}
      />

      <LogSheet tunnel={logName} onClose={() => setLogName(null)} />

      <AlertDialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除端口转发</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting ? `确定删除端口转发 "${deleting}"？` : ''}
              该转发会被停止，并从配置中移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMut.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={(e) => {
                e.preventDefault()
                if (deleting) deleteMut.mutate(deleting)
              }}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending && <Loader2 className="animate-spin" />}
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
