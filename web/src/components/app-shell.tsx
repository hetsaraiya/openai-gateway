import {
  Boxes,
  ChevronDown,
  CircleGauge,
  Cloud,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Menu,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
  X,
} from "lucide-react"
import { useEffect, useState } from "react"

import type { Dashboard, Gateway, Login } from "../lib/api"
import { providerLabel } from "../lib/api"
import { NAVIGATION, type View } from "../lib/navigation"
import type { Theme } from "../lib/theme"
import { cn } from "../lib/utils"
import { AccountDialog } from "./account-dialog"
import { Brand } from "./brand"
import { DeleteAccountDialog } from "./delete-account-dialog"
import { ThemeToggle } from "./theme-toggle"
import { TestAccountButton } from "./test-account-button"
import { Button } from "./ui/button"

type SidebarProps = {
  data: Dashboard | null
  gatewayKey: string
  activeView: View
  selectedProvider: string | null
  onSelect: (view: View) => void
  onSelectProvider: (provider: string) => void
  onLoginStarted: (login: Login) => void
  onAccountAdded: (accountId: string) => void
  onTest: (accountId: string) => Promise<void>
  onDelete: (accountId: string) => Promise<void>
  mobileOpen: boolean
  onCloseMobile: () => void
  onLock: () => void
}

export function Sidebar({
  data,
  gatewayKey,
  activeView,
  selectedProvider,
  onSelect,
  onSelectProvider,
  onLoginStarted,
  onAccountAdded,
  onTest,
  onDelete,
  mobileOpen,
  onCloseMobile,
  onLock,
}: SidebarProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const providers = data?.providers ?? []
  const accounts = data?.gateways ?? []

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
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-40 bg-canvas/75 backdrop-blur-[3px] lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[20rem] flex-col border-r border-line bg-surface transition-transform duration-200 ease-out lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Gateway navigation"
      >
        <div className="flex h-[4.5rem] items-center justify-between gap-2 border-b border-line px-5">
          <Brand subtitle="Model control plane" />
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={onCloseMobile} aria-label="Close navigation">
            <X size={17} aria-hidden="true" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">
          <nav aria-label="Workspace" className="space-y-1">
            <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-subtle">Workspace</p>
            {NAVIGATION.map(({ id, label, icon: Icon }) => {
              const active = activeView === id
              return (
                <a
                  key={id}
                  href={`#${id}`}
                  onClick={() => onSelect(id)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex h-10 items-center gap-3 rounded-lg px-3 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                    active ? "bg-accent-soft text-accent-text" : "text-muted hover:bg-inset hover:text-ink",
                  )}
                >
                  <Icon size={16} aria-hidden="true" />
                  {label}
                  {id === "overview" && data ? (
                    <span className="ml-auto rounded-md bg-inset px-1.5 py-0.5 text-[10px] tabular-nums text-subtle">
                      {data.models.length}
                    </span>
                  ) : null}
                </a>
              )
            })}
          </nav>

          <div className="mt-7">
            <div className="flex items-center justify-between px-3 pb-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-subtle">Providers</p>
              <span className="text-[10px] tabular-nums text-subtle">{providers.length}</span>
            </div>

            <div className="space-y-1.5">
              {providers.map((provider) => {
                const providerAccounts = accounts.filter((account) => account.provider === provider.id)
                const isExpanded = expanded[provider.id] ?? true
                const isSelected = selectedProvider === provider.id && activeView === "overview"
                const canAddAccount =
                  provider.id === "codex" ||
                  provider.id === "opencode-go" ||
                  provider.id === "xai" ||
                  provider.id === "cursor"
                return (
                  <section
                    key={provider.id}
                    className={cn(
                      "overflow-hidden rounded-xl border transition-colors",
                      isSelected ? "border-accent/30 bg-accent-soft/60" : "border-transparent bg-transparent",
                    )}
                  >
                    <div className="flex items-center gap-1 p-1">
                      <button
                        type="button"
                        onClick={() => onSelectProvider(provider.id)}
                        className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-2 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        <ProviderIcon provider={provider.id} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-ink">{providerLabel(provider.id)}</span>
                          <span className="mt-0.5 block text-[10px] text-subtle">
                            {provider.active_accounts}/{provider.accounts} accounts active
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setExpanded((current) => ({ ...current, [provider.id]: !isExpanded }))}
                        className="grid size-8 shrink-0 place-items-center rounded-lg text-subtle transition-colors hover:bg-inset hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                        aria-label={`${isExpanded ? "Collapse" : "Expand"} ${providerLabel(provider.id)} accounts`}
                        aria-expanded={isExpanded}
                      >
                        <ChevronDown
                          size={15}
                          className={cn("transition-transform", isExpanded ? "rotate-0" : "-rotate-90")}
                          aria-hidden="true"
                        />
                      </button>
                    </div>

                    {isExpanded ? (
                      <div className="mx-2 mb-2 border-l border-line pl-2">
                        {providerAccounts.map((account) => (
                          <SidebarAccount key={account.id} account={account} onTest={onTest} onDelete={onDelete} />
                        ))}
                        {!providerAccounts.length ? (
                          <p className="px-2 py-2 text-[11px] text-subtle">No accounts connected</p>
                        ) : null}
                        {canAddAccount ? (
                          <AccountDialog
                            gatewayKey={gatewayKey}
                            disabled={!gatewayKey.trim()}
                            provider={provider.id}
                            onLoginStarted={onLoginStarted}
                            onAccountAdded={onAccountAdded}
                            trigger={
                              <Button variant="ghost" size="sm" className="mt-1 w-full justify-start px-2 text-[11px]">
                                <Plus size={13} aria-hidden="true" />
                                Add account
                              </Button>
                            }
                          />
                        ) : null}
                      </div>
                    ) : null}
                  </section>
                )
              })}

              {!providers.length ? (
                <div className="rounded-xl border border-dashed border-line px-3 py-5 text-center">
                  <Server size={16} className="mx-auto text-subtle" aria-hidden="true" />
                  <p className="mt-2 text-[12px] text-muted">Providers appear after the gateway loads.</p>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="border-t border-line p-3">
          <div className="flex items-start gap-2.5 rounded-lg bg-inset px-3 py-2.5">
            <ShieldCheck size={15} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
            <p className="text-[11px] leading-4 text-subtle">Credentials are stored only in your gateway.</p>
          </div>
          <Button variant="ghost" size="sm" className="mt-1 w-full justify-start" onClick={onLock}>
            <LockKeyhole size={15} aria-hidden="true" />
            Lock console
          </Button>
        </div>
      </aside>
    </>
  )
}

