import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  ArrowUpRight,
  Bot,
  Check,
  CircleAlert,
  Copy,
  Database,
  KeyRound,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  Menu,
  Plus,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react"

import { Button } from "./components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "./components/ui/dialog"
import { Input } from "./components/ui/input"
import gatewayMark from "./assets/gateway-mark.png"
import { cn } from "./lib/utils"

type Gateway = { id: string; provider: string; plan?: string; active: boolean; used_today?: number }
type Model = { id: string; gateway?: string; context_window?: number; max_context_window?: number; supported_endpoints?: string[] }
type Provider = { id: string; accounts: number; active_accounts: number; supported_endpoints: string[] }
type Dashboard = {
  status: { strategy: string }
  gateways: Gateway[]
  models: Model[]
  providers: Provider[]
  model_error?: string | null
}
type Login = { id: string; account_id: string; status: "starting" | "pending" | "complete" | "failed"; verification_url?: string; user_code?: string; error?: string }
type View = "overview" | "accounts"

const NAVIGATION: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "accounts", label: "Accounts", icon: KeyRound },
]

function providerFor(model: Model) {
  return model.gateway ?? (model.id.startsWith("opencode-go/") ? "opencode-go" : "codex")
}

function compactNumber(value: number | undefined) {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value ?? 0)
}

async function responseBody(response: Response) {
  const body: unknown = await response.json().catch(() => null)
  if (body && typeof body === "object" && "error" in body) {
    const error = (body as { error?: { message?: string } }).error
    return error?.message ?? `Request failed (${response.status}).`
  }
  return `Request failed (${response.status}).`
}

function StatusPill({ active, children }: { active: boolean; children: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", active ? "bg-emerald-400/10 text-emerald-200" : "bg-amber-400/10 text-amber-200")}>
      <span className={cn("size-1.5 rounded-full", active ? "bg-emerald-300" : "bg-amber-300")} aria-hidden="true" />
      {children}
    </span>
  )
}

function MetricCard({ icon: Icon, label, value, detail }: { icon: typeof Bot; label: string; value: string | number; detail: string }) {
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-sm shadow-black/10">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-400">{label}</p>
        <span className="grid size-9 place-items-center rounded-xl border border-slate-700 bg-slate-800 text-emerald-300"><Icon size={18} aria-hidden="true" /></span>
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight text-white tabular-nums">{value}</p>
      <p className="mt-1 text-sm text-slate-500">{detail}</p>
    </article>
  )
}

function EmptyState({ onAddAccount }: { onAddAccount: () => void }) {
  return (
    <section className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-12 text-center">
      <span className="mx-auto grid size-12 place-items-center rounded-2xl border border-slate-700 bg-slate-800 text-emerald-300"><Sparkles size={22} aria-hidden="true" /></span>
      <h2 className="mt-5 text-lg font-semibold text-white">Your gateway is ready for an account</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">Connect a ChatGPT account with the secure device flow. Its credentials stay in your gateway’s encrypted runtime volume.</p>
      <Button className="mt-6" onClick={onAddAccount}><Plus size={17} aria-hidden="true" />Connect an account</Button>
    </section>
  )
}

function Header({ loading, onRefresh, onLock, menuOpen, onToggleMenu }: { loading: boolean; onRefresh: () => void; onLock: () => void; menuOpen: boolean; onToggleMenu: () => void }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-800/90 bg-slate-950/90 backdrop-blur-xl">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-slate-950">Skip to main content</a>
      <div className="mx-auto flex h-18 max-w-[1600px] items-center gap-3 px-4 sm:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={onToggleMenu} aria-expanded={menuOpen} aria-label="Toggle navigation">
          {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </Button>
        <div className="min-w-0 flex-1 items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center overflow-hidden rounded-xl bg-slate-800"><img src={gatewayMark} width="40" height="40" alt="" aria-hidden="true" /></span>
          <div className="min-w-0"><p className="truncate text-sm font-semibold text-white">OpenAI Gateway</p><p className="truncate text-xs text-slate-500">Operations console</p></div>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="secondary" size="icon" disabled={loading} onClick={onRefresh} aria-label="Refresh gateway data">
            <RefreshCw size={18} className={cn(loading && "animate-spin motion-reduce:animate-none")} aria-hidden="true" />
          </Button>
          <Button type="button" variant="ghost" className="hidden sm:inline-flex" onClick={onLock}><LockKeyhole size={16} aria-hidden="true" />Lock</Button>
        </div>
      </div>
    </header>
  )
}

