import { LoaderCircle, LockKeyhole, Menu, RefreshCw, ShieldCheck, X } from "lucide-react"
import { useEffect } from "react"

import { NAVIGATION, type View } from "../lib/navigation"
import type { Theme } from "../lib/theme"
import { cn } from "../lib/utils"
import { Brand } from "./brand"
import { ThemeToggle } from "./theme-toggle"
import { Button } from "./ui/button"

export function Sidebar({
  activeView,
  onSelect,
  mobileOpen,
  onCloseMobile,
  onLock,
}: {
  activeView: View
  onSelect: (view: View) => void
  mobileOpen: boolean
  onCloseMobile: () => void
  onLock: () => void
}) {
  useEffect(() => {
    if (!mobileOpen) return
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseMobile()
    }
    window.addEventListener("keydown", close)
    return () => window.removeEventListener("keydown", close)
  }, [mobileOpen, onCloseMobile])

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-canvas/70 backdrop-blur-[2px] lg:hidden" onClick={onCloseMobile} aria-hidden="true" />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[17rem] flex-col border-r border-line bg-surface transition-transform duration-200 ease-out lg:w-64 lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Primary navigation"
      >
        <div className="flex h-16 items-center justify-between gap-2 border-b border-line px-4">
          <Brand />
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={onCloseMobile} aria-label="Close navigation">
            <X size={17} aria-hidden="true" />
          </Button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          <p className="px-3 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.09em] text-subtle">Console</p>
          {NAVIGATION.map(({ id, label, icon: Icon }) => {
            const active = activeView === id
            return (
              <a
                key={id}
                href={`#${id}`}
                onClick={() => onSelect(id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  active ? "bg-accent-soft text-accent-text" : "text-muted hover:bg-inset hover:text-ink",
                )}
              >
                <Icon size={17} aria-hidden="true" />
                {label}
              </a>
            )
          })}
        </nav>

        <div className="border-t border-line p-3">
          <div className="rounded-lg border border-line bg-inset p-3">
            <ShieldCheck size={16} className="text-success" aria-hidden="true" />
            <p className="mt-2 text-[13px] font-medium text-ink">Credentials stay in the gateway</p>
            <p className="mt-1 text-[12px] leading-5 text-subtle">This console keeps your key in memory for the session only.</p>
          </div>
          <Button variant="ghost" className="mt-2 w-full justify-start" onClick={onLock}>
            <LockKeyhole size={16} aria-hidden="true" />
            Lock console
          </Button>
        </div>
      </aside>
    </>
  )
}

export function TopBar({
  activeView,
  loading,
  updatedLabel,
  theme,
  onToggleTheme,
  onRefresh,
  onOpenMobile,
}: {
  activeView: View
  loading: boolean
  updatedLabel: string | null
  theme: Theme
  onToggleTheme: () => void
  onRefresh: () => void
  onOpenMobile: () => void
}) {
  const current = NAVIGATION.find((item) => item.id === activeView)
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-accent-fg"
      >
        Skip to main content
      </a>

      <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={onOpenMobile} aria-label="Open navigation">
          <Menu size={18} aria-hidden="true" />
        </Button>

        <div className="min-w-0 flex-1 lg:hidden">
          <Brand />
        </div>

        <nav className="hidden min-w-0 flex-1 items-center gap-2 text-[13px] lg:flex" aria-label="Breadcrumb">
          <span className="text-subtle">Console</span>
          <span className="text-subtle/60" aria-hidden="true">
            /
          </span>
          <span className="font-medium text-ink">{current?.label ?? "Overview"}</span>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {updatedLabel && (
            <span className="hidden text-[13px] text-subtle sm:inline tabular-nums" aria-live="polite">
              {updatedLabel}
            </span>
          )}
          <Button variant="secondary" size="sm" onClick={onRefresh} disabled={loading} className="gap-1.5">
            {loading ? (
              <LoaderCircle size={15} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={15} aria-hidden="true" />
            )}
            <span className="hidden sm:inline">{loading ? "Refreshing" : "Refresh"}</span>
          </Button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </div>
    </header>
  )
}
