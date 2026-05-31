import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Section header used at the top of every page's content area.
 * Pairs with the global SiteHeader (which carries breadcrumb + global actions).
 */
export function PageHeader({
  title,
  description,
  icon,
  badge,
  actions,
  className,
}: {
  title: ReactNode
  description?: ReactNode
  icon?: ReactNode
  badge?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        {icon ? (
          <div className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-lg [&_svg]:size-4.5">
            {icon}
          </div>
        ) : null}
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-xl font-semibold tracking-tight">
              {title}
            </h1>
            {badge}
          </div>
          {description ? (
            <p className="text-muted-foreground text-sm">{description}</p>
          ) : null}
        </div>
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  )
}
