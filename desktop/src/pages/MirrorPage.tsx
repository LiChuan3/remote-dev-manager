import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ServerCog,
  Server,
  ArrowDownToLine,
  ArrowUpFromLine,
  Activity,
  Trash2,
  Plus,
  FolderSearch,
  FileDown,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { fmtBytes } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Host, Mirror, RepoInfo } from '@/lib/types'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import { EmptyState } from '@/components/empty-state'
import { OperationGuide } from '@/components/operation-guide'

/** Loosely-typed result returned by pull/push/status rsync operations. */
interface MirrorOpResult {
  ok?: boolean
  dry_run?: boolean
  files_transferred?: number
  bytes?: number
  local_path?: string
  errors?: string[]
  message?: string
  [key: string]: unknown
}

interface ResultPanel {
  title: string
  result: MirrorOpResult
}

interface PrefillData {
  name: string
  host: string
  remote_path: string
}

function basename(p: string): string {
  const trimmed = p.replace(/\/+$/, '')
  const idx = trimmed.lastIndexOf('/')
  return idx >= 0 ? trimmed.slice(idx + 1) : trimmed
}

const directionTone = (dir: string) =>
  dir === 'pull'
    ? 'border-sky-500/30 text-sky-600 dark:text-sky-400'
    : dir === 'push'
      ? 'border-amber-500/30 text-amber-600 dark:text-amber-400'
      : 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400'

const directionLabel = (dir: string) =>
  dir === 'pull' ? '拉取' : dir === 'push' ? '推送' : '双向'

// ---------------------------------------------------------------------------
// Small labelled field wrapper (keeps Label + control aligned)
// ---------------------------------------------------------------------------

