import { useState } from "react"
import { BookOpen, ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"

interface OperationGuideProps {
  title?: string
  steps: string[]
  notes?: string[]
  defaultOpen?: boolean
  compact?: boolean
  className?: string
}

export function OperationGuide({
  title = "使用说明",
  steps,
  notes = [],
  defaultOpen = true,
  compact = false,
  className,
}: OperationGuideProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "rounded-lg border bg-muted/30 text-sm",
        compact ? "px-3 py-2" : "px-4 py-3",
        className,
      )}
    >
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="-mx-2 flex h-8 w-[calc(100%+1rem)] justify-start gap-2 px-2"
        >
          <BookOpen className="size-4 text-primary" />
          <span className="font-medium">{title}</span>
          <ChevronDown
            className={cn(
              "ml-auto size-4 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-2">
        <ol className="list-decimal space-y-1.5 pl-5 text-muted-foreground">
          {steps.map((step) => (
            <li key={step} className="pl-1 leading-relaxed">
              {step}
            </li>
          ))}
        </ol>
        {notes.length > 0 ? (
          <div className="mt-2 space-y-1.5 border-t pt-2 text-xs text-muted-foreground">
            {notes.map((note) => (
              <p key={note} className="leading-relaxed">
                {note}
              </p>
            ))}
          </div>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  )
}
