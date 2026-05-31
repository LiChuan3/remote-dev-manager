import { useState } from "react"
import { useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { ModeToggle } from "@/components/mode-toggle"
import { navItems } from "@/components/app-sidebar"

function pageTitle(pathname: string): string {
  // Exact match first, then longest matching prefix (ignoring the index route).
  const exact = navItems.find((i) => i.to === pathname)
  if (exact) return exact.label
  const prefix = navItems
    .filter((i) => i.to !== "/" && pathname.startsWith(i.to))
    .sort((a, b) => b.to.length - a.to.length)[0]
  return prefix?.label ?? "仪表盘"
}

export function SiteHeader() {
  const location = useLocation()
  const title = pageTitle(location.pathname)
  const [reloading, setReloading] = useState(false)

  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 5000,
    retry: false,
  })
  const online = health.isSuccess

  const onReload = async () => {
    setReloading(true)
    try {
      await api.reload()
      toast.success("配置已重新加载")
      void health.refetch()
    } catch (e) {
      toast.error("重新加载失败", {
        description: e instanceof Error ? e.message : undefined,
      })
    } finally {
      setReloading(false)
    }
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <h1 className="text-sm font-medium tracking-tight">{title}</h1>

      <div className="ml-auto flex items-center gap-2">
        <div
          className={cn(
            "hidden items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium sm:flex",
            online ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
          )}
        >
          <span className="relative flex size-2">
            {online && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
            )}
            <span
              className={cn(
                "relative inline-flex size-2 rounded-full",
                online ? "bg-emerald-500" : "bg-rose-500"
              )}
            />
          </span>
          <span className="text-muted-foreground">
            {online ? "后端在线" : "后端离线"}
          </span>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={onReload}
          disabled={reloading}
        >
          <RefreshCw className={cn(reloading && "animate-spin")} />
          重新加载配置
        </Button>

        <ModeToggle />
      </div>
    </header>
  )
}
