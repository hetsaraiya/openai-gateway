import { Cloud, KeyRound, Plus, Zap } from "lucide-react"

import { AccountDialog } from "../components/account-dialog"
import { DeleteAccountDialog } from "../components/delete-account-dialog"
import { DeviceLogin } from "../components/device-login"
import { Badge } from "../components/ui/badge"
import { Panel, PanelEmpty, PanelHeader, PageHeader } from "../components/ui/panel"
import { SkeletonRows } from "../components/ui/skeleton"
import { TestAccountButton } from "../components/test-account-button"
import type { Dashboard, Gateway, Login } from "../lib/api"
import { compactNumber, fullNumber } from "../lib/utils"

export function Accounts({
  data,
  loading,
  gatewayKey,
  login,
  onLoginStarted,
  onAccountAdded,
  onCopy,
  onTest,
  onDelete,
}: {
  data: Dashboard | null
  loading: boolean
  gatewayKey: string
  login: Login | null
  onLoginStarted: (login: Login) => void
  onAccountAdded: (accountId: string) => void
  onCopy: (value: string) => void
  onTest: (accountId: string) => Promise<void>
  onDelete: (accountId: string) => Promise<void>
}) {
  const accounts = data?.gateways ?? []
  const activeCount = accounts.filter((account) => account.active).length
  // Usage bars are relative to the busiest account — absolute quotas aren't reported.
  const busiest = accounts.reduce((peak, account) => Math.max(peak, account.used_today ?? 0), 0)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Identity & access"
        title="Accounts"
        description="Manage OpenAI device sessions and provider API keys in one place. Credentials are stored by the gateway, never by this page."
        actions={
          <div className="flex flex-wrap gap-2">
            <AccountDialog
              gatewayKey={gatewayKey}
              disabled={!gatewayKey.trim()}
              provider="codex"
              trigger={
                <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-accent-fg shadow-panel transition-colors hover:bg-accent-hover">
                  <Plus size={16} aria-hidden="true" />
                  OpenAI account
                </button>
              }
              onLoginStarted={onLoginStarted}
              onAccountAdded={onAccountAdded}
            />
            <AccountDialog
              gatewayKey={gatewayKey}
              disabled={!gatewayKey.trim()}
              provider="xai"
              trigger={
                <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-medium text-ink shadow-panel transition-colors hover:border-line-strong hover:bg-elevated">
                  <Zap size={16} aria-hidden="true" />
                  xAI API key
                </button>
              }
              onLoginStarted={onLoginStarted}
              onAccountAdded={onAccountAdded}
            />
            <AccountDialog
              gatewayKey={gatewayKey}
              disabled={!gatewayKey.trim()}
              provider="opencode-go"
              trigger={
                <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-medium text-ink shadow-panel transition-colors hover:border-line-strong hover:bg-elevated">
                  <Cloud size={16} aria-hidden="true" />
                  OpenCode Go key
                </button>
              }
              onLoginStarted={onLoginStarted}
              onAccountAdded={onAccountAdded}
            />
          </div>
        }
      />

      {login && <DeviceLogin login={login} onCopy={onCopy} />}

      <Panel>
        <PanelHeader
          title="Connected accounts"
          description="Traffic is routed across active accounts using the configured strategy"
          actions={
            accounts.length > 0 && (
              <Badge tone={activeCount ? "success" : "warning"} dot>
                {activeCount} of {accounts.length} active
              </Badge>
            )
          }
        />

        {!data && loading ? (
          <SkeletonRows rows={3} />
        ) : accounts.length ? (
          <ul className="divide-y divide-line">
            {accounts.map((account) => (
              <AccountRow key={account.id} account={account} busiest={busiest} onTest={onTest} onDelete={onDelete} />
            ))}
          </ul>
        ) : (
          <PanelEmpty
            icon={<KeyRound size={18} aria-hidden="true" />}
            title="No accounts connected yet"
            hint="Add an OpenAI account, OpenCode Go key, or xAI API key to start routing requests."
          />
        )}
      </Panel>
    </div>
  )
}

function AccountRow({
  account,
  busiest,
  onTest,
  onDelete,
}: {
  account: Gateway
  busiest: number
  onTest: (accountId: string) => Promise<void>
  onDelete: (accountId: string) => Promise<void>
}) {
  const used = account.used_today ?? 0
  const share = busiest > 0 ? Math.max(used / busiest, used > 0 ? 0.06 : 0) : 0

  return (
    <li className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-line bg-inset text-subtle">
          <KeyRound size={16} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{account.id}</p>
          <p className="mt-0.5 truncate text-[13px] text-subtle">
            {account.provider}
            {account.plan ? ` · ${account.plan}` : ""}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-5 sm:justify-end">
        <div className="w-28 shrink-0">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-semibold text-ink tabular-nums" title={`${fullNumber(used)} requests today`}>
              {compactNumber(used)}
            </span>
            <span className="text-[12px] text-subtle">today</span>
          </div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-inset" aria-hidden="true">
            <div
              className={account.active ? "h-full rounded-full bg-accent" : "h-full rounded-full bg-warning"}
              style={{ width: `${Math.round(share * 100)}%` }}
            />
          </div>
        </div>
        <Badge tone={account.active ? "success" : "warning"} dot>
          {account.active ? "Active" : "Cooling down"}
        </Badge>
        <TestAccountButton accountId={account.id} onTest={onTest} />
        <DeleteAccountDialog account={account} onDelete={onDelete} />
      </div>
    </li>
  )
}
