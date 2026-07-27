import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react"
import type { ReactNode } from "react"

import { cn } from "../../lib/utils"

type Tone = "info" | "success" | "warning" | "danger"

const TONES: Record<Tone, { box: string; icon: typeof Info; iconColor: string }> = {
  info: { box: "border-line bg-inset", icon: Info, iconColor: "text-muted" },
  success: { box: "border-success/25 bg-success-soft", icon: CircleCheck, iconColor: "text-success" },
  warning: { box: "border-warning/25 bg-warning-soft", icon: TriangleAlert, iconColor: "text-warning" },
  danger: { box: "border-danger/25 bg-danger-soft", icon: CircleAlert, iconColor: "text-danger" },
}

export function Callout({
  tone = "info",
  title,
  className,
  children,
}: {
  tone?: Tone
  title?: string
  className?: string
  children?: ReactNode
}) {
  const { box, icon: Icon, iconColor } = TONES[tone]
  return (
    <div className={cn("flex gap-3 rounded-xl border px-4 py-3.5", box, className)} role={tone === "danger" ? "alert" : undefined}>
      <Icon size={17} className={cn("mt-0.5 shrink-0", iconColor)} aria-hidden="true" />
      <div className="min-w-0 text-sm leading-6">
        {title && <p className="font-medium text-ink">{title}</p>}
        {children && <div className={cn("text-muted", title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  )
}
