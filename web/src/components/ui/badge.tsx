import type { ReactNode } from "react"

import { cn } from "../../lib/utils"

type Tone = "neutral" | "success" | "warning" | "danger" | "accent"

const TONES: Record<Tone, { chip: string; dot: string }> = {
  neutral: { chip: "border-line bg-inset text-muted", dot: "bg-subtle" },
  success: { chip: "border-success/25 bg-success-soft text-success", dot: "bg-success" },
  warning: { chip: "border-warning/25 bg-warning-soft text-warning", dot: "bg-warning" },
  danger: { chip: "border-danger/25 bg-danger-soft text-danger", dot: "bg-danger" },
  accent: { chip: "border-accent/25 bg-accent-soft text-accent-text", dot: "bg-accent-text" },
}

export function Badge({
  tone = "neutral",
  dot = false,
  pulse = false,
  className,
  children,
}: {
  tone?: Tone
  dot?: boolean
  pulse?: boolean
  className?: string
  children: ReactNode
}) {
  const styles = TONES[tone]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium whitespace-nowrap",
        styles.chip,
        className,
      )}
    >
      {dot && (
        <span className="relative flex size-1.5" aria-hidden="true">
          {pulse && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", styles.dot)} />}
          <span className={cn("relative inline-flex size-1.5 rounded-full", styles.dot)} />
        </span>
      )}
      {children}
    </span>
  )
}
