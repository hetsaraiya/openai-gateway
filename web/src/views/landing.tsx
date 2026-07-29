import {
  ArrowRight,
  Boxes,
  Check,
  Circle,
  Container,
  Copy,
  Database,
  GitBranch,
  KeyRound,
  LayoutDashboard,
  MessageSquareCode,
  RefreshCw,
  Route,
  ScrollText,
  Server,
  ShieldCheck,
  Split,
  Waves,
} from "lucide-react"
import { useEffect, useState } from "react"

import { CodeSample } from "../components/landing/code-sample"
import { ConsolePreview } from "../components/landing/console-preview"
import {
  CredentialDiagram,
  FailoverDiagram,
  PipelineDiagram,
  TopologyDiagram,
} from "../components/landing/diagrams"
import { Reveal } from "../components/landing/reveal"
import { ThemeToggle } from "../components/theme-toggle"
import { GatewayMark } from "../components/gateway-mark"
import type { Theme } from "../lib/theme"
import { cn } from "../lib/utils"

const REPO_URL = "https://github.com/hetsaraiya/openai-gateway"
const INSTALL_COMMAND = "docker compose up --build"

const NAV_LINKS = [
  { href: "#architecture", label: "Architecture" },
  { href: "#providers", label: "Providers" },
  { href: "#api", label: "API" },
  { href: "#security", label: "Security" },
  { href: "#console", label: "Console" },
]

const STATS = [
  { value: "4", label: "Providers behind one URL" },
  { value: "3", label: "Routing strategies" },
  { value: "4", label: "OpenAI-shaped endpoints" },
  { value: "0", label: "Upstream credentials sent to clients" },
]

const ROUTING_NOTES = [
  "Per-account state in Redis, shared across replicas.",
  "Rate-limited accounts are benched for a cooldown, then re-tried.",
  "Bounded retries — MAX_ACCOUNT_ATTEMPTS accounts per request, then a clean error.",
]

type Provider = {
  name: string
  status: "connected" | "cooling"
  rows: [string, string][]
}

const PROVIDERS: Provider[] = [
  {
    name: "OpenAI Codex",
    status: "connected",
    rows: [
      ["Authentication", "OAuth · auto refresh"],
      ["APIs", "chat · responses"],
      ["Model IDs", "gpt-5.1-codex, …"],
      ["Credentials", "auth/*.json on your disk"],
    ],
  },
  {
    name: "Cursor",
    status: "connected",
    rows: [
      ["Authentication", "cursor-agent CLI login"],
      ["APIs", "chat"],
      ["Model IDs", "cursor/<model>"],
      ["Credentials", "subscription session"],
    ],
  },
  {
    name: "Grok / xAI",
    status: "cooling",
    rows: [
      ["Authentication", "OAuth device flow"],
      ["APIs", "chat · responses"],
      ["Model IDs", "xai/<model>"],
      ["Extras", "prompt-cache affinity"],
    ],
  },
  {
    name: "OpenCode Go",
    status: "connected",
    rows: [
      ["Authentication", "subscription API keys"],
      ["APIs", "chat · messages"],
      ["Model IDs", "opencode-go/<model>"],
      ["Extras", "Anthropic-shaped requests"],
    ],
  },
]

const CAPABILITIES = [
  { icon: Circle, title: "OpenAI compatible", body: "Chat completions, the Responses API and model listing on the wire format your SDK already speaks." },
  { icon: MessageSquareCode, title: "Anthropic messages", body: "/v1/messages accepted for supported OpenCode Go models, translated on the way through." },
  { icon: Split, title: "Multi-account routing", body: "Fallback, round robin or quota-aware selection across every account you link." },
  { icon: RefreshCw, title: "OAuth refresh", body: "Expiring tokens are refreshed in the request path and written back to disk." },
  { icon: Route, title: "Cooldown and retry", body: "A rate-limited account is benched; the request continues on the next healthy one." },
  { icon: Waves, title: "Streaming first", body: "Upstream SSE is translated and forwarded chunk by chunk, never buffered whole." },
  { icon: Database, title: "Idempotency cache", body: "Redis-backed Idempotency-Key deduplication so a retried request is not billed twice." },
  { icon: Boxes, title: "Live model catalog", body: "Model IDs come from what each account can actually reach — nothing hardcoded." },
  { icon: KeyRound, title: "Device login built in", body: "Add Codex, Grok or Cursor accounts from the console without touching the host." },
  { icon: LayoutDashboard, title: "Operator console", body: "Providers, models, account health and per-account connection tests in one view." },
  { icon: ScrollText, title: "Structured logging", body: "Request IDs and the serving account on every line. Prompt and response bodies never." },
  { icon: Container, title: "Docker and Compose", body: "One image, one env file, Redis alongside, and a health endpoint to gate rollout." },
]

