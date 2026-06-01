import { useMemo, useState } from "react"
import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  Zap,
  Server,
  CheckCircle2,
  XCircle,
  Power,
  Activity,
  ArrowRight,
  Terminal,
  ShieldCheck,
  Globe,
  Loader2,
} from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { AiProxyResult, Host } from "@/lib/types"
import { PageHeader } from "@/components/page-header"
import { StatusBadge, StatusDot } from "@/components/status-badge"
import { EmptyState } from "@/components/empty-state"
import { CopyButton } from "@/components/copy-button"
import { OperationGuide } from "@/components/operation-guide"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"

/** Loosely-typed status payload from GET /api/ai-proxy/status. */
interface AiProxyStatusData {
  ok?: boolean
  tunnel?: string
  tunnel_running?: boolean
  reachability?: Record<string, string | number>
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Flow diagram
// ---------------------------------------------------------------------------

function FlowNode({
  icon,
  title,
  sub,
}: {
  icon: ReactNode
  title: string
  sub: string
}) {
  return (
    <div className="bg-muted/40 flex min-w-0 flex-1 flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-center">
      <div className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-lg [&_svg]:size-4">
        {icon}
      </div>
      <p className="text-sm font-medium">{title}</p>
      <p className="text-muted-foreground text-xs leading-tight">{sub}</p>
    </div>
  )
}

function FlowArrow() {
  return <ArrowRight className="text-muted-foreground/60 size-4 shrink-0" />
}

// ---------------------------------------------------------------------------
// Labelled switch row
// ---------------------------------------------------------------------------

function SwitchRow({
  id,
  checked,
  onChange,
  label,
  hint,
}: {
  id: string
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint: string
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 space-y-0.5">
        <Label htmlFor={id} className="cursor-pointer font-normal">
          {label}
        </Label>
        <p className="text-muted-foreground text-xs">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Copyable mono code block
// ---------------------------------------------------------------------------

function CodeBlock({
  label,
  command,
  note,
}: {
  label: string
  command: string
  note?: string
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {label}
        </p>
        <CopyButton value={command} size="xs" />
      </div>
      <pre className="bg-muted/60 overflow-x-auto rounded-lg border px-3 py-2.5 font-mono text-xs leading-relaxed">
        <code>{command}</code>
      </pre>
      {note ? <p className="text-muted-foreground text-xs">{note}</p> : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Setup step checklist
// ---------------------------------------------------------------------------

function StepList({ result }: { result: AiProxyResult }) {
  const steps = result.setup?.steps ?? []
  if (steps.length === 0) return null
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        配置步骤
      </p>
      <ul className="space-y-1.5">
        {steps.map((s, i) => (
          <li
            key={`${s.name}-${i}`}
            className="bg-muted/30 flex items-start gap-2.5 rounded-lg border px-3 py-2"
          >
            {s.ok ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-rose-600 dark:text-rose-400" />
            )}
            <div className="min-w-0">
              <p className="text-sm">{s.name}</p>
              {s.detail ? (
                <p className="text-muted-foreground text-xs break-words">
                  {s.detail}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Reachability badges
// ---------------------------------------------------------------------------

const PROVIDERS = [
  { key: "anthropic", label: "Anthropic" },
  { key: "openai", label: "OpenAI" },
  { key: "google", label: "Google" },
] as const

function reachabilityOk(code: string | number | undefined): boolean {
  if (code === undefined) return false
  const s = String(code).trim()
  return s !== "000" && s !== "0" && s !== ""
}

function StatusReport({ data }: { data: AiProxyStatusData }) {
  const reach = data.reachability ?? {}
  const running = data.tunnel_running ?? data.ok ?? false
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          隧道
        </span>
        <StatusBadge status={running ? "RUNNING" : "STOPPED"} />
      </div>
      <div className="flex flex-wrap gap-2">
        {PROVIDERS.map((p) => {
          const code = reach[p.key]
          const ok = reachabilityOk(code)
          return (
            <span
              key={p.key}
              className={cn(
                "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
                ok
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400",
              )}
            >
              {ok ? (
                <CheckCircle2 className="size-3" />
              ) : (
                <XCircle className="size-3" />
              )}
              {p.label}
              {code !== undefined ? (
                <span className="font-mono opacity-70">{String(code)}</span>
              ) : null}
            </span>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Result view
// ---------------------------------------------------------------------------

function ResultView({
  result,
  envExports,
}: {
  result: AiProxyResult
  envExports: string
}) {
  const proxyUrl = result.setup?.proxy_url
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
            result.ok
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              : "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400",
          )}
        >
          {result.ok ? (
            <CheckCircle2 className="size-3" />
          ) : (
            <XCircle className="size-3" />
          )}
          {result.ok ? "已启用" : "发现问题"}
        </span>
        <StatusBadge status={result.tunnel?.status ?? "STOPPED"} />
        {proxyUrl ? (
          <span className="text-primary font-mono text-xs">{proxyUrl}</span>
        ) : null}
      </div>

      <StepList result={result} />

      {result.launch?.claude?.command ? (
        <CodeBlock
          label="在远程主机启动 Claude Code"
          command={result.launch.claude.command}
          note={result.launch.claude.note}
        />
      ) : null}
      {result.launch?.codex?.command ? (
        <CodeBlock
          label="在远程主机启动 Codex"
          command={result.launch.codex.command}
          note={result.launch.codex.note}
        />
      ) : null}
      {envExports ? (
        <CodeBlock
          label="手动环境变量（远程 Shell）"
          command={envExports}
          note="需要手动配置时，在远程主机启动工具前执行这些命令。"
        />
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AiProxyPage() {
  const configQuery = useQuery({
    queryKey: ["config"],
    queryFn: () => api.getConfig(),
    staleTime: 10000,
  })
  const hosts = useMemo<Host[]>(
    () => configQuery.data?.hosts ?? [],
    [configQuery.data],
  )
  const defaultClashPort = configQuery.data?.defaults?.clash_port ?? 7897

  const [host, setHost] = useState("")
  const [localPort, setLocalPort] = useState<number>(defaultClashPort)
  const [remotePort, setRemotePort] = useState<number>(7897)
  const [persistent, setPersistent] = useState(false)
  const [verify, setVerify] = useState(true)
  const [ensureTunnel, setEnsureTunnel] = useState(true)

  const [statusData, setStatusData] = useState<AiProxyStatusData | null>(null)

  // Default the selected host / clash port once config loads.
  const [seeded, setSeeded] = useState(false)
  if (!seeded && hosts.length > 0) {
    setSeeded(true)
    setHost(hosts[0].name)
    setLocalPort(defaultClashPort)
  }

  const setup = useMutation({
    mutationFn: () =>
      api.aiProxySetup({
        host,
        local_port: localPort,
        remote_port: remotePort,
        persistent,
        verify,
        ensure_tunnel: ensureTunnel,
      }),
    onSuccess: (res) => {
      if (res.ok) toast.success(`${host} 上的 AI 代理已启用`)
      else
        toast.warning("配置完成，但存在问题", {
          description: "请查看下方步骤检查结果。",
        })
    },
    onError: (e: unknown) =>
      toast.error("配置失败", {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  const status = useMutation({
    mutationFn: () => api.aiProxyStatus(host),
    onSuccess: (res) => setStatusData((res ?? {}) as AiProxyStatusData),
    onError: (e: unknown) =>
      toast.error("状态检查失败", {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  const teardown = useMutation({
    mutationFn: () => api.aiProxyTeardown(host),
    onSuccess: () => {
      toast.success(`${host} 上的 AI 代理已禁用`)
      setStatusData(null)
    },
    onError: (e: unknown) =>
      toast.error("禁用失败", {
        description: e instanceof Error ? e.message : undefined,
      }),
  })

  const result = setup.data
  const proxyUrl = result?.setup?.proxy_url
  const envExports = proxyUrl
    ? `export ALL_PROXY=${proxyUrl}\nexport HTTPS_PROXY=${proxyUrl}\nexport HTTP_PROXY=${proxyUrl}`
    : ""

  const header = (
    <PageHeader
      title="AI 代理"
      icon={<Zap />}
      badge={<Badge variant="secondary">主打功能</Badge>}
      description="一键通过反向 SSH 隧道，把远程 Claude Code / Codex 的 API 流量转到本机 Clash。"
    />
  )

  const noHosts = !configQuery.isLoading && hosts.length === 0
  if (noHosts) {
    return (
      <div className="space-y-6">
        {header}
        <Card>
          <CardContent>
            <EmptyState
              icon={<Server />}
              title="还没有配置主机"
              description="请先添加远程主机，再把它的 Claude Code / Codex 流量转到本机 Clash。"
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
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {header}

      <OperationGuide
        title="AI 代理怎么用"
        steps={[
          "先确认本机 Clash 正在运行，并记下本机代理端口，默认常见为 7897。",
          "选择远程主机后点击启用 AI 代理，应用会建立反向 SSH 隧道。",
          "启用成功后，在结果区复制远程 Claude Code 或 Codex 启动命令。",
          "如果远程主机不再需要代理，点击禁用会停止相关反向隧道。",
        ]}
        notes={["写入远程环境会修改远程 ~/.bashrc；不确定时先保持关闭，只使用结果区给出的临时命令。"]}
      />

      {/* Explainer / flow */}
      <Card>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground text-sm">
            点击 <span className="text-foreground font-medium">启用</span> 后，
            应用会从远程主机建立一条回连到本机的反向 SSH 隧道，并把远程
            Claude Code / Codex 指向这条隧道，让 API 流量通过{" "}
            <span className="text-foreground font-medium">本机 Clash</span>
            出口访问网络，无需在服务器上安装代理。
          </p>
          <div className="flex items-center gap-2">
            <FlowNode
              icon={<Server />}
              title="远程主机"
              sub="Claude / Codex"
            />
            <FlowArrow />
            <FlowNode
              icon={<Zap />}
              title="反向 SSH"
              sub={`隧道 :${remotePort}`}
            />
            <FlowArrow />
            <FlowNode
              icon={<ShieldCheck />}
              title="本机 Clash"
              sub={`:${localPort}`}
            />
            <FlowArrow />
            <FlowNode
              icon={<Globe />}
              title="互联网"
              sub="Anthropic / OpenAI"
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Setup form */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="text-primary size-4" /> 配置
            </CardTitle>
            <CardDescription>
              选择主机和端口后启用代理。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="ai-proxy-host">主机</Label>
              <Select value={host} onValueChange={setHost}>
                <SelectTrigger id="ai-proxy-host" className="w-full">
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
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="ai-proxy-local-port">本机 Clash 端口</Label>
                <Input
                  id="ai-proxy-local-port"
                  type="number"
                  value={localPort}
                  onChange={(e) => setLocalPort(Number(e.target.value) || 0)}
                />
                <p className="text-muted-foreground text-xs">当前机器</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ai-proxy-remote-port">远程端口</Label>
                <Input
                  id="ai-proxy-remote-port"
                  type="number"
                  value={remotePort}
                  onChange={(e) => setRemotePort(Number(e.target.value) || 0)}
                />
                <p className="text-muted-foreground text-xs">
                  在远程主机上监听
                </p>
              </div>
            </div>

            <div className="bg-muted/30 space-y-3.5 rounded-lg border p-3.5">
              <SwitchRow
                id="ai-proxy-ensure-tunnel"
                checked={ensureTunnel}
                onChange={setEnsureTunnel}
                label="自动创建并启动反向隧道"
                hint="如果 SSH 反向隧道尚未运行，则自动创建。"
              />
              <SwitchRow
                id="ai-proxy-verify"
                checked={verify}
                onChange={setVerify}
                label="验证连通性"
                hint="配置后通过代理探测 Anthropic / OpenAI / Google。"
              />
              <SwitchRow
                id="ai-proxy-persistent"
                checked={persistent}
                onChange={setPersistent}
                label="写入远程环境（~/.bashrc）"
                hint="写入代理环境变量，让新的 Shell 继续使用。"
              />
            </div>

            <Button
              className="w-full"
              onClick={() => setup.mutate()}
              disabled={!host || setup.isPending}
            >
              {setup.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Zap />
              )}
              {setup.isPending ? "配置中…" : "启用 AI 代理"}
            </Button>

            {setup.isPending ? <Progress className="h-1" /> : null}

            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => status.mutate()}
                disabled={!host || status.isPending}
              >
                {status.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Activity />
                )}
                检查状态
              </Button>
              <Button
                variant="destructive"
                className="flex-1"
                onClick={() => teardown.mutate()}
                disabled={!host || teardown.isPending}
              >
                {teardown.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Power />
                )}
                禁用
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Result / status */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Terminal className="text-primary size-4" /> 结果
            </CardTitle>
            <CardDescription>
              查看配置步骤、启动命令和连通性。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {setup.isPending ? (
              <div className="text-muted-foreground flex flex-col items-center justify-center gap-3 py-10 text-sm">
                <Loader2 className="size-6 animate-spin" />
                正在建立反向隧道并配置远程主机…
              </div>
            ) : result ? (
              <ResultView result={result} envExports={envExports} />
            ) : statusData ? (
              <StatusReport data={statusData} />
            ) : (
              <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-center text-sm">
                <StatusDot status="STOPPED" />
                <p>
                  点击 <span className="text-foreground">启用 AI 代理</span>{" "}
                  或 <span className="text-foreground">检查状态</span> 后，
                  这里会显示结果。
                </p>
              </div>
            )}

            {/* Latest status (shown alongside a setup result) */}
            {result && statusData ? (
              <div className="space-y-3 pt-1">
                <Separator />
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                  最近一次状态检查
                </p>
                <StatusReport data={statusData} />
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
