import type { ReactNode } from "react"

import { cn } from "../../lib/utils"

/** The single card surface used across the console: hairline border, no heavy shadow. */
export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("overflow-hidden rounded-xl border border-line bg-surface shadow-panel", className)}>{children}</section>
}

export function PanelHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        {description && <p className="mt-0.5 truncate text-[13px] text-subtle">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function PanelEmpty({ icon, title, hint }: { icon: ReactNode; title: string; hint?: string }) {
  return (
    <div className="px-5 py-12 text-center">
      <span className="mx-auto grid size-10 place-items-center rounded-lg border border-line bg-inset text-subtle">{icon}</span>
      <p className="mt-3 text-sm font-medium text-ink">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-sm text-[13px] leading-5 text-subtle">{hint}</p>}
    </div>
  )
}

/** Section heading used at the top of each view. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.09em] text-accent-text">{eyebrow}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.02em] text-balance text-ink">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
