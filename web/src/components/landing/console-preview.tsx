import { useEffect, useState } from "react"

import { cn } from "../../lib/utils"
import { GatewayMark } from "../gateway-mark"

const NAV = [
  { label: "Models", badge: "live", accent: true },
  { label: "Accounts", badge: "7", accent: false },
  { label: "Providers", badge: "4", accent: false },
  { label: "Routing", badge: "", accent: false },
  { label: "Health", badge: "", accent: false },
]

const METRICS = [
  { label: "Available models", value: "18" },
  { label: "Active accounts", value: "7" },
  { label: "Providers", value: "4" },
  { label: "Cooling down", value: "1" },
]

const ROWS: { account: string; provider: string; model: string; state: string; healthy: boolean }[] = [
  { account: "codex · main", provider: "codex", model: "gpt-5.1-codex", state: "healthy", healthy: true },
  { account: "codex · backup", provider: "codex", model: "gpt-5.1-codex", state: "healthy", healthy: true },
  { account: "cursor · team", provider: "cursor", model: "cursor/composer", state: "healthy", healthy: true },
  { account: "grok · personal", provider: "xai", model: "xai/grok-4.5", state: "cooldown", healthy: false },
  { account: "opencode · sub", provider: "opencode-go", model: "opencode-go/…", state: "healthy", healthy: true },
]

const BAR_COUNT = 44
const TICK_MS = 1400

function nextBars(previous: number[]): number[] {
  const sample = () => 24 + Math.random() * 68
  if (previous.length === 0) return Array.from({ length: BAR_COUNT }, sample)
  return [...previous.slice(1), sample()]
}

/** A scrolling traffic sparkline. Static when the reader prefers reduced motion. */
function TrafficBars() {
  const [bars, setBars] = useState<number[]>(() => nextBars([]))

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    const timer = window.setInterval(() => setBars(nextBars), TICK_MS)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="mt-4 flex h-24 items-end gap-[3px]" aria-hidden="true">
      {bars.map((height, index) => (
        <div
          key={index}
          className={cn(
            "flex-1 rounded-t-[2px] transition-[height] duration-500 ease-out",
            index > BAR_COUNT - 6 ? "bg-accent" : index % 7 === 0 ? "bg-accent/30" : "bg-inset",
          )}
          style={{ height: `${height.toFixed(1)}%` }}
        />
      ))}
    </div>
  )
}

/** A non-interactive likeness of the operator console, used on the landing page. */
export function ConsolePreview() {
  return (
    <div className="overflow-hidden rounded-2xl border border-line shadow-panel">
      <div className="grid md:grid-cols-[216px_minmax(0,1fr)]">
        <aside className="hidden border-r border-line bg-elevated p-4 md:block">
          <div className="flex items-center gap-2.5 px-2 py-1.5">
            <span className="grid size-6 place-items-center rounded-md border border-line bg-inset text-accent-text">
              <GatewayMark size={14} />
            </span>
            <span className="text-[13px] font-semibold text-ink">gateway.internal</span>
          </div>

          <div className="mt-4 grid gap-0.5">
            {NAV.map((item, index) => (
              <div
                key={item.label}
                className={cn(
                  "flex items-center justify-between rounded-md px-2.5 py-1.5 text-[13px]",
                  index === 0 ? "border border-line bg-surface font-medium text-ink" : "text-muted",
                )}
              >
                {item.label}
                {item.badge && (
                  <span className={cn("font-mono text-[10px]", item.accent ? "text-accent-text" : "text-subtle")}>{item.badge}</span>
                )}
              </div>
            ))}
          </div>

          <p className="mt-6 px-2.5 font-mono text-[10px] tracking-[0.08em] text-subtle">CLUSTER</p>
          <dl className="mt-2.5 grid gap-2 px-2.5 font-mono text-[11px] text-muted">
            <div className="flex justify-between">
              <dt>redis</dt>
              <dd className="text-accent-text">ok</dd>
            </div>
            <div className="flex justify-between">
              <dt>strategy</dt>
              <dd className="text-ink">quota</dd>
            </div>
            <div className="flex justify-between">
              <dt>attempts</dt>
              <dd className="text-ink">3</dd>
            </div>
          </dl>
        </aside>

        <div className="bg-surface p-6">
          <div className="flex items-baseline justify-between gap-5">
            <div>
              <p className="text-[19px] font-semibold tracking-[-0.01em] text-ink">Models</p>
              <p className="mt-1 text-[12.5px] text-subtle">Live inventory across every linked account</p>
            </div>
            <div className="hidden gap-2 sm:flex">
              {["1h", "24h", "7d"].map((range, index) => (
                <span
                  key={range}
                  className={cn(
                    "rounded-md border px-2.5 py-1 font-mono text-[11px]",
                    index === 0 ? "border-line text-muted" : "border-transparent text-subtle",
                  )}
                >
                  {range}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
            {METRICS.map((metric) => (
              <div key={metric.label} className="rounded-lg border border-line p-3.5">
                <p className="text-[11.5px] text-subtle">{metric.label}</p>
                <p className="mt-2 font-mono text-[19px] text-ink tabular-nums">{metric.value}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-lg border border-line p-4">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold text-ink">Requests by account</p>
              <p className="font-mono text-[10.5px] text-subtle">round robin</p>
            </div>
            <TrafficBars />
          </div>

          <div className="mt-6 overflow-hidden rounded-lg border border-line">
            <div className="grid grid-cols-[1.4fr_1fr_1.2fr_.8fr] gap-3 border-b border-line bg-elevated px-4 py-2.5 font-mono text-[10.5px] tracking-[0.06em] text-subtle">
              <div>ACCOUNT</div>
              <div>PROVIDER</div>
              <div className="hidden sm:block">MODEL</div>
              <div>STATE</div>
            </div>
            {ROWS.map((row) => (
              <div
                key={row.account}
                className="grid grid-cols-[1.4fr_1fr_1.2fr_.8fr] items-center gap-3 border-b border-line/60 px-4 py-3 font-mono text-[11.5px] text-muted last:border-b-0"
              >
                <div className="truncate text-ink">{row.account}</div>
                <div className="truncate">{row.provider}</div>
                <div className="hidden truncate sm:block">{row.model}</div>
                <div className={row.healthy ? "text-accent-text" : "text-subtle"}>{row.state}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