function FieldShell({
  label,
  htmlFor,
  hint,
  className,
  children,
}: {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mirror row
// ---------------------------------------------------------------------------

function MirrorRow({
  mirror,
  dryRun,
  onResult,
  onRequestDelete,
}: {
  mirror: Mirror
  dryRun: boolean
  onResult: (panel: ResultPanel) => void
  onRequestDelete: () => void
}) {
  const [busy, setBusy] = useState<null | 'pull' | 'push' | 'status'>(null)
  const actionLabel = { pull: '拉取', push: '推送', status: '状态' }

  const run = async (
    action: 'pull' | 'push' | 'status',
    fn: () => Promise<unknown>,
  ) => {
    setBusy(action)
    try {
      const res = (await fn()) as MirrorOpResult
      onResult({
        title: `${mirror.name} — ${actionLabel[action]}${
          dryRun && action !== 'status' ? '（试运行）' : ''
        }`,
        result: res ?? {},
      })
    } catch (e) {
      toast.error(`${actionLabel[action]}失败`, {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setBusy(null)
    }
  }

  return (
    <TableRow>
      <TableCell className="font-medium">{mirror.name}</TableCell>
      <TableCell className="text-muted-foreground">{mirror.host}</TableCell>
      <TableCell>
        <div className="flex flex-col gap-0.5 font-mono text-xs">
          <span>{mirror.remote_path}</span>
          <span className="text-muted-foreground">→ {mirror.local_path}</span>
        </div>
      </TableCell>
      <TableCell>
        <Badge variant="outline" className={directionTone(mirror.direction)}>
          {directionLabel(mirror.direction)}
        </Badge>
      </TableCell>
      <TableCell>
        {mirror.auto_exclude ? (
          <Badge
            variant="outline"
            className="border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
          >
            自动排除
          </Badge>
        ) : (
          <span className="text-muted-foreground text-xs">关闭</span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground font-mono text-xs">
        {fmtBytes(mirror.max_file_size)}
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="拉取"
                disabled={busy !== null}
                onClick={() =>
                  run('pull', () => api.pullMirror(mirror.name, dryRun))
                }
              >
                {busy === 'pull' ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ArrowDownToLine />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>拉取（远程 → 本地）</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="推送"
                disabled={busy !== null}
                onClick={() =>
                  run('push', () => api.pushMirror(mirror.name, dryRun))
                }
              >
                {busy === 'push' ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ArrowUpFromLine />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>推送（本地 → 远程）</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="状态"
                disabled={busy !== null}
                onClick={() => run('status', () => api.mirrorStatus(mirror.name))}
              >
                {busy === 'status' ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Activity />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>状态</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="删除"
                disabled={busy !== null}
                className="text-rose-600 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-400"
                onClick={onRequestDelete}
              >
                <Trash2 />
              </Button>
            </TooltipTrigger>
            <TooltipContent>删除镜像</TooltipContent>
          </Tooltip>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Add mirror dialog
// ---------------------------------------------------------------------------

function AddMirrorDialog({
  open,
  hosts,
  prefill,
  onOpenChange,
  onAdded,
}: {
  open: boolean
  hosts: Host[]
  prefill: PrefillData | null
  onOpenChange: (open: boolean) => void
  onAdded: () => void
}) {
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [remotePath, setRemotePath] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [autoExclude, setAutoExclude] = useState(true)
  const [maxFileSize, setMaxFileSize] = useState('10M')
  const [exclude, setExclude] = useState('')
  const [include, setInclude] = useState('')
  const [del, setDel] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // Apply prefill / defaults when the dialog opens.
  const [seeded, setSeeded] = useState(false)
  if (open && !seeded) {
    setSeeded(true)
    setName(prefill?.name ?? '')
    setHost(prefill?.host ?? hosts[0]?.name ?? '')
    setRemotePath(prefill?.remote_path ?? '')
    setLocalPath('')
    setAutoExclude(true)
    setMaxFileSize('10M')
    setExclude('')
    setInclude('')
    setDel(false)
  }
  if (!open && seeded) setSeeded(false)

  const handleOpenChange = (next: boolean) => {
    if (submitting) return
    onOpenChange(next)
  }

  const submit = async () => {
    if (!name.trim() || !host || !remotePath.trim()) {
      toast.error('名称、主机和远程路径必填')
      return
    }
    const toLines = (s: string) =>
      s
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)

    setSubmitting(true)
    try {
      await api.addMirror({
        name: name.trim(),
        host,
        remote_path: remotePath.trim(),
        local_path: localPath.trim() || undefined,
        auto_exclude: autoExclude,
        max_file_size: maxFileSize.trim(),
        exclude: toLines(exclude),
        include: toLines(include),
        delete: del,
      })
      toast.success(`同步镜像 "${name.trim()}" 已添加`)
      onAdded()
      onOpenChange(false)
    } catch (e) {
      toast.error('无法添加同步镜像', {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[calc(100vh-2rem)] overflow-hidden sm:max-w-xl"
        showCloseButton={!submitting}
      >
        <DialogHeader>
          <DialogTitle>添加同步镜像</DialogTitle>
          <DialogDescription>
            使用 rsync 将远程目录同步到本地目录。
          </DialogDescription>
        </DialogHeader>

        <OperationGuide
          compact
          title="同步镜像怎么填"
          steps={[
            "选择主机和远程路径；本地路径留空时会自动放到工作区 mirrors 目录。",
            "最大文件大小用于跳过大文件，适合避免模型权重、数据集或缓存被误同步。",
            "自动排除会跳过 .git、node_modules、__pycache__ 等常见无关目录。",
            "删除目标端多余文件是危险选项，建议先打开试运行查看计划再正式同步。",
          ]}
        />

        <ScrollArea className="-mx-1 max-h-[52vh] px-1">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FieldShell label="名称" htmlFor="mirror-name">
              <Input
                id="mirror-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-repo"
              />
            </FieldShell>
            <FieldShell label="主机" htmlFor="mirror-host">
              <Select value={host} onValueChange={setHost}>
                <SelectTrigger id="mirror-host" className="w-full">
                  <SelectValue placeholder="选择主机" />
                </SelectTrigger>
                <SelectContent>
                  {hosts.map((h) => (
                    <SelectItem key={h.name} value={h.name}>
                      {h.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldShell>
            <FieldShell
              className="sm:col-span-2"
              label="远程路径"
              htmlFor="mirror-remote"
            >
              <Input
                id="mirror-remote"
                value={remotePath}
                onChange={(e) => setRemotePath(e.target.value)}
                placeholder="~/code/my-repo"
              />
            </FieldShell>
            <FieldShell
              className="sm:col-span-2"
              label="本地路径（可选）"
              htmlFor="mirror-local"
              hint="留空则自动放到工作区的 mirrors 目录下。"
            >
              <Input
                id="mirror-local"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
                placeholder="自动：<workspace>/mirrors/<name>"
              />
            </FieldShell>
            <FieldShell
              label="最大文件大小"
              htmlFor="mirror-maxsize"
              hint="跳过大于此大小的文件（如 10M、1G）。"
            >
              <Input
                id="mirror-maxsize"
                value={maxFileSize}
                onChange={(e) => setMaxFileSize(e.target.value)}
                placeholder="10M"
              />
            </FieldShell>
            <FieldShell label="选项">
              <div className="flex flex-col gap-3 pt-1">
                <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                  <Switch
                    aria-label="自动排除无关目录"
                    checked={autoExclude}
                    onCheckedChange={setAutoExclude}
                  />
                  <span>自动排除无关目录（node_modules、.git 等）</span>
                </label>
                <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                  <Switch
                    aria-label="删除目标端多余文件"
                    checked={del}
                    onCheckedChange={setDel}
                    className="data-checked:bg-rose-500"
                  />
                  <span
                    className={cn(
                      del && 'text-rose-600 dark:text-rose-400',
                    )}
                  >
                    删除目标端多余文件
                  </span>
                </label>
              </div>
            </FieldShell>
            <FieldShell
              label="排除规则"
              htmlFor="mirror-exclude"
              hint="每行一个 glob。"
            >
              <Textarea
                id="mirror-exclude"
                value={exclude}
                onChange={(e) => setExclude(e.target.value)}
                placeholder={'*.log\nbuild/\n.cache/'}
                className="min-h-24 font-mono text-xs"
              />
            </FieldShell>
            <FieldShell
              label="包含规则"
              htmlFor="mirror-include"
              hint="每行一个 glob（优先级高于排除规则）。"
            >
              <Textarea
                id="mirror-include"
                value={include}
                onChange={(e) => setInclude(e.target.value)}
                placeholder={'*.rs\nsrc/**'}
                className="min-h-24 font-mono text-xs"
              />
            </FieldShell>
            {del && (
              <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 sm:col-span-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-500" />
                <p className="text-xs text-rose-600 dark:text-rose-400">
                  已开启删除：下次同步时，目标端存在但源端缺失的文件会被永久删除。
                </p>
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={submitting}
          >
            取消
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="animate-spin" /> : <Plus />}
            添加同步镜像
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Browse remote section
// ---------------------------------------------------------------------------

function BrowseRemote({
  hosts,
  onAddAsMirror,
}: {
  hosts: Host[]
  onAddAsMirror: (prefill: PrefillData) => void
}) {
  const [host, setHost] = useState(hosts[0]?.name ?? '')
  const [path, setPath] = useState('~')
  const [depth, setDepth] = useState(3)
  const [repos, setRepos] = useState<RepoInfo[] | null>(null)

  const browse = useMutation({
    mutationFn: () =>
      api.browseHost(host || hosts[0]?.name || '', { path, depth }),
    onSuccess: (data) => setRepos(data),
    onError: (e: unknown) =>
      toast.error('浏览失败', {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  const effectiveHost = host || hosts[0]?.name || ''

  return (
    <Card className="py-0">
      <CardHeader className="border-b py-4">
        <CardTitle className="flex items-center gap-2 text-sm">
          <FolderSearch className="text-primary size-4" /> 浏览远程仓库
        </CardTitle>
        <CardDescription>
          选择主机并扫描可同步的代码仓库。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 py-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end">
          <FieldShell label="主机" htmlFor="browse-host">
            <Select value={host} onValueChange={setHost}>
              <SelectTrigger id="browse-host" className="w-full">
                <SelectValue placeholder="选择主机" />
              </SelectTrigger>
              <SelectContent>
                {hosts.map((h) => (
                  <SelectItem key={h.name} value={h.name}>
                    {h.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldShell>
          <FieldShell label="起始路径" htmlFor="browse-path">
            <Input
              id="browse-path"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="~"
            />
          </FieldShell>
          <FieldShell label="深度" htmlFor="browse-depth">
            <Input
              id="browse-depth"
              type="number"
              min={1}
              max={6}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value) || 1)}
              className="sm:w-20"
            />
          </FieldShell>
          <Button
            variant="secondary"
            onClick={() => browse.mutate()}
            disabled={browse.isPending}
          >
            {browse.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <FolderSearch />
            )}
            扫描
          </Button>
        </div>

        {browse.isPending ? (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-8 text-sm">
            <Loader2 className="size-4 animate-spin" /> 正在扫描 {effectiveHost}…
          </div>
        ) : repos && repos.length > 0 ? (
          <div className="overflow-hidden rounded-lg ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>路径</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>大小</TableHead>
                  <TableHead>标记</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {repos.map((r) => (
                  <TableRow key={r.path}>
                    <TableCell className="font-mono text-xs">{r.path}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {r.type}
                    </TableCell>
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {fmtBytes(r.size)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {r.markers.length === 0 ? (
                          <span className="text-muted-foreground text-xs">
                            —
                          </span>
                        ) : (
                          r.markers.map((m) => (
                            <Badge key={m} variant="secondary">
                              {m}
                            </Badge>
                          ))
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          onAddAsMirror({
                            name: basename(r.path),
                            remote_path: r.path,
                            host: effectiveHost,
                          })
                        }
                      >
                        <Plus />
                        添加为镜像
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : repos && repos.length === 0 ? (
          <p className="text-muted-foreground py-4 text-center text-sm">
            在 {path} 下没有发现仓库。
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Quick file clone section
// ---------------------------------------------------------------------------

function QuickFileClone({ hosts }: { hosts: Host[] }) {
  const [host, setHost] = useState(hosts[0]?.name ?? '')
  const [remotePath, setRemotePath] = useState('')
  const [localPath, setLocalPath] = useState('')

  const clone = useMutation({
    mutationFn: () =>
      api.fetchFile({
        host: host || hosts[0]?.name || '',
        remote_path: remotePath.trim(),
        local_path: localPath.trim() || undefined,
      }),
    onSuccess: (res) => {
      const r = (res ?? {}) as { bytes?: number; local_path?: string }
      toast.success('文件已拉取', {
        description:
          (r.bytes != null ? `已复制 ${fmtBytes(r.bytes)}` : '已复制') +
          (r.local_path ? ` → ${r.local_path}` : ''),
      })
    },
    onError: (e: unknown) =>
      toast.error('拉取失败', {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  return (
    <Card className="py-0">
      <CardHeader className="border-b py-4">
        <CardTitle className="flex items-center gap-2 text-sm">
          <FileDown className="text-primary size-4" /> 快速拉取单文件
        </CardTitle>
        <CardDescription>
          将单个远程文件拉取到本机，适合临时查看文件而不创建完整镜像。
        </CardDescription>
      </CardHeader>
      <CardContent className="py-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[auto_1fr_1fr_auto] sm:items-end">
          <FieldShell label="主机" htmlFor="clone-host">
            <Select value={host} onValueChange={setHost}>
              <SelectTrigger id="clone-host" className="w-full">
                <SelectValue placeholder="选择主机" />
              </SelectTrigger>
              <SelectContent>
                {hosts.map((h) => (
                  <SelectItem key={h.name} value={h.name}>
                    {h.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FieldShell>
          <FieldShell label="远程文件" htmlFor="clone-remote">
            <Input
              id="clone-remote"
              value={remotePath}
              onChange={(e) => setRemotePath(e.target.value)}
              placeholder="~/code/app/src/main.rs"
            />
          </FieldShell>
          <FieldShell label="本地路径（可选）" htmlFor="clone-local">
            <Input
              id="clone-local"
              value={localPath}
              onChange={(e) => setLocalPath(e.target.value)}
              placeholder="自动：工作区"
            />
          </FieldShell>
          <Button
            onClick={() => {
              if (!remotePath.trim()) {
                toast.error('远程文件路径必填')
                return
              }
              clone.mutate()
            }}
            disabled={clone.isPending}
          >
            {clone.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <FileDown />
            )}
            拉取
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Result dialog (rsync plan / result)
// ---------------------------------------------------------------------------

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-muted/40 rounded-lg p-3 ring-1 ring-foreground/10">
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function ResultDialog({
  panel,
  onClose,
}: {
  panel: ResultPanel | null
  onClose: () => void
}) {
  const r = panel?.result
  const errors = Array.isArray(r?.errors) ? r?.errors : []

  return (
    <Dialog open={panel !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{panel?.title}</DialogTitle>
          <DialogDescription>rsync 结果</DialogDescription>
        </DialogHeader>

        <OperationGuide
          compact
          title="怎么看结果"
          steps={[
            "传输文件和字节数表示本次实际或试运行计划涉及的内容。",
            "试运行标记表示没有写入任何变更，可用于正式拉取或推送前确认风险。",
            "原始输出保留后端返回的完整信息，排查错误时可以直接查看或复制。",
          ]}
        />

        {r && (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <Stat
                label="传输文件"
                value={
                  r.files_transferred != null
                    ? String(r.files_transferred)
                    : '—'
                }
              />
              <Stat
                label="字节数"
                value={r.bytes != null ? fmtBytes(r.bytes) : '—'}
              />
            </div>
            {r.local_path && (
              <div>
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                  本地路径
                </p>
                <p className="mt-0.5 font-mono text-xs break-all">
                  {r.local_path}
                </p>
              </div>
            )}
            {r.dry_run && (
              <Badge
                variant="outline"
                className="border-amber-500/30 text-amber-600 dark:text-amber-400"
              >
                试运行：不会写入任何变更
              </Badge>
            )}
            {r.message && (
              <p className="bg-muted/50 text-muted-foreground rounded-lg p-2.5 font-mono text-xs ring-1 ring-foreground/10">
                {r.message}
              </p>
            )}
            {errors && errors.length > 0 && (
              <div className="space-y-1 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3">
                <p className="flex items-center gap-1.5 text-xs font-medium text-rose-600 dark:text-rose-400">
                  <AlertTriangle className="size-3.5" /> {errors.length} 个错误
                </p>
                <ul className="space-y-0.5 font-mono text-xs text-rose-600/90 dark:text-rose-400/90">
                  {errors.map((err, i) => (
                    <li key={i} className="break-all">
                      {err}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <p className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">
                原始输出
              </p>
              <ScrollArea className="bg-muted/50 max-h-56 rounded-lg ring-1 ring-foreground/10">
                <pre className="p-3 font-mono text-xs whitespace-pre-wrap break-all">
                  {JSON.stringify(r, null, 2)}
                </pre>
              </ScrollArea>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function MirrorPage() {
  const queryClient = useQueryClient()
  const [dryRun, setDryRun] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [prefill, setPrefill] = useState<PrefillData | null>(null)
  const [resultPanel, setResultPanel] = useState<ResultPanel | null>(null)
  const [deleting, setDeleting] = useState<Mirror | null>(null)
  const [deletingBusy, setDeletingBusy] = useState(false)

  const configQuery = useQuery({
    queryKey: ['config'],
    queryFn: () => api.getConfig(),
    staleTime: 10000,
  })

  const mirrorsQuery = useQuery({
    queryKey: ['mirrors'],
    queryFn: () => api.listMirrors(),
  })

  const hosts = useMemo(() => configQuery.data?.hosts ?? [], [configQuery.data])
  const mirrors = mirrorsQuery.data ?? []

  const invalidateMirrors = () =>
    void queryClient.invalidateQueries({ queryKey: ['mirrors'] })

  const openAdd = (data: PrefillData | null) => {
    setPrefill(data)
    setAddOpen(true)
  }

  const confirmDelete = async () => {
    if (!deleting) return
    setDeletingBusy(true)
    try {
      await api.removeMirror(deleting.name)
      toast.success(`已删除 ${deleting.name}`)
      setDeleting(null)
      invalidateMirrors()
    } catch (e) {
      toast.error('删除失败', {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setDeletingBusy(false)
    }
  }

  const noHosts = !configQuery.isLoading && hosts.length === 0

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<ServerCog />}
        title="同步镜像"
        description="通过 SSH 上的 rsync，让远程项目目录与本地副本保持同步。"
        actions={
          <>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <Switch
                aria-label="试运行"
                checked={dryRun}
                onCheckedChange={setDryRun}
              />
              <span>试运行</span>
            </label>
            <Button onClick={() => openAdd(null)} disabled={noHosts}>
              <Plus />
              添加同步镜像
            </Button>
          </>
        }
      />

      <OperationGuide
        title="同步镜像页怎么用"
        steps={[
          "先添加主机，再创建同步镜像，把远程项目目录映射到本机目录。",
          "日常修改建议先拉取远程到本地，在本地编辑后再推送回服务器。",
          "开启试运行后，拉取和推送只展示计划，不会写入文件，适合检查删除或覆盖风险。",
          "下方可扫描远程仓库并添加为镜像，也可以快速拉取单个文件用于临时查看。",
        ]}
        notes={["需要可靠读写时优先使用同步镜像，而不是把 SSHFS 挂载当作长期同步方式。"]}
      />

      {noHosts ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={<Server />}
              title="还没有配置主机"
              description="请先添加远程主机，再创建同步镜像。"
              action={
                <Button asChild>
                  <Link to="/hosts">
                    <Server />
                    添加主机
                  </Link>
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="py-0">
            <CardHeader className="flex flex-row items-center justify-between border-b py-4">
              <div className="space-y-1">
                <CardTitle>同步镜像</CardTitle>
                <CardDescription>
                  {dryRun
                    ? '试运行已开启：拉取/推送只预览，不写入。'
                    : '可对每个镜像执行拉取、推送或状态检查。'}
                </CardDescription>
              </div>
              {mirrors.length > 0 && (
                <Badge variant="secondary">{mirrors.length}</Badge>
              )}
            </CardHeader>

            <CardContent className="px-0 pb-0">
              {mirrorsQuery.isLoading ? (
                <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
                  <Loader2 className="size-4 animate-spin" /> 正在加载同步镜像…
                </div>
              ) : mirrors.length === 0 ? (
                <EmptyState
                  icon={<ServerCog />}
                  title="还没有同步镜像"
                  description="可以手动添加镜像，也可以在下方浏览主机发现可同步仓库。"
                  action={
                    <Button onClick={() => openAdd(null)}>
                      <Plus />
                      添加同步镜像
                    </Button>
                  }
                />
              ) : (
                <TooltipProvider>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>名称</TableHead>
                        <TableHead>主机</TableHead>
                        <TableHead>路径</TableHead>
                        <TableHead>方向</TableHead>
                        <TableHead>排除</TableHead>
                        <TableHead>最大大小</TableHead>
                        <TableHead className="text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {mirrors.map((m) => (
                        <MirrorRow
                          key={m.name}
                          mirror={m}
                          dryRun={dryRun}
                          onResult={setResultPanel}
                          onRequestDelete={() => setDeleting(m)}
                        />
                      ))}
                    </TableBody>
                  </Table>
                </TooltipProvider>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-6">
            <BrowseRemote hosts={hosts} onAddAsMirror={openAdd} />
            <QuickFileClone hosts={hosts} />
          </div>
        </>
      )}

      {mirrorsQuery.isError && (
        <p className="text-muted-foreground flex items-center justify-center gap-1.5 text-center text-xs">
          <AlertTriangle className="size-3.5 text-rose-500" /> 无法加载
          同步镜像。{' '}
          <button
            className="text-destructive underline-offset-4 hover:underline"
            onClick={() => void mirrorsQuery.refetch()}
          >
            重试
          </button>
        </p>
      )}

      <AddMirrorDialog
        open={addOpen}
        hosts={hosts}
        prefill={prefill}
        onOpenChange={setAddOpen}
        onAdded={invalidateMirrors}
      />

      <ResultDialog panel={resultPanel} onClose={() => setResultPanel(null)} />

      <AlertDialog
        open={deleting !== null}
        onOpenChange={(o) => {
          if (!o && !deletingBusy) setDeleting(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              删除同步镜像{deleting ? ` "${deleting.name}"` : ''}？
            </AlertDialogTitle>
            <AlertDialogDescription>
              这只会删除镜像定义，本地文件会保留。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingBusy}>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deletingBusy}
              onClick={(e) => {
                e.preventDefault()
                void confirmDelete()
              }}
            >
              {deletingBusy ? <Loader2 className="animate-spin" /> : <Trash2 />}
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
