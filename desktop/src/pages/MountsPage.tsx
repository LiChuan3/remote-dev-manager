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
  ArrowRight,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Download,
} from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useStatusSocket, useLogSocket } from '@/lib/ws'
import type { Host, MountDiagnostics, ServiceInfo, ServiceStatus } from '@/lib/types'
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
import { OperationGuide } from '@/components/operation-guide'
import { ResizableSheetContent } from '@/components/resizable-sheet-content'

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

function MountDiagnosticsPanel({
  diagnostics,
  loading,
  error,
  installing,
  onRetry,
  onInstall,
}: {
  diagnostics: MountDiagnostics | undefined
  loading: boolean
  error: unknown
  installing: boolean
  onRetry: () => void
  onInstall: () => void
}) {
  const ready = diagnostics?.ready === true
  const missing = diagnostics?.missing ?? []
  const canInstall = diagnostics?.platform === 'Windows' && !ready
  const statusText = loading
    ? '正在检查挂载依赖'
    : ready
      ? '目录挂载环境可用'
      : '目录挂载环境不完整'
  const detail = ready
    ? diagnostics?.sshfs_version || diagnostics?.sshfs_path || '已找到 sshfs'
    : missing.length > 0
      ? `缺少：${missing.join('、')}`
      : error instanceof Error
        ? error.message
        : '未找到可用的 sshfs 环境'

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/40 px-4 py-3 text-sm sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        {loading ? (
          <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground" />
        ) : ready ? (
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
        ) : (
          <XCircle className="mt-0.5 size-4 shrink-0 text-rose-600 dark:text-rose-400" />
        )}
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{statusText}</p>
            {diagnostics?.platform ? (
              <Badge variant="secondary">{diagnostics.platform}</Badge>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground break-all">{detail}</p>
          {diagnostics ? (
            <div className="flex flex-wrap gap-1.5 pt-1">
              <Badge variant={diagnostics.sshfs_found ? 'default' : 'outline'}>
                sshfs {diagnostics.sshfs_found ? '已安装' : '未找到'}
              </Badge>
              {diagnostics.platform === 'Windows' ? (
                <>
                  <Badge variant={diagnostics.sshfs_win_found ? 'default' : 'outline'}>
                    SSHFS-Win {diagnostics.sshfs_win_found ? '已安装' : '未找到'}
                  </Badge>
                  <Badge variant={diagnostics.winfsp_found ? 'default' : 'outline'}>
                    WinFsp {diagnostics.winfsp_found ? '已安装' : '未找到'}
                  </Badge>
                </>
              ) : null}
            </div>
          ) : null}
          {diagnostics?.sshfs_path ? (
            <p className="text-xs text-muted-foreground break-all">
              sshfs：{diagnostics.sshfs_path}
            </p>
          ) : null}
          {!ready ? (
            <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              Windows 需要同时安装 WinFsp 和 SSHFS-Win，安装后重新打开应用即可。
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            SSHFS/SSHFS-Win 挂载更适合读取、浏览和临时编辑；写入受网络、缓存和 FUSE/WinFsp
            影响，不建议作为可靠同步方式。需要稳定读写时，建议先拉取或镜像到本地修改，再同步回服务器。
          </p>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {canInstall ? (
          <Button size="sm" onClick={onInstall} disabled={installing}>
            {installing ? <Loader2 className="animate-spin" /> : <Download />}
            一键安装
          </Button>
        ) : null}
        <Button variant="outline" size="sm" onClick={onRetry} disabled={loading}>
          {loading ? <Loader2 className="animate-spin" /> : null}
          重新检查
        </Button>
      </div>
    </div>
  )
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
      <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>添加目录挂载</DialogTitle>
          <DialogDescription>通过 SSHFS 把远程目录挂载到本机。</DialogDescription>
        </DialogHeader>

        <OperationGuide
          compact
          title="目录挂载怎么填"
          steps={[
            "选择已测试可用的主机，远程路径填写服务器上的目录，例如 /home/ubuntu/project。",
            "挂载点可留空，应用会自动放到工作区 mounts 目录；也可以填一个本机空目录。",
            "选项每行一个 sshfs -o 参数，例如 reconnect 或 ServerAliveInterval=15。",
            "创建后在列表里点击挂载；需要排查时打开日志查看 sshfs 输出。",
          ]}
          notes={[
            "SSHFS/SSHFS-Win 更适合读取、浏览和临时编辑；需要稳定读写同步时，建议使用同步镜像拉取到本地修改后再推送。",
          ]}
        />

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

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
      <ResizableSheetContent
        title={mount ? `日志 · ${mount}` : '日志'}
        defaultWidth={720}
        minWidth={380}
        maxWidth={1040}
        storageKey="rdm:mount-log-width"
      >
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
        <div className="px-4 pb-4">
          <OperationGuide
            compact
            title="日志面板"
            steps={[
              "打开后会先加载最近日志，再持续追加实时输出。",
              "如果缺少 WinFsp、SSHFS-Win、权限不足或远程路径不存在，错误会显示在这里。",
              "右侧面板左边缘可以拖动调整宽度，右上角可以最小化或关闭。",
            ]}
          />
        </div>
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
      </ResizableSheetContent>
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
  const diagnosticsQuery = useQuery({
    queryKey: ['mount-diagnostics'],
    queryFn: () => api.mountDiagnostics(),
    refetchInterval: 30000,
    retry: false,
  })

  const [addOpen, setAddOpen] = useState(false)
  const [logName, setLogName] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [installOpen, setInstallOpen] = useState(false)

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

  const installMut = useMutation({
    mutationFn: () => api.installMountDependencies(),
    onSuccess: (res) => {
      setInstallOpen(false)
      if (res.ok) {
        toast.success('安装窗口已打开', {
          description: res.message || '请在管理员 PowerShell 中完成安装。',
        })
      } else {
        toast.error('无法启动安装器', { description: res.message })
      }
    },
    onError: (e) =>
      toast.error('无法启动安装器', {
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

      <OperationGuide
        title="目录挂载页怎么用"
        steps={[
          "先确认页面顶部依赖检查为可用；缺少 WinFsp 或 SSHFS-Win 时可点一键安装。",
          "添加挂载时选择主机和远程目录，保存后点击挂载，状态变为运行中即可在本机访问目录。",
          "卸载会停止本机挂载，不会删除远程目录；删除配置会先卸载再从应用配置移除。",
          "写入远程文件不建议依赖挂载作为稳定同步方案，重要修改请使用同步镜像拉取和推送。",
        ]}
        notes={["窗口变窄时表格可横向滚动；日志面板支持拖动宽度和最小化。"]}
      />

      <MountDiagnosticsPanel
        diagnostics={diagnosticsQuery.data}
        loading={diagnosticsQuery.isLoading || diagnosticsQuery.isFetching}
        error={diagnosticsQuery.error}
        installing={installMut.isPending}
        onRetry={() => void diagnosticsQuery.refetch()}
        onInstall={() => setInstallOpen(true)}
      />

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

      <AlertDialog open={installOpen} onOpenChange={setInstallOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>安装目录挂载依赖</AlertDialogTitle>
            <AlertDialogDescription>
              将打开管理员 PowerShell，并通过 winget 安装 WinFsp 和 SSHFS-Win。
              安装过程中可能出现 UAC 权限确认窗口。安装完成后请回到应用点击“重新检查”。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={installMut.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                installMut.mutate()
              }}
              disabled={installMut.isPending}
            >
              {installMut.isPending ? <Loader2 className="animate-spin" /> : null}
              打开安装器
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