function AccessGate({ onVerified }: { onVerified: (key: string) => Promise<void> }) {
  const [key, setKey] = useState("")
  const [error, setError] = useState("")
  const [checking, setChecking] = useState(false)

  async function verify(event: React.FormEvent) {
    event.preventDefault()
    setError("")
    setChecking(true)
    try {
      const response = await fetch("/dashboard/auth/check", { method: "POST", headers: { "X-Gateway-Key": key.trim() } })
      if (!response.ok) {
        setError(response.status === 401 ? "This gateway key was not accepted. Check it and try again." : await responseBody(response))
        return
      }
      await onVerified(key.trim())
    } catch {
      setError("The gateway could not be reached. Check the connection and try again.")
    } finally {
      setChecking(false)
    }
  }

  return <main className="grid min-h-dvh place-items-center overflow-x-hidden bg-slate-950 bg-[radial-gradient(ellipse_at_top,rgba(143,102,162,0.24),transparent_38rem)] p-4 text-slate-100"><section className="w-full max-w-md rounded-3xl border border-slate-700/80 bg-slate-900/90 p-6 shadow-2xl shadow-black/30 sm:p-8"><div className="flex items-center gap-4"><span className="grid size-14 shrink-0 place-items-center overflow-hidden rounded-2xl border border-slate-700 bg-slate-800"><img src={gatewayMark} width="56" height="56" alt="OpenAI Gateway shield mark" /></span><div><p className="text-sm font-medium text-emerald-300">Private operations console</p><h1 className="mt-1 text-balance text-2xl font-semibold tracking-tight text-white">OpenAI Gateway</h1></div></div><p className="mt-7 text-sm leading-6 text-slate-400">Enter your gateway key to unlock the dashboard. Nothing else is requested until the key is verified.</p><form className="mt-6 space-y-3" onSubmit={verify}><div className="space-y-2"><label className="text-sm font-medium text-slate-200" htmlFor="access-key">Gateway API key</label><Input id="access-key" name="gateway-key" value={key} onChange={(event) => setKey(event.target.value)} type="password" autoComplete="current-password" placeholder="Paste your gateway API key…" spellCheck={false} /></div>{error && <p className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-100" role="alert">{error}</p>}<Button type="submit" className="w-full" disabled={!key.trim() || checking}>{checking ? <LoaderCircle size={17} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <ShieldCheck size={17} aria-hidden="true" />}{checking ? "Verifying secure access…" : "Unlock dashboard"}</Button></form><p className="mt-6 flex items-start gap-2 text-xs leading-5 text-slate-500"><LockKeyhole size={15} className="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />The key is kept only in memory for this dashboard session.</p></section></main>
}

function Sidebar({ activeView, onSelect, mobileOpen }: { activeView: View; onSelect: (view: View) => void; mobileOpen: boolean }) {
  return (
    <aside className={cn("fixed inset-x-0 bottom-0 top-18 z-10 hidden border-b border-slate-800 bg-slate-950 px-4 py-4 lg:sticky lg:top-18 lg:block lg:h-[calc(100dvh-4.5rem)] lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r lg:px-5", mobileOpen && "block")} aria-label="Primary navigation">
      <nav className="space-y-1">
        {NAVIGATION.map(({ id, label, icon: Icon }) => <a key={id} href={`#${id}`} onClick={() => onSelect(id)} className={cn("flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300", activeView === id ? "bg-emerald-400/10 text-emerald-200" : "text-slate-400 hover:bg-slate-900 hover:text-slate-100")} aria-current={activeView === id ? "page" : undefined}>
          <Icon size={18} aria-hidden="true" />{label}
        </a>)}
      </nav>
      <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <LockKeyhole size={18} className="text-emerald-300" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-slate-200">Credentials stay local</p>
        <p className="mt-1 text-xs leading-5 text-slate-500">This console only stores your gateway key in this browser session.</p>
      </div>
    </aside>
  )
}

function AccountDialog({ keyValue, onLoginStarted, disabled }: { keyValue: string; onLoginStarted: (login: Login) => void; disabled: boolean }) {
  const [account, setAccount] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  async function startLogin() {
    setError("")
    setBusy(true)
    try {
      const response = await fetch(`/admin/accounts/${encodeURIComponent(account.trim())}/login/device`, { method: "POST", headers: { "X-Gateway-Key": keyValue } })
      if (!response.ok) {
        setError(await responseBody(response))
        return
      }
      const login = await response.json() as Login
      onLoginStarted(login)
    } catch {
      setError("The gateway could not be reached. Check the connection and try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog>
      <DialogTrigger asChild><Button disabled={disabled}><Plus size={17} aria-hidden="true" />Connect account</Button></DialogTrigger>
      <DialogContent>
        <DialogTitle className="text-lg font-semibold text-white">Connect a ChatGPT account</DialogTitle>
        <DialogDescription className="mt-2 pr-8 text-sm leading-6 text-slate-400">Name the account, then complete the secure OpenAI device login in your browser.</DialogDescription>
        <div className="mt-6 space-y-2">
          <label className="text-sm font-medium text-slate-200" htmlFor="account-id">Account identifier</label>
          <Input id="account-id" name="account-id" value={account} onChange={(event) => setAccount(event.target.value)} placeholder="For example, engineering-team…" autoComplete="off" spellCheck={false} aria-describedby="account-help" />
          <p id="account-help" className="text-xs leading-5 text-slate-500">Use letters, numbers, hyphens, or underscores. This name is only used inside the gateway.</p>
          {error && <p className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-200" role="alert">{error}</p>}
        </div>
        <Button className="mt-6 w-full" onClick={startLogin} disabled={!account.trim() || busy}>{busy ? <LoaderCircle size={17} className="animate-spin" aria-hidden="true" /> : <ArrowUpRight size={17} aria-hidden="true" />}{busy ? "Starting secure login…" : "Continue to OpenAI"}</Button>
      </DialogContent>
    </Dialog>
  )
}

function LoginPanel({ login, onCopy }: { login: Login; onCopy: (value: string) => void }) {
  if (login.status === "complete") return <div className="flex items-start gap-3 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm text-emerald-100"><Check className="mt-0.5 shrink-0" size={18} aria-hidden="true" /><div><p className="font-semibold">Account connected</p><p className="mt-1 text-emerald-100/75">{login.account_id} is now available to the gateway.</p></div></div>
  if (login.status === "failed") return <div className="flex items-start gap-3 rounded-2xl border border-rose-400/20 bg-rose-500/10 p-4 text-sm text-rose-100"><CircleAlert className="mt-0.5 shrink-0" size={18} aria-hidden="true" /><div><p className="font-semibold">Login did not complete</p><p className="mt-1 text-rose-100/75">{login.error ?? "Start a new secure login and try again."}</p></div></div>
  return <section className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-5" aria-live="polite">
    <div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-400 text-slate-950"><KeyRound size={19} aria-hidden="true" /></span><div><h2 className="font-semibold text-white">Finish in your browser</h2><p className="mt-1 text-sm leading-6 text-slate-400">Open the secure OpenAI page, then enter this one-time code.</p></div></div>
    <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center"><code className="min-w-0 flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-center text-lg font-semibold tracking-[0.2em] text-white">{login.user_code ?? "Preparing code…"}</code><Button variant="secondary" onClick={() => login.user_code && onCopy(login.user_code)} disabled={!login.user_code}><Copy size={17} aria-hidden="true" />Copy code</Button></div>
    <div className="mt-3 flex items-center gap-2 text-sm text-slate-400"><LoaderCircle size={15} className="animate-spin motion-reduce:animate-none text-emerald-300" aria-hidden="true" /><span>Waiting for OpenAI to confirm the sign-in…</span></div>
    {login.verification_url && <a className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-400 px-4 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950" href={login.verification_url} target="_blank" rel="noreferrer"><ArrowUpRight size={17} aria-hidden="true" />Open secure sign-in</a>}
  </section>
}

function Overview({ data, loading, onAddAccount }: { data: Dashboard | null; loading: boolean; onAddAccount: () => void }) {
  const activeAccounts = data?.gateways.filter((account) => account.active).length ?? 0
  return <div className="space-y-8">
    <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-emerald-300">Gateway health</p><h1 className="mt-2 text-balance text-3xl font-semibold tracking-tight text-white sm:text-4xl">Operate every account with confidence.</h1><p className="mt-3 max-w-2xl text-base leading-7 text-slate-400">Live account availability, model catalog, and secure browser sign-in—without exposing credentials in the dashboard.</p></div><StatusPill active={!loading}>{loading ? "Refreshing" : data ? "Live data" : "Awaiting key"}</StatusPill></section>
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard icon={KeyRound} label="Accounts" value={data?.gateways.length ?? "—"} detail={data ? `${activeAccounts} available now` : "Connect to load status"} /><MetricCard icon={Activity} label="Active" value={data ? activeAccounts : "—"} detail="Ready to receive traffic" /><MetricCard icon={Bot} label="Models" value={data?.models.length ?? "—"} detail="In the current catalog" /><MetricCard icon={ServerCog} label="Routing" value={data?.status.strategy ?? "—"} detail="Current selection strategy" /></section>
    {data?.model_error && <div className="flex gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100"><CircleAlert className="mt-0.5 shrink-0" size={18} aria-hidden="true" /><p><span className="font-semibold">Model catalog unavailable.</span> {data.model_error}</p></div>}
    {!data ? <EmptyState onAddAccount={onAddAccount} /> : <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]"><ProviderList providers={data.providers} /><ModelList models={data.models} /></section>}
  </div>
}

function ProviderList({ providers }: { providers: Provider[] }) {
  return <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80"><div className="flex items-center justify-between border-b border-slate-800 px-5 py-4"><div><h2 className="font-semibold text-white">Providers</h2><p className="mt-1 text-sm text-slate-500">Availability by upstream service</p></div><Database size={19} className="text-slate-500" aria-hidden="true" /></div><div className="divide-y divide-slate-800">{providers.length ? providers.map((provider) => <article key={provider.id} className="content-auto flex items-center justify-between gap-4 px-5 py-4"><div className="min-w-0"><p className="font-medium text-slate-200">{provider.id}</p><p className="mt-1 truncate text-sm text-slate-500">{provider.supported_endpoints.join(" · ") || "No endpoints reported"}</p></div><div className="shrink-0 text-right"><p className="text-sm font-semibold text-white tabular-nums">{provider.active_accounts}/{provider.accounts}</p><p className="mt-1 text-xs text-slate-500">active accounts</p></div></article>) : <p className="px-5 py-10 text-center text-sm text-slate-500">No providers configured.</p>}</div></section>
}

function ModelList({ models }: { models: Model[] }) {
  return <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80"><div className="flex items-center justify-between border-b border-slate-800 px-5 py-4"><div><h2 className="font-semibold text-white">Available models</h2><p className="mt-1 text-sm text-slate-500">Current gateway catalog</p></div><Bot size={19} className="text-slate-500" aria-hidden="true" /></div><div className="max-h-[27rem] divide-y divide-slate-800 overflow-y-auto">{models.length ? models.map((model) => <article key={model.id} className="content-auto flex items-center justify-between gap-4 px-5 py-4"><div className="min-w-0"><p className="truncate font-mono text-sm text-slate-200">{model.id}</p><p className="mt-1 text-xs text-slate-500">{providerFor(model)} · {model.supported_endpoints?.join(" · ") ?? "endpoints not reported"}</p></div><p className="shrink-0 text-right text-xs text-slate-500 tabular-nums">{model.context_window ?? model.max_context_window ? `${compactNumber(model.context_window ?? model.max_context_window)} ctx` : ""}</p></article>) : <p className="px-5 py-10 text-center text-sm text-slate-500">No models available.</p>}</div></section>
}

function Accounts({ data, keyValue, login, onLoginStarted, onCopy }: { data: Dashboard | null; keyValue: string; login: Login | null; onLoginStarted: (login: Login) => void; onCopy: (value: string) => void }) {
  return <div className="space-y-8"><section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-emerald-300">Identity & access</p><h1 className="mt-2 text-balance text-3xl font-semibold tracking-tight text-white sm:text-4xl">Connected accounts</h1><p className="mt-3 max-w-2xl text-base leading-7 text-slate-400">Use the OpenAI device flow to connect an account from any browser. Refreshed credentials are stored by the gateway, not this page.</p></div><AccountDialog keyValue={keyValue} onLoginStarted={onLoginStarted} disabled={!keyValue.trim()} /></section>{login && <LoginPanel login={login} onCopy={onCopy} />}<section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80"><div className="border-b border-slate-800 px-5 py-4"><h2 className="font-semibold text-white">Account inventory</h2><p className="mt-1 text-sm text-slate-500">The gateway chooses among active accounts using its configured routing strategy.</p></div>{data?.gateways.length ? <div className="divide-y divide-slate-800">{data.gateways.map((account) => <article key={account.id} className="content-auto flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium text-slate-100">{account.id}</p><p className="mt-1 text-sm text-slate-500">{account.provider} {account.plan ? `· ${account.plan}` : ""}</p></div><div className="flex items-center gap-5"><p className="text-right text-sm text-slate-500"><span className="block font-semibold text-slate-200 tabular-nums">{compactNumber(account.used_today)}</span>used today</p><StatusPill active={account.active}>{account.active ? "Active" : "Cooling down"}</StatusPill></div></article>)}</div> : <div className="px-5 py-12 text-center"><KeyRound className="mx-auto text-slate-600" size={24} aria-hidden="true" /><p className="mt-3 text-sm text-slate-400">No accounts connected yet.</p><p className="mt-1 text-xs text-slate-500">Enter your gateway API key, then start a secure connection above.</p></div>}</section></div>
}

export default function App() {
  const [keyValue, setKeyValue] = useState("")
  const [authenticated, setAuthenticated] = useState(false)
  const [data, setData] = useState<Dashboard | null>(null)
  const [message, setMessage] = useState("Enter a gateway API key to load live status.")
  const [loading, setLoading] = useState(false)
  const [activeView, setActiveView] = useState<View>(() => window.location.hash === "#accounts" ? "accounts" : "overview")
  const [mobileOpen, setMobileOpen] = useState(false)
  const [login, setLogin] = useState<Login | null>(null)

  const loadDashboard = useCallback(async (requestedKey: string) => {
    if (!requestedKey) { setMessage("Enter a gateway API key to load live status."); return }
    setLoading(true)
    setMessage("Refreshing live gateway data…")
    try {
      const response = await fetch("/dashboard/data", { headers: { "X-Gateway-Key": requestedKey } })
      if (!response.ok) { setMessage(await responseBody(response)); return }
      const dashboard = await response.json() as Dashboard
      setData(dashboard)
      setMessage("Live data is current.")
    } catch {
      setMessage("The gateway could not be reached. Check the connection and try again.")
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    const syncView = () => setActiveView(window.location.hash === "#accounts" ? "accounts" : "overview")
    window.addEventListener("hashchange", syncView)
    return () => window.removeEventListener("hashchange", syncView)
  }, [])

  const loginId = login?.id
  const loginStatus = login?.status

  useEffect(() => {
    if (!loginId || loginStatus !== "pending") return
    const interval = window.setInterval(async () => {
      try {
        const response = await fetch(`/admin/logins/${loginId}`, { headers: { "X-Gateway-Key": keyValue.trim() } })
        if (response.ok) {
          const next = await response.json() as Login
          setLogin(next)
          if (next.status === "complete") void loadDashboard(keyValue.trim())
        }
      } catch { /* Keep the current panel; the next poll will retry. */ }
    }, 3000)
    return () => window.clearInterval(interval)
  }, [keyValue, loadDashboard, loginId, loginStatus])

  function selectView(view: View) {
    if (window.location.hash !== `#${view}`) window.history.pushState(null, "", `#${view}`)
    setActiveView(view)
    setMobileOpen(false)
  }
  async function copy(value: string) { await navigator.clipboard.writeText(value); setMessage("Device code copied to your clipboard.") }
  function handleLoginStarted(next: Login) { setLogin(next); setActiveView("accounts"); setMessage("Complete the secure OpenAI sign-in in your browser.") }
  async function unlock(requestedKey: string) {
    setKeyValue(requestedKey)
    setAuthenticated(true)
    setMessage("Gateway key verified. Loading live data…")
    await loadDashboard(requestedKey)
  }
  function lock() {
    setKeyValue("")
    setData(null)
    setLogin(null)
    setAuthenticated(false)
    setMessage("Enter a gateway API key to load live status.")
  }

  if (!authenticated) return <AccessGate onVerified={unlock} />

  return <div className="min-h-dvh touch-manipulation overflow-x-hidden bg-slate-950 bg-[radial-gradient(ellipse_at_top,rgba(143,102,162,0.2),transparent_42rem)] text-slate-100"><Header loading={loading} onRefresh={() => loadDashboard(keyValue)} onLock={lock} menuOpen={mobileOpen} onToggleMenu={() => setMobileOpen((open) => !open)} /><div className="mx-auto flex max-w-[1600px]"><Sidebar activeView={activeView} onSelect={selectView} mobileOpen={mobileOpen} /><main id="main-content" className="min-w-0 flex-1 px-4 py-8 sm:px-6 lg:px-10 lg:py-10"><div className="mx-auto max-w-6xl"><p className={cn("mb-6 rounded-xl border px-4 py-3 text-sm", message.includes("could not") || message.includes("failed") ? "border-rose-400/20 bg-rose-500/10 text-rose-100" : "border-slate-800 bg-slate-900/60 text-slate-400")} role="status">{message}</p>{activeView === "overview" ? <Overview data={data} loading={loading} onAddAccount={() => selectView("accounts")} /> : <Accounts data={data} keyValue={keyValue} login={login} onLoginStarted={handleLoginStarted} onCopy={copy} />}</div></main></div></div>
}
