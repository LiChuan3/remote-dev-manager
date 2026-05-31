import { useState } from "react"
import { Check, Copy } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/** Copies `value` to the clipboard with transient "Copied" feedback. */
export function CopyButton({
  value,
  label,
  size = "sm",
  variant = "ghost",
  className,
}: {
  value: string
  label?: string
  size?: React.ComponentProps<typeof Button>["size"]
  variant?: React.ComponentProps<typeof Button>["variant"]
  className?: string
}) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error("无法复制到剪贴板")
    }
  }

  return (
    <Button
      type="button"
      size={size}
      variant={variant}
      onClick={copy}
      className={cn(className)}
    >
      {copied ? (
        <Check className="text-emerald-500" />
      ) : (
        <Copy />
      )}
      {label ?? (copied ? "已复制" : "复制")}
    </Button>
  )
}
