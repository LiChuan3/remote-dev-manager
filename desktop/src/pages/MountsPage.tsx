import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  HardDrive,
  Plus,
  Play,
  Square,
  RotateCw,
  Trash2,
  ScrollText,
  Info,
  ArrowRight,
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
import { Textarea } from '@/components/ui/textarea'
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/page-header'
import { StatusBadge } from '@/components/status-badge'
import { EmptyState } from '@/components/empty-state'

interface MountDef {
  name: string
  host?: string
  remote_path?: string
  mount_point?: string
  options?: string[]
}

interface MergedMount {
  name: string
  def: MountDef | undefined
  svc: ServiceInfo | undefined
}

type MountBody = {
  name: string
  host: string
  remote_path: string
  mount_point?: string
  options?: string[]
}

// -------------------------------------------------------------------------
// Add mount dialog
// -------------------------------------------------------------------------

interface AddMountDialogProps {
  open: boolean
  hosts: Host[]
  workspace: string
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (body: MountBody) => void
}

function AddMountDialog({
  open,
  hosts,
  workspace,
  submitting,
  onOpenChange,
  onSubmit,
}: AddMountDialogProps) {
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [remotePath, setRemotePath] = useState('')
  const [mountPoint, setMountPoint] = useState('')
  const [options, setOptions] = useState('')

  const [wasOpen, setWasOpen] = useState(false)
  if (open && !wasOpen) {
    setWasOpen(true)
    setName('')
    setHost(hosts[0]?.name ?? '')
    setRemotePath('')
    setMountPoint('')
    setOptions('')
  }
  if (!open && wasOpen) setWasOpen(false)

  const valid = Boolean(name.trim() && host && remotePath.trim())

  const autoPlaceholder = `自动：${workspace || '<workspace>'}/mounts/${name.trim() || '<name>'}`

  const submit = () => {
    const opts = options
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    onSubmit({
      name: name.trim(),
      host,
      remote_path: remotePath.trim(),
      mount_point: mountPoint.trim() || undefined,
      options: opts.length > 0 ? opts : undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>添加目录挂载</DialogTitle>
          <DialogDescription>通过 SSHFS 把远程目录挂载到本机。</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="mount-name">名称</Label>
            <Input
              id="mount-name"
              placeholder="project-src"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="mount-host">主机</Label>
              <Select value={host} onValueChange={setHost}>
                <SelectTrigger id="mount-host" className="w-full">
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
              <Label htmlFor="mount-remote">远程路径</Label>
              <Input
                id="mount-remote"
                placeholder="/home/ubuntu/project"
                value={remotePath}
                onChange={(e) => setRemotePath(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mount-point">挂载点（可选）</Label>
            <Input
              id="mount-point"
              placeholder={autoPlaceholder}
              value={mountPoint}
              onChange={(e) => setMountPoint(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mount-options">选项（可选）</Label>
            <Textarea
              id="mount-options"
              placeholder={'reconnect\nServerAliveInterval=15'}
              value={options}
              onChange={(e) => setOptions(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">每行一个 -o 选项。</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button disabled={!valid || submitting} onClick={submit}>
            {submitting && <Loader2 className="animate-spin" />}
            创建目录挂载
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
  mount,
  onClose,
}: {
  mount: string | null
  onClose: () => void
}) {
  const open = mount !== null
  const { lines, connected } = useLogSocket('mount', mount ?? '', open)
  const [seed, setSeed] = useState<string[]>([])
  const viewportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!mount) {
      setSeed([])
      return
    }
    let cancelled = false
    void api
      .getServiceLog('mount', mount, 200)
      .then((res) => {
        if (!cancelled) setSeed(res.lines ?? [])
      })
      .catch(() => {
        if (!cancelled) setSeed([])
      })
    return () => {
      cancelled = true
    }
  }, [mount])

  const allLines = seed.length > 0 ? [...seed, ...lines] : lines

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
            {mount ? `日志 · ${mount}` : '日志'}
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
        <Button size="icon-sm" variant="ghost" disabled={disabled} onClick={onClick}>
          {busy ? <Loader2 className="animate-spin" /> : children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

interface MountRowProps {
  mount: MergedMount
  onLog: () => void
  onDelete: () => void
}

function MountRow({ mount, onLog, onDelete }: MountRowProps) {
  const [busy, setBusy] = useState<string | null>(null)
  const actionLabel: Record<string, string> = {
    start: '挂载',
    stop: '卸载',
    restart: '重新挂载',
  }
  const status: ServiceStatus = mount.svc?.status ?? 'STOPPED'
  const running = status === 'RUNNING'

  const remotePath = mount.def?.remote_path || '?'
  const mountPoint = mount.def?.mount_point || '自动'

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

  return (
    <TableRow>
      <TableCell>
        <StatusBadge status={status} />
      </TableCell>
      <TableCell className="font-medium">{mount.name}</TableCell>
      <TableCell>
        {mount.def?.host ? (
          <Badge variant="secondary">{mount.def.host}</Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="max-w-xs">
        <p className="flex items-center gap-1.5 truncate font-mono text-xs text-muted-foreground">
          <span className="truncate" title={remotePath}>
            {remotePath}
          </span>
          <ArrowRight className="size-3 shrink-0 text-muted-foreground/60" />
          <span className="truncate" title={mountPoint}>
            {mountPoint}
          </span>
        </p>
        {mount.svc?.last_error && (
          <p className="mt-0.5 truncate text-xs text-rose-500" title={mount.svc.last_error}>
            {mount.svc.last_error}
          </p>
        )}
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {mount.svc?.pid != null ? `pid ${mount.svc.pid}` : '—'}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {mount.svc?.uptime || '—'}
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-0.5">
          <IconButton
            label="挂载"
            busy={busy === 'start'}
            disabled={running || busy !== null}
            onClick={() =>
              run('start', () => api.startService('mount', mount.name), `${mount.name} 已挂载`)
            }
          >
            <Play />
          </IconButton>
          <IconButton
            label="卸载"
            busy={busy === 'stop'}
            disabled={!running || busy !== null}
            onClick={() =>
              run('stop', () => api.stopService('mount', mount.name), `${mount.name} 已卸载`)
            }
          >
            <Square />
          </IconButton>
          <IconButton
            label="重新挂载"
            busy={busy === 'restart'}
            disabled={busy !== null}
            onClick={() =>
              run(
                'restart',
                () => api.restartService('mount', mount.name),
                `${mount.name} 正在重新挂载`,
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

export default function MountsPage() {
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
  const workspace = configQuery.data?.workspace ?? ''
  const defs = (configQuery.data?.mounts ?? []) as MountDef[]

  const merged: MergedMount[] = useMemo(() => {
    const svcByName = new Map<string, ServiceInfo>()
    services
      .filter((s) => s.kind === 'mount')
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
    mutationFn: (body: MountBody) => api.addMount(body),
    onSuccess: (_d, vars) => {
      toast.success(`目录挂载 "${vars.name}" 已创建`)
      setAddOpen(false)
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
    onError: (e) =>
      toast.error('无法创建目录挂载', {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  const deleteMut = useMutation({
    mutationFn: (name: string) => api.removeMount(name),
    onSuccess: () => {
      toast.success('目录挂载已删除')
      setDeleting(null)
      void qc.invalidateQueries({ queryKey: ['config'] })
    },
    onError: (e) =>
      toast.error('无法删除目录挂载', {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<HardDrive />}
        title="目录挂载"
        description="通过 SSHFS 把远程目录挂载到本机。"
        actions={
          <Button onClick={() => setAddOpen(true)}>
            <Plus />
            添加目录挂载
          </Button>
        }
      />

      <div className="flex items-start gap-2 rounded-lg border bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0 text-primary" />
        <span>
          目录挂载需要 Linux 上的 <span className="font-mono text-foreground">sshfs</span>，
          或 Windows 上的 <span className="font-mono text-foreground">SSHFS-Win</span>。
        </span>
      </div>

      <Card className="py-0">
        <CardContent className="px-0">
          {configQuery.isLoading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : merged.length === 0 ? (
            <EmptyState
              icon={<HardDrive />}
              title="还没有目录挂载"
              description="挂载远程目录后，可以用本机工具直接编辑。"
              action={
                <Button onClick={() => setAddOpen(true)}>
                  <Plus />
                  添加目录挂载
                </Button>
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>状态</TableHead>
                  <TableHead>名称</TableHead>
                  <TableHead>主机</TableHead>
                  <TableHead>路径</TableHead>
                  <TableHead>PID</TableHead>
                  <TableHead>运行时长</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {merged.map((m) => (
                  <MountRow
                    key={m.name}
                    mount={m}
                    onLog={() => setLogName(m.name)}
                    onDelete={() => setDeleting(m.name)}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AddMountDialog
        open={addOpen}
        hosts={hosts}
        workspace={workspace}
        submitting={addMut.isPending}
        onOpenChange={setAddOpen}
        onSubmit={(body) => addMut.mutate(body)}
      />

      <LogSheet mount={logName} onClose={() => setLogName(null)} />

      <AlertDialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除目录挂载</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting ? `确定删除目录挂载 "${deleting}"？` : ''}
              该挂载会被卸载，并从配置中移除。
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
