import { useMemo, useState } from "react"
import type { ChangeEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Server,
  Plus,
  Pencil,
  Trash2,
  Activity,
  FolderGit2,
  Package,
  Loader2,
  Search,
  Download,
} from "lucide-react"
import { toast } from "sonner"

import { api, ApiError } from "@/lib/api"
import { fmtBytes } from "@/lib/format"
import type { Host, RepoInfo, SshConfigHost, TestResult } from "@/lib/types"

import { PageHeader } from "@/components/page-header"
import { EmptyState } from "@/components/empty-state"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

// ---------------------------------------------------------------------------
// Form helpers
// ---------------------------------------------------------------------------

interface HostForm {
  name: string
  user: string
  host: string
  port: string
  identity: string
}

const emptyForm: HostForm = {
  name: "",
  user: "",
  host: "",
  port: "22",
  identity: "",
}

function toBody(f: HostForm) {
  return {
    name: f.name.trim(),
    user: f.user.trim(),
    host: f.host.trim(),
    port: Number(f.port) || 22,
    identity: f.identity.trim() || undefined,
  }
}

function errMessage(e: unknown): string | undefined {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return undefined
}

// ---------------------------------------------------------------------------
// Add / Edit dialog
// ---------------------------------------------------------------------------

interface HostFormDialogProps {
  open: boolean
  title: string
  initial: HostForm
  lockName?: boolean
  submitting: boolean
  onClose: () => void
  onSubmit: (form: HostForm) => void
}

