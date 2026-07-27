import { ArrowUpRight, Check, CircleAlert, CircleCheck, Copy, LoaderCircle } from "lucide-react"
import { useState } from "react"

import type { Login } from "../lib/api"
import { cn } from "../lib/utils"
import { Button } from "./ui/button"

export function DeviceLogin({ login, onCopy }: { login: Login; onCopy: (value: string) => void }) {
  const [copied, setCopied] = useState(false)

  if (login.status === "complete") {
    return (
      <section className="flex items-start gap-3 rounded-xl border border-success/25 bg-success-soft px-4 py-3.5">
        <CircleCheck size={17} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
        <div className="text-sm leading-6">
          <p className="font-medium text-ink">Account connected</p>
          <p className="text-muted">
            <span className="font-mono text-[13px]">{login.account_id}</span> is now available to the gateway.
          </p>
        </div>
      </section>
    )
  }

  if (login.status === "failed") {
    return (
      <section className="flex items-start gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3.5" role="alert">
        <CircleAlert size={17} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
        <div className="text-sm leading-6">
          <p className="font-medium text-ink">Sign-in did not complete</p>
          <p className="text-muted">{login.error ?? "Start a new device login and try again."}</p>
        </div>
      </section>
    )
  }

  function copy() {
    if (!login.user_code) return
    onCopy(login.user_code)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="rounded-xl border border-accent/25 bg-surface shadow-panel" aria-live="polite">
      <div className="flex items-center gap-3 border-b border-line px-5 py-4">
        <span className="grid size-8 place-items-center rounded-lg border border-accent/20 bg-accent-soft text-accent-text">
          <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-[-0.01em] text-ink">
            Finish signing in as <span className="font-mono">{login.account_id}</span>
          </h2>
          <p className="mt-0.5 text-[13px] text-subtle">Waiting for OpenAI to confirm the device…</p>
        </div>
      </div>

      <ol className="divide-y divide-line">
        <Step index={1} title="Open the secure OpenAI sign-in page">
          {login.verification_url ? (
            <a
              href={login.verification_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-accent-fg shadow-panel transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
            >
              <ArrowUpRight size={16} aria-hidden="true" />
              Open sign-in page
            </a>
          ) : (
            <p className="text-[13px] text-subtle">Preparing the sign-in link…</p>
          )}
        </Step>

        <Step index={2} title="Enter this one-time device code">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="min-w-0 rounded-lg border border-line bg-inset px-6 py-3 text-center font-mono text-lg font-semibold tracking-[0.28em] text-ink sm:min-w-[13rem]">
              {login.user_code ?? "······"}
            </code>
            <Button variant="secondary" onClick={copy} disabled={!login.user_code} className={cn(copied && "text-success")}>
              {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </Step>
      </ol>
    </section>
  )
}

function Step({ index, title, children }: { index: number; title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-4 px-5 py-4">
      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border border-line bg-inset text-[12px] font-semibold text-muted tabular-nums">
        {index}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-ink">{title}</p>
        <div className="mt-3">{children}</div>
      </div>
    </li>
  )
}