function ProviderIcon({ provider }: { provider: string }) {
  const Icon = provider === "codex" ? Cloud : provider === "opencode-go" ? CircleGauge : provider === "xai" ? Zap : Server
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-accent-text shadow-panel">
      <Icon size={15} aria-hidden="true" />
    </span>
  )
}

function SidebarAccount({
  account,
  onTest,
  onDelete,
}: {
  account: Gateway
  onTest: (accountId: string) => Promise<void>
  onDelete: (accountId: string) => Promise<void>
}) {
  return (
    <div className="group flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-inset">
      <span
        className={cn("size-1.5 shrink-0 rounded-full", account.active ? "bg-success" : "bg-warning")}
        title={account.active ? "Active" : "Cooling down"}
      />
      <KeyRound size={12} className="shrink-0 text-subtle" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-[11px] text-muted">{account.id}</span>
      <TestAccountButton accountId={account.id} onTest={onTest} />
      <DeleteAccountDialog account={account} onDelete={onDelete} />
    </div>
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
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/88 backdrop-blur-xl">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-accent-fg"
      >
        Skip to main content
      </a>

      <div className="flex h-[4.5rem] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={onOpenMobile} aria-label="Open navigation">
          <Menu size={18} aria-hidden="true" />
        </Button>

        <div className="min-w-0 flex-1 lg:hidden">
          <Brand subtitle={current?.label ?? "Console"} />
        </div>

        <div className="hidden min-w-0 flex-1 items-center gap-3 lg:flex">
          <span className="grid size-8 place-items-center rounded-lg border border-line bg-surface text-muted shadow-panel">
            {activeView === "overview" ? <Boxes size={15} aria-hidden="true" /> : <KeyRound size={15} aria-hidden="true" />}
          </span>
          <div>
            <p className="text-[13px] font-semibold text-ink">{current?.label ?? "Model catalog"}</p>
            <p className="text-[11px] text-subtle">OpenAI-compatible gateway</p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {updatedLabel ? (
            <span className="hidden text-[11px] text-subtle sm:inline tabular-nums" aria-live="polite">
              {updatedLabel}
            </span>
          ) : null}
          <Button variant="secondary" size="sm" onClick={onRefresh} disabled={loading} className="gap-1.5">
            {loading ? (
              <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            <span className="hidden sm:inline">{loading ? "Syncing" : "Sync"}</span>
          </Button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </div>
    </header>
  )
}
