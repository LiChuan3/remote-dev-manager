import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { TerminalSquare } from "lucide-react"

import { api } from "@/lib/api"
import { getSidecarPort } from "@/lib/tauri"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { useTheme } from "@/components/theme-provider"

async function safe(fn: () => Promise<string>): Promise<string> {
  try {
    return await fn()
  } catch {
    return "n/a"
  }
}

interface AppMeta {
  name: string
  version: string
  tauri: string
  port: number
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  )
}

// Vite injects `import.meta.env.DEV`; type it loosely since the project has no
// `vite/client` ambient types referenced.
const isDev = (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV ?? false

export function DebugPanel() {
  if (!isDev) return null
  return <DebugPanelInner />
}

function DebugPanelInner() {
  const { theme } = useTheme()
  const [meta, setMeta] = useState<AppMeta | null>(null)

  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 5000,
    retry: false,
  })

  useEffect(() => {
    let active = true
    void (async () => {
      const [appMod, port] = await Promise.all([
        import("@tauri-apps/api/app").catch(() => null),
        getSidecarPort(),
      ])
      const name = appMod ? await safe(appMod.getName) : "n/a"
      const version = appMod ? await safe(appMod.getVersion) : "n/a"
      const tauri = appMod ? await safe(appMod.getTauriVersion) : "n/a"
      if (active) setMeta({ name, version, tauri, port })
    })()
    return () => {
      active = false
    }
  }, [])

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon-sm"
          className="fixed right-4 bottom-4 z-50 shadow-md"
          aria-label="调试面板"
        >
          <TerminalSquare className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" side="top" className="w-72 gap-2 text-xs">
        <p className="text-sm font-medium">诊断信息</p>
        <div className="flex flex-col gap-1.5">
          <Row label="应用" value={meta?.name ?? "…"} />
          <Row label="版本" value={meta?.version ?? "…"} />
          <Row label="Tauri" value={meta?.tauri ?? "…"} />
          <Row label="后端端口" value={meta?.port ?? "…"} />
          <Row
            label="后端"
            value={
              health.isSuccess
                ? "在线"
                : health.isLoading
                  ? "检查中"
                  : "离线"
            }
          />
          <Row label="主题" value={theme ?? "跟随系统"} />
        </div>
      </PopoverContent>
    </Popover>
  )
}