const SECURITY_CARDS = [
  { title: "One key at the edge", body: "Clients present a master key you set. Nothing upstream is ever handed out." },
  { title: "Credentials stay put", body: "Account files live in auth/, git-ignored, owned by the gateway user alone." },
  { title: "Metadata-only logs", body: "Request IDs, accounts and timings are logged; message bodies are not." },
  { title: "No phone-home", body: "No telemetry and no hosted control plane. The only egress is to the providers." },
]

const STACK = ["Python 3.12", "FastAPI", "Redis", "React", "TypeScript", "Docker"]

/** Section eyebrow + heading, shared by every band below the hero. */
function SectionHeader({ eyebrow, title, body, className }: { eyebrow: string; title: string; body?: string; className?: string }) {
  return (
    <div className={cn("max-w-[39rem]", className)}>
      <p className="font-mono text-[11px] tracking-[0.1em] text-accent-text">{eyebrow}</p>
      <h2 className="mt-4 text-[clamp(1.9rem,4vw,2.75rem)] font-semibold leading-[1.08] tracking-[-0.03em] text-ink">{title}</h2>
      {body && <p className="mt-4 text-[17px] leading-[1.6] text-muted">{body}</p>}
    </div>
  )
}

/** Copies a shell command to the clipboard and confirms inline. */
function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
    } catch {
      // Clipboard access can be denied; the command is selectable either way.
    }
  }

  return (
    <div className="flex max-w-[32.5rem] items-center gap-3 rounded-xl border border-line bg-elevated py-3 pl-3.5 pr-3">
      <span className="font-mono text-[12.5px] text-subtle">$</span>
      <code className="truncate font-mono text-[12.5px] text-ink">{command}</code>
      <button
        type="button"
        onClick={() => void copy()}
        className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1.5 font-mono text-[11px] text-muted transition-colors hover:border-accent hover:text-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
        {copied ? "copied" : "copy"}
      </button>
    </div>
  )
}

const PRIMARY_CTA =
  "inline-flex items-center gap-2.5 rounded-xl bg-accent px-5 py-3.5 text-[15px] font-medium text-accent-fg shadow-panel transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-float focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
const SECONDARY_CTA =
  "inline-flex items-center gap-2.5 rounded-xl border border-line bg-surface px-5 py-3.5 text-[15px] font-medium text-ink transition-[transform,border-color] duration-200 hover:-translate-y-0.5 hover:border-line-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
const CARD = "rounded-2xl border border-line bg-surface"

