import { cn } from "@/lib/utils"
import type { ServiceStatus } from "@/lib/types"

const STYLES: Record<
  string,
  { label: string; dot: string; text: string; ring: string }
> = {
  RUNNING: {
    label: "运行中",
    dot: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "border-emerald-500/30 bg-emerald-500/10",
  },
  STARTING: {
    label: "启动中",
    dot: "bg-amber-500 animate-pulse",
    text: "text-amber-600 dark:text-amber-400",
    ring: "border-amber-500/30 bg-amber-500/10",
  },
  FAILED: {
    label: "失败",
    dot: "bg-rose-500",
    text: "text-rose-600 dark:text-rose-400",
    ring: "border-rose-500/30 bg-rose-500/10",
  },
  STOPPED: {
    label: "已停止",
    dot: "bg-muted-foreground/60",
    text: "text-muted-foreground",
    ring: "border-border bg-muted/40",
  },
}

/** Colored pill (dot + label) for a service status. */
export function StatusBadge({
  status,
  className,
  showLabel = true,
}: {
  status: ServiceStatus | string
  className?: string
  showLabel?: boolean
}) {
  const s = STYLES[status] ?? STYLES.STOPPED
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit items-center gap-1.5 rounded-full border px-2 text-xs font-medium",
        s.ring,
        s.text,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {showLabel ? s.label : null}
    </span>
  )
}

/** Bare colored dot, for compact rows. */
export function StatusDot({
  status,
  className,
}: {
  status: ServiceStatus | string
  className?: string
}) {
  const s = STYLES[status] ?? STYLES.STOPPED
  return <span className={cn("inline-block size-2 rounded-full", s.dot, className)} />
}
