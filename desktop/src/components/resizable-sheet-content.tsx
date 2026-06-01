import * as React from "react"
import { GripVertical, PanelRightClose, PanelRightOpen, X } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { SheetClose, SheetContent } from "@/components/ui/sheet"

interface ResizableSheetContentProps
  extends Omit<React.ComponentProps<typeof SheetContent>, "side"> {
  title: string
  defaultWidth?: number
  minWidth?: number
  maxWidth?: number
  collapsedWidth?: number
  storageKey?: string
}

export function ResizableSheetContent({
  title,
  children,
  className,
  style,
  defaultWidth = 720,
  minWidth = 360,
  maxWidth = 960,
  collapsedWidth = 72,
  storageKey,
  ...props
}: ResizableSheetContentProps) {
  const [minimized, setMinimized] = React.useState(false)
  const [dragging, setDragging] = React.useState(false)
  const [width, setWidth] = React.useState(() => {
    if (!storageKey) return defaultWidth
    const saved = window.localStorage.getItem(storageKey)
    const parsed = saved ? Number(saved) : Number.NaN
    return Number.isFinite(parsed) ? parsed : defaultWidth
  })

  const clampWidth = React.useCallback(
    (next: number) => {
      const viewportMax =
        typeof window === "undefined" ? maxWidth : window.innerWidth - 16
      const hardMax = Math.max(minWidth, Math.min(maxWidth, viewportMax))
      return Math.min(Math.max(next, minWidth), hardMax)
    },
    [maxWidth, minWidth],
  )

  React.useEffect(() => {
    setWidth((current) => clampWidth(current))
  }, [clampWidth])

  React.useEffect(() => {
    if (!storageKey || minimized) return
    window.localStorage.setItem(storageKey, String(Math.round(width)))
  }, [minimized, storageKey, width])

  React.useEffect(() => {
    if (!dragging) return

    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = "ew-resize"
    document.body.style.userSelect = "none"

    const onPointerMove = (event: PointerEvent) => {
      setMinimized(false)
      setWidth(clampWidth(window.innerWidth - event.clientX))
    }
    const stopDragging = () => setDragging(false)

    window.addEventListener("pointermove", onPointerMove)
    window.addEventListener("pointerup", stopDragging, { once: true })
    window.addEventListener("pointercancel", stopDragging, { once: true })
    return () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
      window.removeEventListener("pointermove", onPointerMove)
      window.removeEventListener("pointerup", stopDragging)
      window.removeEventListener("pointercancel", stopDragging)
    }
  }, [clampWidth, dragging])

  const effectiveWidth = minimized ? collapsedWidth : clampWidth(width)

  return (
    <SheetContent
      side="right"
      showCloseButton={false}
      className={cn(
        "w-[var(--sheet-width)] max-w-[calc(100vw-1rem)] gap-0 overflow-hidden p-0 sm:max-w-none",
        className,
      )}
      style={
        {
          ...style,
          "--sheet-width": `${effectiveWidth}px`,
        } as React.CSSProperties
      }
      {...props}
    >
      {minimized ? (
        <div className="flex h-full flex-col items-center gap-3 border-l bg-muted/40 px-2 py-3">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="展开面板"
            onClick={() => setMinimized(false)}
          >
            <PanelRightOpen />
          </Button>
          <SheetClose asChild>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="关闭面板">
              <X />
            </Button>
          </SheetClose>
          <div className="mt-2 max-h-[calc(100vh-8rem)] text-muted-foreground [writing-mode:vertical-rl]">
            <span className="line-clamp-1 text-xs">{title}</span>
          </div>
          <div className="mt-auto flex flex-col items-center gap-1 text-[11px] text-muted-foreground">
            <GripVertical className="size-4" />
            <span className="[writing-mode:vertical-rl]">已最小化</span>
          </div>
        </div>
      ) : (
        <>
          <button
            type="button"
            aria-label="拖动调整面板宽度"
            title="按住拖动调整面板宽度"
            className="absolute inset-y-0 left-0 z-20 flex w-7 cursor-ew-resize items-center justify-center border-r bg-muted/60 text-muted-foreground shadow-sm hover:bg-primary/10 hover:text-primary focus-visible:bg-primary/10 focus-visible:text-primary focus-visible:outline-none"
            onPointerDown={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
          >
            <div className="flex flex-col items-center gap-1">
              <GripVertical className="size-4" />
              <span className="text-[10px] leading-none [writing-mode:vertical-rl]">
                拖动
              </span>
            </div>
          </button>
          <div className="absolute right-3 top-3 z-30 flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="最小化面板"
              onClick={() => setMinimized(true)}
            >
              <PanelRightClose />
            </Button>
            <SheetClose asChild>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="关闭面板">
                <X />
              </Button>
            </SheetClose>
          </div>
          <div className="flex h-full min-w-0 flex-col pl-7">{children}</div>
        </>
      )}
    </SheetContent>
  )
}
