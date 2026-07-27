import { KeyRound } from "lucide-react"

import { AccountDialog } from "../components/account-dialog"
import { DeviceLogin } from "../components/device-login"
import { Badge } from "../components/ui/badge"
import { Panel, PanelEmpty, PanelHeader, PageHeader } from "../components/ui/panel"
import { SkeletonRows } from "../components/ui/skeleton"
import type { Dashboard, Gateway, Login } from "../lib/api"
import { compactNumber, fullNumber } from "../lib/utils"

export function Accounts({
  data,
  loading,
  gatewayKey,
  login,
  onLoginStarted,
  onCopy,
}: {
  data: Dashboard | null
  loading: boolean
  gatewayKey: string
  login: Login | null
  onLoginStarted: (login: Login) => void
  onCopy: (value: string) => void
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
        description="Connect ChatGPT accounts through the OpenAI device flow. Refreshed credentials are stored by the gateway, never by this page."
        actions={<AccountDialog gatewayKey={gatewayKey} disabled={!gatewayKey.trim()} onLoginStarted={onLoginStarted} />}
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
              <AccountRow key={account.id} account={account} busiest={busiest} />
            ))}
          </ul>
        ) : (
          <PanelEmpty
            icon={<KeyRound size={18} aria-hidden="true" />}
            title="No accounts connected yet"
            hint="Use “Connect account” above to start a secure OpenAI device sign-in."
          />
        )}
      </Panel>
    </div>
  )
}

function AccountRow({ account, busiest }: { account: Gateway; busiest: number }) {
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
      </div>
    </li>
  )
}
