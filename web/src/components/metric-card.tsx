import type { LucideIcon } from "lucide-react"

import { cn } from "../lib/utils"
import { Skeleton } from "./ui/skeleton"

export function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  loading = false,
  emphasis = "default",
}: {
  icon: LucideIcon
  label: string
  value: string | number
  detail: string
  loading?: boolean
  emphasis?: "default" | "accent"
}) {
  return (
    <article className="rounded-xl border border-line bg-surface p-5 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-muted">{label}</p>
        <span
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-lg border",
            emphasis === "accent" ? "border-accent/20 bg-accent-soft text-accent-text" : "border-line bg-inset text-subtle",
          )}
        >
          <Icon size={16} aria-hidden="true" />
        </span>
      </div>
      {loading ? (
        <Skeleton className="mt-4 h-8 w-20" />
      ) : (
        <p className="mt-4 truncate text-[28px] font-semibold leading-none tracking-[-0.02em] text-ink tabular-nums">{value}</p>
      )}
      <p className="mt-2 truncate text-[13px] text-subtle">{detail}</p>
    </article>
  )
}
