import { Activity, Boxes, Database, KeyRound, Route, Search, Sparkles } from "lucide-react"
import { useMemo, useState } from "react"

import { MetricCard } from "../components/metric-card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Callout } from "../components/ui/callout"
import { Panel, PanelEmpty, PanelHeader, PageHeader } from "../components/ui/panel"
import { SkeletonRows } from "../components/ui/skeleton"
import { contextWindow, providerFor, type Dashboard, type Model, type Provider } from "../lib/api"
import { compactNumber } from "../lib/utils"

export function Overview({
  data,
  loading,
  onAddAccount,
}: {
  data: Dashboard | null
  loading: boolean
  onAddAccount: () => void
}) {
  const accounts = data?.gateways ?? []
  const activeAccounts = accounts.filter((account) => account.active).length
  const firstLoad = !data && loading

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Gateway health"
        title="Overview"
        description="Live account availability, the model catalog, and the routing strategy currently in force."
        actions={
          data ? (
            <Badge tone="success" dot pulse>
              Live
            </Badge>
          ) : (
            <Badge tone="neutral" dot>
              {loading ? "Loading" : "No data"}
            </Badge>
          )
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={KeyRound}
          label="Accounts"
          value={data ? accounts.length : "—"}
          detail={data ? `${activeAccounts} available right now` : "Awaiting gateway data"}
          loading={firstLoad}
          emphasis="accent"
        />
        <MetricCard
          icon={Activity}
          label="Active"
          value={data ? activeAccounts : "—"}
          detail={accounts.length ? `${accounts.length - activeAccounts} cooling down` : "Ready to receive traffic"}
          loading={firstLoad}
        />
        <MetricCard
          icon={Boxes}
          label="Models"
          value={data ? data.models.length : "—"}
          detail="In the current catalog"
          loading={firstLoad}
        />
        <MetricCard
          icon={Route}
          label="Routing"
          value={data?.status.strategy ?? "—"}
          detail="Account selection strategy"
          loading={firstLoad}
        />
      </section>

      {data?.model_error && (
        <Callout tone="warning" title="Model catalog unavailable">
          {data.model_error}
        </Callout>
      )}

      {!loading && data && accounts.length === 0 ? (
        <EmptyGateway onAddAccount={onAddAccount} />
      ) : (
        <section className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <ProviderPanel providers={data?.providers ?? []} loading={firstLoad} />
          <ModelPanel models={data?.models ?? []} loading={firstLoad} />
        </section>
      )}
    </div>
  )
}

function EmptyGateway({ onAddAccount }: { onAddAccount: () => void }) {
  return (
    <section className="rounded-xl border border-dashed border-line-strong bg-surface px-6 py-14 text-center">
      <span className="mx-auto grid size-11 place-items-center rounded-xl border border-accent/20 bg-accent-soft text-accent-text">
        <Sparkles size={20} aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-semibold tracking-[-0.01em] text-ink">Your gateway is ready for its first account</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">
        Connect a ChatGPT account with the OpenAI device flow. Credentials are written to the gateway's encrypted volume, never to this page.
      </p>
      <Button className="mt-6" onClick={onAddAccount}>
        Connect an account
      </Button>
    </section>
  )
}

function ProviderPanel({ providers, loading }: { providers: Provider[]; loading: boolean }) {
  return (
    <Panel>
      <PanelHeader title="Providers" description="Availability by upstream service" />
      {loading ? (
        <SkeletonRows rows={2} />
      ) : providers.length ? (
        <div className="divide-y divide-line">
          {providers.map((provider) => (
            <article key={provider.id} className="flex items-center justify-between gap-4 px-5 py-4">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{provider.id}</p>
                <p className="mt-1 truncate text-[13px] text-subtle">
                  {provider.supported_endpoints.join(" · ") || "No endpoints reported"}
                </p>
              </div>
              <Badge tone={provider.active_accounts ? "success" : "warning"} dot className="shrink-0 tabular-nums">
                {provider.active_accounts}/{provider.accounts} active
              </Badge>
            </article>
          ))}
        </div>
      ) : (
        <PanelEmpty icon={<Database size={18} aria-hidden="true" />} title="No providers configured" />
      )}
    </Panel>
  )
}

function ModelPanel({ models, loading }: { models: Model[]; loading: boolean }) {
  const [query, setQuery] = useState("")

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return models
    return models.filter((model) => `${model.id} ${providerFor(model)}`.toLowerCase().includes(needle))
  }, [models, query])

  return (
    <Panel className="flex flex-col">
      <PanelHeader
        title="Available models"
        description={models.length ? `${filtered.length} of ${models.length} in the catalog` : "Current gateway catalog"}
        actions={
          models.length > 0 && (
            <div className="relative w-full sm:w-56">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle" aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter models"
                aria-label="Filter models"
                spellCheck={false}
                className="h-9 w-full rounded-lg border border-line bg-inset pl-9 pr-3 text-[13px] text-ink outline-none transition-[border-color,box-shadow] placeholder:text-subtle hover:border-line-strong focus:border-accent focus:ring-2 focus:ring-accent/25"
              />
            </div>
          )
        }
      />
      {loading ? (
        <SkeletonRows rows={5} />
      ) : filtered.length ? (
        <div className="max-h-[26rem] divide-y divide-line overflow-y-auto">
          {filtered.map((model) => {
            const context = contextWindow(model)
            return (
              <article key={model.id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                <div className="min-w-0">
                  <p className="truncate font-mono text-[13px] text-ink">{model.id}</p>
                  <p className="mt-1 truncate text-[12px] text-subtle">
                    {providerFor(model)}
                    {model.supported_endpoints?.length ? ` · ${model.supported_endpoints.join(" · ")}` : ""}
                  </p>
                </div>
                {context ? (
                  <span className="shrink-0 rounded-md border border-line bg-inset px-2 py-1 text-[12px] text-muted tabular-nums">
                    {compactNumber(context)} ctx
                  </span>
                ) : null}
              </article>
            )
          })}
        </div>
      ) : (
        <PanelEmpty
          icon={<Boxes size={18} aria-hidden="true" />}
          title={models.length ? "No models match that filter" : "No models available"}
          hint={models.length ? "Try a shorter search term." : "Connect an account to load the catalog."}
        />
      )}
    </Panel>
  )
}
