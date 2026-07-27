import { Eye, EyeOff, LoaderCircle, LockKeyhole, ShieldCheck } from "lucide-react"
import { useState } from "react"

import { ApiError, checkKey } from "../lib/api"
import { SESSION_DAYS } from "../lib/session"
import type { Theme } from "../lib/theme"
import { BrandMark } from "./brand"
import { ThemeToggle } from "./theme-toggle"
import { Button } from "./ui/button"
import { Callout } from "./ui/callout"
import { Field, Input } from "./ui/input"

export function AccessGate({
  theme,
  notice,
  onToggleTheme,
  onVerified,
}: {
  theme: Theme
  notice?: string
  onToggleTheme: () => void
  onVerified: (key: string) => Promise<void>
}) {
  const [key, setKey] = useState("")
  const [reveal, setReveal] = useState(false)
  const [error, setError] = useState("")
  const [checking, setChecking] = useState(false)

  async function verify(event: React.FormEvent) {
    event.preventDefault()
    setError("")
    setChecking(true)
    try {
      await checkKey(key.trim())
      await onVerified(key.trim())
    } catch (cause) {
      const failure = cause as ApiError
      setError(failure.status === 401 ? "That gateway key was not accepted. Check it and try again." : failure.message)
      setChecking(false)
    }
  }

  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden px-4 py-10">
      {/* A single soft sapphire wash keeps the sign-in screen from reading as a flat slab. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[32rem] opacity-70"
        style={{ background: "radial-gradient(60% 100% at 50% 0%, color-mix(in oklab, var(--accent) 20%, transparent), transparent 70%)" }}
        aria-hidden="true"
      />

      <div className="absolute right-4 top-4">
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>

      <section className="relative w-full max-w-[26rem] rounded-2xl border border-line bg-surface p-7 shadow-float sm:p-8">
        <BrandMark size={44} className="rounded-xl" />
        <h1 className="mt-5 text-xl font-semibold tracking-[-0.02em] text-ink">OpenAI Gateway</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Enter your gateway key to open the operations console. Nothing is requested before the key is verified.
        </p>

        {notice && (
          <Callout tone="warning" className="mt-5">
            {notice}
          </Callout>
        )}

        <form className="mt-7 space-y-4" onSubmit={verify} noValidate>
          <Field label="Gateway API key" htmlFor="gateway-key" error={error}>
            <div className="relative">
              <Input
                id="gateway-key"
                name="gateway-key"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                type={reveal ? "text" : "password"}
                autoComplete="current-password"
                placeholder="Paste your gateway API key"
                spellCheck={false}
                autoFocus
                className="pr-11 font-mono"
                aria-invalid={error ? true : undefined}
              />
              <button
                type="button"
                onClick={() => setReveal((shown) => !shown)}
                className="absolute right-1 top-1 grid size-8 place-items-center rounded-md text-subtle transition-colors hover:bg-inset hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                aria-label={reveal ? "Hide key" : "Show key"}
              >
                {reveal ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
          </Field>

          <Button type="submit" size="lg" className="w-full" disabled={!key.trim() || checking}>
            {checking ? (
              <LoaderCircle size={17} className="animate-spin" aria-hidden="true" />
            ) : (
              <ShieldCheck size={17} aria-hidden="true" />
            )}
            {checking ? "Verifying…" : "Unlock console"}
          </Button>
        </form>

        <p className="mt-6 flex items-start gap-2 border-t border-line pt-5 text-[13px] leading-5 text-subtle">
          <LockKeyhole size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          The key is kept in this browser so you stay signed in, and is cleared after {SESSION_DAYS} days of
          inactivity or when you lock the console.
        </p>
      </section>
    </main>
  )
}
