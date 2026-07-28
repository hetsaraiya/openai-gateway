import {
  Activity,
  ArrowRight,
  Boxes,
  Braces,
  CheckCircle2,
  CircleOff,
  KeyRound,
  Route,
  Search,
  Sparkles,
  X,
} from "lucide-react"
import { useDeferredValue, useMemo, useState } from "react"

import { MetricCard } from "../components/metric-card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Callout } from "../components/ui/callout"
import { PanelEmpty, PageHeader } from "../components/ui/panel"
import { SkeletonRows } from "../components/ui/skeleton"
import {
  contextWindow,
  providerFor,
  providerLabel,
  type Dashboard,
  type Model,
} from "../lib/api"
import { cn } from "../lib/utils"
import { compactNumber } from "../lib/utils"

export function Overview({
  data,
  loading,
  selectedProvider,
  onSelectProvider,
  onAddAccount,
}: {
  data: Dashboard | null
  loading: boolean
  selectedProvider: string | null
  onSelectProvider: (provider: string | null) => void
  onAddAccount: () => void
}) {
  const accounts = data?.gateways ?? []
  const models = data?.models ?? []
  const providers = data?.providers ?? []
  const activeAccounts = accounts.filter((account) => account.active).length
  const firstLoad = !data && loading

  return (
    <div className="space-y-7">
      <PageHeader
        eyebrow="Live inventory"
        title="Models"
        description="Every model currently available through your gateway, organized by upstream provider and ready to use with one API."
        actions={
          data ? (
            <Badge tone="success" dot pulse>
              Gateway online
            </Badge>
          ) : (
            <Badge tone="neutral" dot>
              {loading ? "Loading" : "No data"}
            </Badge>
          )
        }
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Boxes}
          label="Available models"
          value={data ? models.length : "—"}
          detail={`Across ${providers.length} provider${providers.length === 1 ? "" : "s"}`}
          loading={firstLoad}
          emphasis="accent"
        />
        <MetricCard
          icon={KeyRound}
          label="Connected accounts"
          value={data ? accounts.length : "—"}
          detail={`${activeAccounts} ready to route`}
          loading={firstLoad}
        />
        <MetricCard
          icon={Activity}
          label="Provider health"
          value={data ? `${providers.filter((provider) => provider.active_accounts > 0).length}/${providers.length}` : "—"}
          detail="Providers with active capacity"
          loading={firstLoad}
        />
        <MetricCard
          icon={Route}
          label="Routing strategy"
          value={data?.status.strategy ?? "—"}
          detail="Applied to every request"
          loading={firstLoad}
        />
      </section>

      {data?.model_error ? (
        <Callout tone="warning" title="Some models could not be loaded">
          {data.model_error}
        </Callout>
      ) : null}

      {!loading && data && accounts.length === 0 ? (
        <EmptyGateway onAddAccount={onAddAccount} />
      ) : (
        <ModelCatalog
          models={models}
          loading={firstLoad}
          providers={providers.map((provider) => provider.id)}
          selectedProvider={selectedProvider}
          onSelectProvider={onSelectProvider}
        />
      )}
    </div>
  )
}

function EmptyGateway({ onAddAccount }: { onAddAccount: () => void }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-16 text-center">
      <div className="pointer-events-none absolute inset-x-1/4 top-0 h-32 rounded-full bg-accent/10 blur-3xl" aria-hidden="true" />
      <span className="relative mx-auto grid size-12 place-items-center rounded-xl border border-accent/20 bg-accent-soft text-accent-text">
        <Sparkles size={20} aria-hidden="true" />
      </span>
      <h2 className="relative mt-4 text-lg font-semibold tracking-[-0.02em] text-ink">Connect your first provider account</h2>
      <p className="relative mx-auto mt-2 max-w-md text-sm leading-6 text-muted">
        Add an OpenAI account or an OpenCode Go key to populate the model catalog and begin routing requests.
      </p>
      <Button className="relative mt-6" onClick={onAddAccount}>
        Manage accounts
        <ArrowRight size={16} aria-hidden="true" />
      </Button>
    </section>
  )
}