export function Landing({ theme, onToggleTheme, onOpenConsole }: { theme: Theme; onToggleTheme: () => void; onOpenConsole: () => void }) {
  return (
    <div className="relative overflow-x-hidden bg-canvas">
      <header className="sticky top-0 z-50 border-b border-line bg-canvas/80 backdrop-blur-md backdrop-saturate-150">
        <div className="mx-auto flex h-16 max-w-[75rem] items-center gap-8 px-5 sm:px-8">
          <a href="#top" className="flex flex-none items-center gap-2.5 text-ink">
            <span className="grid size-7 place-items-center rounded-lg border border-line bg-inset text-accent-text">
              <GatewayMark size={16} />
            </span>
            <span className="text-[15px] font-semibold tracking-[-0.01em] whitespace-nowrap">OpenAI Gateway</span>
            <span className="hidden rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] font-medium text-subtle sm:inline">
              self-hosted
            </span>
          </a>

          <nav className="hidden min-w-0 items-center gap-6 lg:flex xl:gap-7">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="text-sm whitespace-nowrap text-muted transition-colors hover:text-ink">
                {link.label}
              </a>
            ))}
          </nav>

          <div className="ml-auto flex flex-none items-center gap-2">
            <ThemeToggle theme={theme} onToggle={onToggleTheme} />
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="hidden items-center gap-2 rounded-lg border border-line px-3 py-2 text-[13px] font-medium text-ink transition-colors hover:border-line-strong hover:bg-elevated sm:inline-flex"
            >
              <GitBranch size={14} aria-hidden="true" />
              GitHub
            </a>
            <button
              type="button"
              onClick={onOpenConsole}
              className="rounded-lg bg-ink px-3.5 py-2 text-[13px] font-medium whitespace-nowrap text-canvas transition-colors hover:bg-accent hover:text-accent-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
            >
              Open console
            </button>
          </div>
        </div>
      </header>

      <main id="top">
        {/* Hero */}
        <section className="relative px-5 pb-16 pt-20 sm:px-8 sm:pb-20 sm:pt-24">
          <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
            <div
              className="absolute -inset-24 animate-grid opacity-70"
              style={{
                backgroundImage:
                  "linear-gradient(to right, var(--line) 1px, transparent 1px), linear-gradient(to bottom, var(--line) 1px, transparent 1px)",
                backgroundSize: "56px 56px",
                maskImage: "radial-gradient(120% 90% at 60% 10%, #000 0%, transparent 72%)",
                WebkitMaskImage: "radial-gradient(120% 90% at 60% 10%, #000 0%, transparent 72%)",
              }}
            />
          </div>

          <div className="relative mx-auto grid max-w-[75rem] items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)] lg:gap-16">
            <div>
              <p className="inline-flex items-center gap-2.5 rounded-full border border-line bg-surface py-1.5 pl-2.5 pr-3 text-[12.5px] text-muted">
                <span className="relative inline-flex size-[7px]" aria-hidden="true">
                  <span className="absolute inset-0 rounded-full bg-accent" />
                  <span className="absolute inset-0 animate-ring rounded-full bg-accent" />
                </span>
                Self-hosted · no vendor lock-in
              </p>

              <h1 className="mt-6 text-[clamp(2.6rem,6vw,4.25rem)] font-semibold leading-[1.02] tracking-[-0.035em] text-ink">
                One endpoint for every AI coding subscription you already pay for.
              </h1>

              <p className="mt-6 max-w-[33rem] text-[18.5px] leading-[1.6] text-muted">
                An OpenAI-compatible gateway that unifies Codex, Cursor, Grok and OpenCode Go behind a single URL. Route across
                accounts, ride out rate limits, and keep every credential on your own infrastructure.
              </p>

              <div className="mt-9 flex flex-wrap items-center gap-3">
                <a href="#quickstart" className={PRIMARY_CTA}>
                  Deploy the gateway
                  <ArrowRight size={15} aria-hidden="true" />
                </a>
                <a href="#api" className={SECONDARY_CTA}>
                  Read the API reference
                </a>
              </div>

              <div id="quickstart" className="mt-8 scroll-mt-24">
                <CopyCommand command={INSTALL_COMMAND} />
                <p className="mt-3 text-[13px] text-subtle">
                  Set <code className="font-mono text-muted">GATEWAY_API_KEY</code>, drop a credential file in{" "}
                  <code className="font-mono text-muted">auth/</code>, and the gateway answers on{" "}
                  <code className="font-mono text-muted">:8000</code>.
                </p>
              </div>
            </div>

            <div className="relative">
              <TopologyDiagram />
            </div>
          </div>
        </section>

        {/* Stat band */}
        <Reveal className="border-y border-line bg-elevated">
          <div className="mx-auto grid max-w-[75rem] grid-cols-2 gap-8 px-5 py-10 sm:px-8 lg:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.label}>
                <p className="font-mono text-[30px] font-medium tracking-[-0.02em] text-ink tabular-nums">{stat.value}</p>
                <p className="mt-1.5 text-[13px] text-muted">{stat.label}</p>
              </div>
            ))}
          </div>
        </Reveal>

        {/* API */}
        <Reveal id="api" className="scroll-mt-16 px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[75rem]">
            <SectionHeader
              eyebrow="DROP-IN COMPATIBLE"
              title="Change the base URL. Nothing else."
              body="The gateway speaks the OpenAI wire format — chat completions, streaming and the Responses API. Every SDK, agent framework and editor plugin you already use keeps working."
            />
            <div className="mt-11">
              <CodeSample />
            </div>
          </div>
        </Reveal>

        {/* Architecture */}
        <Reveal id="architecture" className="scroll-mt-16 border-t border-line bg-elevated px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[75rem]">
            <SectionHeader
              eyebrow="ARCHITECTURE"
              title="A single hop between your agent and every subscription."
              body="A stateless request path, a Redis-backed dedup and cooldown ledger, and a router that knows which account can serve the model you asked for."
            />
            <div className={cn(CARD, "mt-14 px-6 py-10 sm:px-8")}>
              <PipelineDiagram />
            </div>
          </div>
        </Reveal>

        {/* Routing */}
        <Reveal className="border-t border-line px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto grid max-w-[75rem] items-center gap-12 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-18">
            <div>
              <SectionHeader
                eyebrow="ACCOUNT ROUTING"
                title="Rate limits stop being your problem."
                body="Requests spread across every account you have linked. When one hits a quota wall the router benches it, retries on the next healthy account, and returns the response — the client never sees the 429."
              />
              <ol className="mt-7 grid gap-3.5">
                {ROUTING_NOTES.map((note, index) => (
                  <li key={note} className="flex items-baseline gap-3">
                    <span className="font-mono text-[11px] text-accent-text">{String(index + 1).padStart(2, "0")}</span>
                    <span className="text-[14.5px] leading-[1.55] text-muted">{note}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div className={cn(CARD, "bg-elevated p-7")}>
              <FailoverDiagram />
            </div>
          </div>
        </Reveal>

        {/* Providers */}
        <Reveal id="providers" className="scroll-mt-16 border-t border-line bg-elevated px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[75rem]">
            <div className="flex flex-wrap items-end justify-between gap-10">
              <SectionHeader eyebrow="PROVIDERS" title="Four upstreams, one contract." />
              <p className="max-w-[20rem] text-[15px] text-muted">
                Each provider is an adapter: an auth flow, a model map and a health probe. Adding a fifth is one module.
              </p>
            </div>

            <div className="mt-12 grid gap-5 md:grid-cols-2">
              {PROVIDERS.map((provider) => (
                <article
                  key={provider.name}
                  className={cn(
                    CARD,
                    "px-7 py-6 transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-float",
                  )}
                >
                  <div className="flex items-center justify-between gap-4">
                    <h3 className="text-[18px] font-semibold tracking-[-0.01em] text-ink">{provider.name}</h3>
                    <span
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[10.5px]",
                        provider.status === "connected"
                          ? "border-accent/25 bg-accent-soft text-accent-text"
                          : "border-line bg-inset text-muted",
                      )}
                    >
                      <span
                        className={cn(
                          "size-[5px] rounded-full",
                          provider.status === "connected" ? "animate-node bg-accent" : "bg-line-strong",
                        )}
                        aria-hidden="true"
                      />
                      {provider.status === "connected" ? "connected" : "cooling down"}
                    </span>
                  </div>

                  <dl className="mt-5 grid gap-3 text-[13px]">
                    {provider.rows.map(([label, value], index) => (
                      <div
                        key={label}
                        className={cn(
                          "flex justify-between gap-4",
                          index < provider.rows.length - 1 && "border-b border-line/70 pb-2.5",
                        )}
                      >
                        <dt className="text-subtle">{label}</dt>
                        <dd className="truncate font-mono text-ink">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
              ))}
            </div>
          </div>
        </Reveal>

        {/* Capabilities */}
        <Reveal className="border-t border-line px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[75rem]">
            <SectionHeader eyebrow="CAPABILITIES" title="Everything a gateway should do. Nothing it shouldn't." />
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {CAPABILITIES.map(({ icon: Icon, title, body }) => (
                <article
                  key={title}
                  className="rounded-xl border border-line p-5 transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-panel"
                >
                  <Icon size={19} className="text-accent-text" aria-hidden="true" />
                  <h3 className="mt-4 text-[15.5px] font-semibold text-ink">{title}</h3>
                  <p className="mt-2 text-[13.5px] leading-[1.55] text-muted">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </Reveal>

        {/* Security */}
        <Reveal id="security" className="scroll-mt-16 border-t border-line bg-elevated px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[75rem]">
            <SectionHeader
              eyebrow="SECURITY MODEL"
              title="Your credentials never leave your network."
              body="Clients authenticate with a master key you issue. Upstream tokens are read from disk in the request path, refreshed when they expire, and never written to a log or returned to a caller."
            />
            <div className={cn(CARD, "mt-13 px-6 py-9 sm:px-8")}>
              <CredentialDiagram />
              <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {SECURITY_CARDS.map((card) => (
                  <div key={card.title} className="rounded-xl border border-line p-4">
                    <h3 className="text-[13.5px] font-semibold text-ink">{card.title}</h3>
                    <p className="mt-1.5 text-[12.5px] leading-[1.5] text-muted">{card.body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Reveal>

        {/* Console */}
        <Reveal id="console" className="scroll-mt-16 border-t border-line px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-[75rem]">
            <div className="flex flex-wrap items-end justify-between gap-8">
              <SectionHeader eyebrow="OPERATOR CONSOLE" title="See exactly which account served which request." />
              <button type="button" onClick={onOpenConsole} className={SECONDARY_CTA}>
                Open the console
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            </div>
            <div className="mt-11">
              <ConsolePreview />
            </div>
          </div>
        </Reveal>

        {/* Open source */}
        <Reveal id="opensource" className="scroll-mt-16 border-t border-line bg-elevated px-5 py-24 sm:px-8 sm:py-28">
          <div className="mx-auto grid max-w-[75rem] items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:gap-18">
            <div>
              <SectionHeader
                eyebrow="OPEN SOURCE"
                title="Read every line before you trust it."
                body="The gateway is a FastAPI service, a React console and a Redis dependency you probably already run. Clone it, read it, run it on your own box."
              />
              <ul className="mt-7 flex flex-wrap gap-2">
                {STACK.map((item) => (
                  <li
                    key={item}
                    className="rounded-full border border-line bg-surface px-3 py-1.5 font-mono text-[11.5px] text-muted"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className={cn(CARD, "p-6 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-float")}>
              <div className="flex items-center gap-2.5">
                <GitBranch size={18} className="text-ink" aria-hidden="true" />
                <span className="font-mono text-[13px] text-ink">hetsaraiya / openai-gateway</span>
              </div>
              <p className="mt-3.5 text-[13.5px] leading-[1.6] text-muted">
                Self-hosted OpenAI-compatible gateway for AI coding subscriptions. Multi-account routing, cooldown-aware
                failover, live model discovery.
              </p>

              <div className="mt-5 h-px bg-line" />

              <dl className="mt-4 grid gap-2.5 font-mono text-[11.5px] text-muted">
                <div className="flex justify-between gap-4">
                  <dt>runtime</dt>
                  <dd className="text-ink">Python 3.12 · FastAPI</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>deploy</dt>
                  <dd className="text-ink">docker compose</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>tests</dt>
                  <dd className="text-ink">uv run pytest</dd>
                </div>
              </dl>

              <a
                href={REPO_URL}
                target="_blank"
                rel="noreferrer"
                className="mt-6 flex items-center justify-center gap-2 rounded-lg bg-ink px-4 py-3 text-sm font-medium text-canvas transition-colors hover:bg-accent hover:text-accent-fg"
              >
                View on GitHub
                <ArrowRight size={15} aria-hidden="true" />
              </a>
            </div>
          </div>
        </Reveal>

        {/* Closing CTA */}
        <Reveal className="border-t border-line px-5 py-28 text-center sm:px-8 sm:py-32">
          <div className="mx-auto max-w-[47rem]">
            <h2 className="text-[clamp(2.1rem,5vw,3.25rem)] font-semibold leading-[1.05] tracking-[-0.035em] text-ink">
              Ship it in the time it takes to read the README.
            </h2>
            <p className="mt-5 text-[17.5px] leading-[1.6] text-muted">
              One container, one master key, one base URL. Everything else stays exactly where it is.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <a href="#quickstart" className={PRIMARY_CTA}>
                <Server size={15} aria-hidden="true" />
                Deploy the gateway
              </a>
              <button type="button" onClick={onOpenConsole} className={SECONDARY_CTA}>
                <ShieldCheck size={15} aria-hidden="true" />
                Open the console
              </button>
            </div>
          </div>
        </Reveal>
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto grid max-w-[75rem] gap-10 px-5 py-12 sm:px-8 md:grid-cols-[minmax(0,1fr)_auto]">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="grid size-6 place-items-center rounded-md border border-line bg-inset text-accent-text">
                <GatewayMark size={14} />
              </span>
              <span className="text-sm font-semibold text-ink">OpenAI Gateway</span>
            </div>
            <p className="mt-3 max-w-[34rem] text-[13px] leading-[1.6] text-subtle">
              Not affiliated with any provider listed. Trademarks belong to their owners. Use only accounts and workloads you
              are authorized to operate.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-7 gap-y-3 md:flex-nowrap md:justify-end">
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-[13.5px] text-muted transition-colors hover:text-ink">
              GitHub
            </a>
            <a href="#api" className="text-[13.5px] text-muted transition-colors hover:text-ink">
              API
            </a>
            <a href="#architecture" className="text-[13.5px] text-muted transition-colors hover:text-ink">
              Architecture
            </a>
            <a href="#security" className="text-[13.5px] text-muted transition-colors hover:text-ink">
              Security
            </a>
            <button type="button" onClick={onOpenConsole} className="text-[13.5px] text-muted transition-colors hover:text-ink">
              Console
            </button>
          </nav>
        </div>
      </footer>
    </div>
  )
}
