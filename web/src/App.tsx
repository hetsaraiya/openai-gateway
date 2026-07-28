import { useCallback, useEffect, useRef, useState } from "react"

import { AccessGate } from "./components/access-gate"
import { Sidebar, TopBar } from "./components/app-shell"
import { Callout } from "./components/ui/callout"
import { ToastRegion } from "./components/ui/toast"
import { ApiError, deleteAccount, fetchDashboard, fetchLogin, type Dashboard, type Login } from "./lib/api"
import { viewFromHash, type View } from "./lib/navigation"
import { clearSession, loadSession, saveSession } from "./lib/session"
import { useTheme } from "./lib/theme"
import { useToasts } from "./lib/use-toasts"
import { relativeTime } from "./lib/utils"
import { Accounts } from "./views/accounts"
import { Overview } from "./views/overview"

const LOGIN_POLL_MS = 3000
const AUTO_REFRESH_MS = 60_000
const CLOCK_TICK_MS = 30_000

export default function App() {
  const { theme, toggle: toggleTheme } = useTheme()
  const { toasts, push, dismiss } = useToasts()

  const [gatewayKey, setGatewayKey] = useState(() => loadSession() ?? "")
  const [authenticated, setAuthenticated] = useState(() => Boolean(loadSession()))
  const [data, setData] = useState<Dashboard | null>(null)
  const [sessionNotice, setSessionNotice] = useState("")
  const [loadError, setLoadError] = useState("")
  const [loading, setLoading] = useState(false)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [now, setNow] = useState(() => new Date())
  const [activeView, setActiveView] = useState<View>(viewFromHash)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [login, setLogin] = useState<Login | null>(null)

  // `push` is stable, but reading it through a ref keeps loadDashboard's identity
  // fixed so the polling effects below don't resubscribe on every toast.
  const pushRef = useRef(push)
  pushRef.current = push

  // Forgets the key everywhere — memory and storage — and returns to the gate.
  const endSession = useCallback((notice = "") => {
    clearSession()
    setGatewayKey("")
    setAuthenticated(false)
    setData(null)
    setLogin(null)
    setLoadError("")
    setUpdatedAt(null)
    setMobileOpen(false)
    setSessionNotice(notice)
  }, [])

  const loadDashboard = useCallback(async (key: string, options?: { silent?: boolean }) => {
    if (!key) return
    if (!options?.silent) setLoading(true)
    try {
      setData(await fetchDashboard(key))
      setLoadError("")
      setUpdatedAt(new Date())
      // Each authenticated round trip pushes the expiry back out.
      saveSession(key)
    } catch (cause) {
      const failure = cause as ApiError
      // A stored key the gateway no longer accepts is worse than no key at all:
      // drop it and ask again rather than leaving a console that cannot load.
      if (failure.status === 401) {
        endSession("Your saved gateway key is no longer accepted. Enter it again.")
        return
      }
      setLoadError(failure.message)
      if (!options?.silent) pushRef.current(failure.message, "danger")
    } finally {
      if (!options?.silent) setLoading(false)
    }
  }, [endSession])

  // Restores a stored session on first paint; the load also revalidates the key.
  useEffect(() => {
    const stored = loadSession()
    if (stored) void loadDashboard(stored)
  }, [loadDashboard])

  useEffect(() => {
    const syncView = () => setActiveView(viewFromHash())
    window.addEventListener("hashchange", syncView)
    return () => window.removeEventListener("hashchange", syncView)
  }, [])

  // Keeps the "updated 4m ago" label honest without a re-render every second.
  useEffect(() => {
    if (!authenticated) return
    const tick = window.setInterval(() => setNow(new Date()), CLOCK_TICK_MS)
    return () => window.clearInterval(tick)
  }, [authenticated])

  useEffect(() => {
    if (!authenticated || !gatewayKey) return
    const refresh = window.setInterval(() => void loadDashboard(gatewayKey, { silent: true }), AUTO_REFRESH_MS)
    return () => window.clearInterval(refresh)
  }, [authenticated, gatewayKey, loadDashboard])

  const loginId = login?.id
  const loginStatus = login?.status

  useEffect(() => {
    if (!loginId || (loginStatus !== "pending" && loginStatus !== "starting")) return
    const poll = window.setInterval(async () => {
      try {
        const next = await fetchLogin(loginId, gatewayKey)
        setLogin(next)
        if (next.status === "complete") {
          pushRef.current(`${next.account_id} connected.`, "success")
          void loadDashboard(gatewayKey, { silent: true })
        }
        if (next.status === "failed") pushRef.current(next.error ?? "The device sign-in failed.", "danger")
      } catch {
        // Keep the panel as-is; the next poll retries.
      }
    }, LOGIN_POLL_MS)
    return () => window.clearInterval(poll)
  }, [gatewayKey, loadDashboard, loginId, loginStatus])

  function selectView(view: View) {
    if (window.location.hash !== `#${view}`) window.history.pushState(null, "", `#${view}`)
    setActiveView(view)
    setMobileOpen(false)
  }

  async function copyCode(value: string) {
    try {
      await navigator.clipboard.writeText(value)
      push("Device code copied to your clipboard.", "success")
    } catch {
      push("Copying failed — select the code and copy it manually.", "danger")
    }
  }

  function handleLoginStarted(next: Login) {
    setLogin(next)
    selectView("accounts")
  }

  async function handleDeleteAccount(accountId: string) {
    await deleteAccount(accountId, gatewayKey)
    await loadDashboard(gatewayKey, { silent: true })
    push(`${accountId} deleted.`, "success")
  }

  async function unlock(key: string) {
    saveSession(key)
    setGatewayKey(key)
    setAuthenticated(true)
    setSessionNotice("")
    await loadDashboard(key)
  }

  if (!authenticated) {
    return <AccessGate theme={theme} notice={sessionNotice} onToggleTheme={toggleTheme} onVerified={unlock} />
  }

  return (
    <div className="min-h-dvh">
      <Sidebar
        activeView={activeView}
        onSelect={selectView}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onLock={() => endSession()}
      />

      <div className="lg:pl-64">
        <TopBar
          activeView={activeView}
          loading={loading}
          updatedLabel={updatedAt ? `Updated ${relativeTime(updatedAt, now)}` : null}
          theme={theme}
          onToggleTheme={toggleTheme}
          onRefresh={() => void loadDashboard(gatewayKey)}
          onOpenMobile={() => setMobileOpen(true)}
        />

        <main id="main-content" className="px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto max-w-6xl space-y-6">
            {loadError && (
              <Callout tone="danger" title="Could not load gateway data">
                {loadError}
              </Callout>
            )}

            {activeView === "overview" ? (
              <Overview data={data} loading={loading} onAddAccount={() => selectView("accounts")} />
            ) : (
              <Accounts
                data={data}
                loading={loading}
                gatewayKey={gatewayKey}
                login={login}
                onLoginStarted={handleLoginStarted}
                onCopy={copyCode}
                onDelete={handleDeleteAccount}
              />
            )}
          </div>
        </main>
      </div>

      <ToastRegion toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}