function ModelCatalog({
  models,
  providers,
  loading,
  selectedProvider,
  onSelectProvider,
}: {
  models: Model[]
  providers: string[]
  loading: boolean
  selectedProvider: string | null
  onSelectProvider: (provider: string | null) => void
}) {
  const [query, setQuery] = useState("")
  const deferredQuery = useDeferredValue(query)

  const providerCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const model of models) {
      const provider = providerFor(model)
      counts.set(provider, (counts.get(provider) ?? 0) + 1)
    }
    return counts
  }, [models])

  const filtered = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    return models.filter((model) => {
      if (selectedProvider && providerFor(model) !== selectedProvider) return false
      if (!needle) return true
      return [
        model.id,
        model.display_name,
        model.description,
        providerLabel(providerFor(model)),
        ...(model.supported_endpoints ?? []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle)
    })
  }, [deferredQuery, models, selectedProvider])

  const grouped = useMemo(() => {
    const groups = new Map<string, Model[]>()
    for (const model of filtered) {
      const provider = providerFor(model)
      const entries = groups.get(provider)
      if (entries) entries.push(model)
      else groups.set(provider, [model])
    }
    return groups
  }, [filtered])

  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-surface shadow-panel">
      <div className="border-b border-line px-5 py-5 sm:px-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Braces size={17} className="text-accent-text" aria-hidden="true" />
              <h2 className="text-base font-semibold tracking-[-0.02em] text-ink">Gateway model catalog</h2>
            </div>
            <p className="mt-1.5 text-[13px] text-subtle">
              Showing {filtered.length} of {models.length} models
              {selectedProvider ? ` from ${providerLabel(selectedProvider)}` : " across all providers"}
            </p>
          </div>

          <div className="relative w-full xl:w-80">
            <Search
              size={15}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-subtle"
              aria-hidden="true"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search models, endpoints, providers…"
              aria-label="Search model catalog"
              spellCheck={false}
              className="h-10 w-full rounded-xl border border-line bg-inset pl-10 pr-10 text-[13px] text-ink outline-none transition-[border-color,box-shadow] placeholder:text-subtle hover:border-line-strong focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-subtle hover:bg-surface hover:text-ink"
                aria-label="Clear search"
              >
                <X size={14} aria-hidden="true" />
              </button>
            ) : null}
          </div>
        </div>

        <div className="mt-5 flex gap-2 overflow-x-auto pb-0.5" aria-label="Filter by provider">
          <ProviderFilter
            label="All providers"
            count={models.length}
            active={!selectedProvider}
            onClick={() => onSelectProvider(null)}
          />
          {providers.map((provider) => (
            <ProviderFilter
              key={provider}
              label={providerLabel(provider)}
              count={providerCounts.get(provider) ?? 0}
              active={selectedProvider === provider}
              onClick={() => onSelectProvider(provider)}
            />
          ))}
        </div>
      </div>

      {loading ? (
        <SkeletonRows rows={6} />
      ) : grouped.size ? (
        <div className="divide-y divide-line">
          {[...grouped.entries()].map(([provider, providerModels]) => (
            <ProviderModels key={provider} provider={provider} models={providerModels} />
          ))}
        </div>
      ) : (
        <PanelEmpty
          icon={<CircleOff size={18} aria-hidden="true" />}
          title={models.length ? "No models match these filters" : "No models available"}
          hint={models.length ? "Try another provider or a shorter search term." : "Add a provider account to load its models."}
        />
      )}
    </section>
  )
}

function ProviderFilter({
  label,
  count,
  active,
  onClick,
}: {
  label: string
  count: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-2 rounded-lg border px-3 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        active
          ? "border-accent/25 bg-accent-soft text-accent-text"
          : "border-line bg-surface text-muted hover:border-line-strong hover:bg-inset hover:text-ink",
      )}
      aria-pressed={active}
    >
      {label}
      <span className={cn("text-[10px] tabular-nums", active ? "text-accent-text/70" : "text-subtle")}>{count}</span>
    </button>
  )
}

function ProviderModels({ provider, models }: { provider: string; models: Model[] }) {
  return (
    <section className="px-5 py-5 sm:px-6">
      <header className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg border border-line bg-inset text-accent-text">
            <Boxes size={15} aria-hidden="true" />
          </span>
          <div>
            <h3 className="text-[13px] font-semibold text-ink">{providerLabel(provider)}</h3>
            <p className="text-[11px] text-subtle">{provider}</p>
          </div>
        </div>
        <Badge tone="neutral">{models.length} models</Badge>
      </header>

      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {models.map((model) => (
          <ModelCard key={model.id} model={model} />
        ))}
      </div>
    </section>
  )
}

function ModelCard({ model }: { model: Model }) {
  const context = contextWindow(model)
  const endpoints = model.supported_endpoints ?? []
  const modalities = model.input_modalities ?? []

  return (
    <article className="group flex min-h-40 flex-col rounded-xl border border-line bg-elevated p-4 transition-[border-color,transform,box-shadow] hover:-translate-y-0.5 hover:border-line-strong hover:shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-ink" title={model.id}>
            {model.display_name || model.id}
          </p>
          {model.display_name && model.display_name !== model.id ? (
            <code className="mt-1 block truncate font-mono text-[10px] text-subtle" title={model.id}>
              {model.id}
            </code>
          ) : null}
        </div>
        {model.supported_in_api !== false ? (
          <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-success" aria-label="API ready" />
        ) : (
          <CircleOff size={15} className="mt-0.5 shrink-0 text-warning" aria-label="Not available in API" />
        )}
      </div>

      <p className="mt-3 line-clamp-2 text-[11px] leading-[1.55] text-muted">
        {model.description || "Available through the gateway with provider-native capabilities."}
      </p>

      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
        {context ? (
          <span className="rounded-md border border-line bg-surface px-2 py-1 text-[10px] font-medium text-muted tabular-nums">
            {compactNumber(context)} context
          </span>
        ) : null}
        {modalities.map((modality) => (
          <span key={modality} className="rounded-md border border-line bg-surface px-2 py-1 text-[10px] text-subtle">
            {modality}
          </span>
        ))}
        {endpoints.map((endpoint) => (
          <span
            key={endpoint}
            className="max-w-full truncate rounded-md bg-accent-soft px-2 py-1 font-mono text-[9px] text-accent-text"
            title={endpoint}
          >
            {endpoint.replace("/v1/", "")}
          </span>
        ))}
      </div>
    </article>
  )
}