function HostFormDialog({
  open,
  title,
  initial,
  lockName,
  submitting,
  onClose,
  onSubmit,
}: HostFormDialogProps) {
  const [form, setForm] = useState<HostForm>(initial)

  // Re-seed local state whenever the dialog is (re)opened with new initial values.
  const [seed, setSeed] = useState(initial)
  if (open && seed !== initial) {
    setSeed(initial)
    setForm(initial)
  }

  const set =
    (k: keyof HostForm) => (e: ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [k]: e.target.value }))

  const valid =
    form.name.trim() !== "" && form.user.trim() !== "" && form.host.trim() !== ""

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            填写远程 SSH 主机的连接信息。
          </DialogDescription>
        </DialogHeader>

        <form
          id="host-form"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (valid && !submitting) onSubmit(form)
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="host-name">名称</Label>
            <Input
              id="host-name"
              placeholder="my-server"
              value={form.name}
              onChange={set("name")}
              disabled={lockName}
              autoFocus={!lockName}
            />
            {lockName ? (
              <p className="text-muted-foreground text-xs">
                名称创建后不能修改。
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="host-user">用户名</Label>
              <Input
                id="host-user"
                placeholder="ubuntu"
                value={form.user}
                onChange={set("user")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="host-host">主机地址</Label>
              <Input
                id="host-host"
                placeholder="1.2.3.4"
                value={form.host}
                onChange={set("host")}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="host-port">端口</Label>
              <Input
                id="host-port"
                type="number"
                placeholder="22"
                value={form.port}
                onChange={set("port")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="host-identity">密钥</Label>
              <Input
                id="host-identity"
                placeholder="~/.ssh/id_ed25519"
                value={form.identity}
                onChange={set("identity")}
              />
              <p className="text-muted-foreground text-xs">
                可选。留空则使用 SSH agent 或默认密钥。
              </p>
            </div>
          </div>
        </form>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={submitting}
          >
            取消
          </Button>
          <Button type="submit" form="host-form" disabled={!valid || submitting}>
            {submitting ? <Loader2 className="animate-spin" /> : null}
            保存主机
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// SSH config import dialog
// ---------------------------------------------------------------------------

interface ImportSshConfigDialogProps {
  open: boolean
  hosts: Host[]
  importingName: string | null
  onClose: () => void
  onImport: (host: SshConfigHost) => void
}

function ImportSshConfigDialog({
  open,
  hosts,
  importingName,
  onClose,
  onImport,
}: ImportSshConfigDialogProps) {
  const sshConfigQuery = useQuery({
    queryKey: ["hosts", "ssh-config"],
    queryFn: () => api.listSshConfigHosts(),
    enabled: open,
    retry: false,
  })

  const existingNames = useMemo(
    () => new Set(hosts.map((host) => host.name)),
    [hosts],
  )
  const candidates = sshConfigQuery.data ?? []

  const proxyLabel = (item: SshConfigHost) => {
    if (item.proxy_jump) return `ProxyJump: ${item.proxy_jump}`
    if (item.proxy_command) return "ProxyCommand"
    return "默认 SSH 配置"
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-hidden sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>导入 SSH 配置</DialogTitle>
          <DialogDescription>
            读取本机 ~/.ssh/config，导入后通过 SSH 别名连接。
          </DialogDescription>
        </DialogHeader>

        {sshConfigQuery.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : sshConfigQuery.isError ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border px-6 py-10 text-center">
            <p className="text-sm text-rose-600 dark:text-rose-400">
              无法读取 SSH 配置。
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void sshConfigQuery.refetch()}
            >
              重试
            </Button>
          </div>
        ) : candidates.length === 0 ? (
          <div className="rounded-lg border px-6 py-10 text-center">
            <p className="text-muted-foreground text-sm">
              没有找到可导入的 SSH Host。
            </p>
          </div>
        ) : (
          <ScrollArea className="max-h-[52vh] rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>别名</TableHead>
                  <TableHead>实际地址</TableHead>
                  <TableHead>用户 / 端口</TableHead>
                  <TableHead>密钥 / 跳板</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.map((item) => {
                  const already = existingNames.has(item.name)
                  const missingUser = item.user.trim() === ""
                  const busy = importingName === item.name
                  return (
                    <TableRow key={`${item.source}-${item.name}`}>
                      <TableCell className="font-medium">{item.name}</TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {item.hostname || item.host}
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {item.user || "未设置"}:{item.port}
                      </TableCell>
                      <TableCell className="max-w-64">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-muted-foreground truncate font-mono text-xs">
                            {item.identity || "agent / 默认"}
                          </span>
                          <span className="text-muted-foreground truncate text-xs">
                            {proxyLabel(item)}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant={already ? "secondary" : "outline"}
                          disabled={already || missingUser || importingName !== null}
                          onClick={() => onImport(item)}
                        >
                          {busy ? <Loader2 className="animate-spin" /> : <Download />}
                          {already ? "已导入" : missingUser ? "缺少用户" : "导入"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </ScrollArea>
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
// Browse repos sheet
// ---------------------------------------------------------------------------

function basename(p: string) {
  const parts = p.replace(/\/+$/, "").split("/")
  return parts[parts.length - 1] || p
}

function BrowseSheet({
  host,
  onClose,
}: {
  host: Host | null
  onClose: () => void
}) {
  const [path, setPath] = useState("~")
  const [depth, setDepth] = useState("3")
  const [repos, setRepos] = useState<RepoInfo[] | null>(null)
  const [adding, setAdding] = useState<string | null>(null)

  // Re-seed when a new host opens the sheet.
  const [seedHost, setSeedHost] = useState<Host | null>(null)
  if (host && host !== seedHost) {
    setSeedHost(host)
    setPath("~")
    setDepth("3")
    setRepos(null)
    setAdding(null)
  }

  const browse = useMutation({
    mutationFn: () =>
      api.browseHost(host!.name, {
        path: path.trim() || "~",
        depth: Number(depth) || 3,
      }),
    onSuccess: (data) => setRepos(data),
    onError: (e) =>
      toast.error("浏览失败", { description: errMessage(e) }),
  })

  const addMirror = async (repo: RepoInfo) => {
    if (!host) return
    const name = basename(repo.path)
    setAdding(repo.path)
    try {
      await api.addMirror({
        name,
        host: host.name,
        remote_path: repo.path,
        auto_exclude: true,
      })
      toast.success(`镜像 "${name}" 已添加`, {
        description: "前往同步镜像页面执行同步。",
      })
    } catch (e) {
      toast.error("无法添加镜像", { description: errMessage(e) })
    } finally {
      setAdding(null)
    }
  }

  return (
    <Sheet open={host !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="w-full gap-0 sm:max-w-lg"
      >
        <SheetHeader>
          <SheetTitle>
            {host ? `浏览 ${host.name} 上的仓库` : "浏览"}
          </SheetTitle>
          <SheetDescription>
            扫描指定路径下可同步到本机的代码仓库。
          </SheetDescription>
        </SheetHeader>

        <div className="flex items-end gap-2 px-4 pb-4">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="browse-path">起始路径</Label>
            <Input
              id="browse-path"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="~"
            />
          </div>
          <div className="w-20 space-y-1.5">
            <Label htmlFor="browse-depth">深度</Label>
            <Input
              id="browse-depth"
              type="number"
              value={depth}
              onChange={(e) => setDepth(e.target.value)}
            />
          </div>
          <Button
            onClick={() => browse.mutate()}
            disabled={browse.isPending}
          >
            {browse.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Search />
            )}
            扫描
          </Button>
        </div>

        <ScrollArea className="flex-1 border-t">
          <div className="p-4">
            {browse.isPending ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : repos === null ? (
              <p className="text-muted-foreground py-10 text-center text-sm">
                输入路径并扫描，以发现远程仓库。
              </p>
            ) : repos.length === 0 ? (
              <p className="text-muted-foreground py-10 text-center text-sm">
                在 {path || "~"} 下没有发现仓库。
              </p>
            ) : (
              <ul className="space-y-2">
                {repos.map((repo) => (
                  <li
                    key={repo.path}
                    className="border-border bg-muted/30 flex items-center gap-3 rounded-lg border p-3"
                  >
                    <FolderGit2 className="text-primary size-4 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-xs">{repo.path}</p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {repo.type ? (
                          <Badge variant="secondary">{repo.type}</Badge>
                        ) : null}
                        <span className="text-muted-foreground text-xs">
                          {fmtBytes(repo.size)}
                        </span>
                        {repo.markers.map((m) => (
                          <Badge key={m} variant="outline">
                            {m}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => addMirror(repo)}
                      disabled={adding !== null}
                    >
                      {adding === repo.path ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <Package />
                      )}
                      添加镜像
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

// ---------------------------------------------------------------------------
// Host row
// ---------------------------------------------------------------------------

function TestResultCell({ result }: { result: TestResult | undefined }) {
  if (!result) {
    return <span className="text-muted-foreground text-xs">—</span>
  }
  if (!result.ok) {
    return (
      <Badge
        variant="outline"
        className="border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400"
      >
        失败
      </Badge>
    )
  }
  return (
    <div className="flex flex-col gap-0.5">
      <Badge
        variant="outline"
        className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
      >
        OK · {result.latency_ms}ms
      </Badge>
      {result.whoami || result.hostname || result.os ? (
        <span className="text-muted-foreground truncate font-mono text-[11px]">
          {result.whoami}@{result.hostname}
          {result.os ? ` (${result.os})` : ""}
        </span>
      ) : null}
    </div>
  )
}

interface HostRowProps {
  host: Host
  testResult: TestResult | undefined
  testing: boolean
  onTest: () => void
  onBrowse: () => void
  onEdit: () => void
  onDelete: () => void
}

function HostRow({
  host,
  testResult,
  testing,
  onTest,
  onBrowse,
  onEdit,
  onDelete,
}: HostRowProps) {
  const identityLabel = host.identity ? host.identity : "agent / 默认"

  const iconBtn = (
    label: string,
    icon: React.ReactNode,
    onClick: () => void,
    extra?: { disabled?: boolean; danger?: boolean },
  ) => (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={onClick}
          disabled={extra?.disabled}
          className={extra?.danger ? "text-rose-500 hover:text-rose-500" : undefined}
          aria-label={label}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )

  return (
    <TableRow>
      <TableCell className="font-medium">{host.name}</TableCell>
      <TableCell className="text-muted-foreground font-mono text-xs">
        {host.user}@{host.host}:{host.port}
      </TableCell>
      <TableCell className="text-muted-foreground font-mono text-xs">
        {identityLabel}
      </TableCell>
      <TableCell>
        <TestResultCell result={testResult} />
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          {iconBtn(
            "测试连接",
            testing ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Activity />
            ),
            onTest,
            { disabled: testing },
          )}
          {iconBtn("浏览仓库", <FolderGit2 />, onBrowse)}
          {iconBtn("编辑", <Pencil />, onEdit)}
          {iconBtn("删除", <Trash2 />, onDelete, { danger: true })}
        </div>
      </TableCell>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HostsPage() {
  const qc = useQueryClient()

  const hostsQuery = useQuery({
    queryKey: ["hosts"],
    queryFn: () => api.listHosts(),
  })

  const [addOpen, setAddOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editing, setEditing] = useState<Host | null>(null)
  const [deleting, setDeleting] = useState<Host | null>(null)
  const [browsing, setBrowsing] = useState<Host | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [testingName, setTestingName] = useState<string | null>(null)

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["hosts"] })
    void qc.invalidateQueries({ queryKey: ["config"] })
  }

  const addMut = useMutation({
    mutationFn: (form: HostForm) => api.addHost(toBody(form)),
    onSuccess: (host) => {
      toast.success(`主机 "${host.name}" 已添加`)
      setAddOpen(false)
      invalidate()
    },
    onError: (e) =>
      toast.error("无法添加主机", { description: errMessage(e) }),
  })

  const editMut = useMutation({
    mutationFn: ({ name, form }: { name: string; form: HostForm }) =>
      api.updateHost(name, toBody(form)),
    onSuccess: (host) => {
      toast.success(`主机 "${host.name}" 已更新`)
      setEditing(null)
      invalidate()
    },
    onError: (e) =>
      toast.error("无法更新主机", { description: errMessage(e) }),
  })

  const deleteMut = useMutation({
    mutationFn: (name: string) => api.removeHost(name),
    onSuccess: () => {
      toast.success("主机已删除")
      setDeleting(null)
      invalidate()
    },
    onError: (e) =>
      toast.error("无法删除主机", { description: errMessage(e) }),
  })

  const importMut = useMutation({
    mutationFn: (candidate: SshConfigHost) =>
      api.addHost({
        name: candidate.name,
        user: candidate.user,
        host: candidate.host,
        port: candidate.port,
        identity: candidate.identity || undefined,
      }),
    onSuccess: (host) => {
      toast.success(`主机 "${host.name}" 已导入`)
      invalidate()
    },
    onError: (e) =>
      toast.error("无法导入主机", { description: errMessage(e) }),
  })

  const runTest = async (host: Host) => {
    setTestingName(host.name)
    try {
      const res = await api.testHost(host.name)
      setTestResults((prev) => ({ ...prev, [host.name]: res }))
      if (res.ok) {
        toast.success(`${host.name}: ${res.latency_ms}ms`, {
          description: `${res.whoami}@${res.hostname} (${res.os})`,
        })
      } else {
        toast.error(`${host.name}: 连接失败`, {
          description: res.message || undefined,
        })
      }
    } catch (e) {
      const failed: TestResult = {
        ok: false,
        latency_ms: 0,
        message: errMessage(e) ?? "测试失败",
        whoami: "",
        hostname: "",
        os: "",
      }
      setTestResults((prev) => ({ ...prev, [host.name]: failed }))
      toast.error(`${host.name}: 测试失败`, { description: failed.message })
    } finally {
      setTestingName(null)
    }
  }

  const hosts = hostsQuery.data ?? []

  const editInitial: HostForm = useMemo(
    () =>
      editing
        ? {
            name: editing.name,
            user: editing.user,
            host: editing.host,
            port: String(editing.port),
            identity: editing.identity ?? "",
          }
        : emptyForm,
    [editing],
  )

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-6">
        <PageHeader
          title="主机"
          description="添加 SSH 远程主机，测试连通性，并浏览可同步的仓库。"
          icon={<Server />}
          actions={
            <>
              <Button variant="outline" onClick={() => setImportOpen(true)}>
                <Download />
                导入 SSH 配置
              </Button>
              <Button onClick={() => setAddOpen(true)}>
                <Plus />
                添加主机
              </Button>
            </>
          }
        />

        <Card className="py-0">
          <CardContent className="px-0">
            {hostsQuery.isLoading ? (
              <div className="space-y-3 p-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : hostsQuery.isError ? (
              <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
                <p className="text-sm text-rose-600 dark:text-rose-400">
                  无法加载主机。
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void hostsQuery.refetch()}
                >
                  重试
                </Button>
              </div>
            ) : hosts.length === 0 ? (
              <EmptyState
                icon={<Server />}
                title="还没有主机"
                description="添加远程主机后，即可创建端口转发、目录挂载和同步镜像。"
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button variant="outline" onClick={() => setImportOpen(true)}>
                      <Download />
                      导入 SSH 配置
                    </Button>
                    <Button onClick={() => setAddOpen(true)}>
                      <Plus />
                      添加主机
                    </Button>
                  </div>
                }
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead>
                    <TableHead>连接</TableHead>
                    <TableHead>密钥</TableHead>
                    <TableHead>最近测试</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {hosts.map((host) => (
                    <HostRow
                      key={host.name}
                      host={host}
                      testResult={testResults[host.name]}
                      testing={testingName === host.name}
                      onTest={() => runTest(host)}
                      onBrowse={() => setBrowsing(host)}
                      onEdit={() => setEditing(host)}
                      onDelete={() => setDeleting(host)}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Add */}
        <HostFormDialog
          open={addOpen}
          title="添加主机"
          initial={emptyForm}
          submitting={addMut.isPending}
          onClose={() => setAddOpen(false)}
          onSubmit={(form) => addMut.mutate(form)}
        />

        {/* Import SSH config */}
        <ImportSshConfigDialog
          open={importOpen}
          hosts={hosts}
          importingName={importMut.isPending ? importMut.variables?.name ?? null : null}
          onClose={() => setImportOpen(false)}
          onImport={(host) => importMut.mutate(host)}
        />

        {/* Edit */}
        <HostFormDialog
          open={editing !== null}
          title={editing ? `编辑 ${editing.name}` : "编辑主机"}
          initial={editInitial}
          lockName
          submitting={editMut.isPending}
          onClose={() => setEditing(null)}
          onSubmit={(form) =>
            editing && editMut.mutate({ name: editing.name, form })
          }
        />

        {/* Delete confirm */}
        <AlertDialog
          open={deleting !== null}
          onOpenChange={(o) => !o && setDeleting(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>删除主机</AlertDialogTitle>
              <AlertDialogDescription>
                {deleting
                  ? `确定删除 "${deleting.name}"？绑定到它的服务将无法继续工作。这里只会删除主机定义，不会改动远程机器。`
                  : null}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleteMut.isPending}>
                取消
              </AlertDialogCancel>
              <AlertDialogAction
                variant="destructive"
                disabled={deleteMut.isPending}
                onClick={(e) => {
                  e.preventDefault()
                  if (deleting) deleteMut.mutate(deleting.name)
                }}
              >
                {deleteMut.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : null}
                删除
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Browse repos */}
        <BrowseSheet host={browsing} onClose={() => setBrowsing(null)} />
      </div>
    </TooltipProvider>
  )
}
