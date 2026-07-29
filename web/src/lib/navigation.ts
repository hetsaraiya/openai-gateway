import { KeyRound, LayoutDashboard, type LucideIcon } from "lucide-react"

export type View = "overview" | "accounts"

export const NAVIGATION: { id: View; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Model catalog", icon: LayoutDashboard },
  { id: "accounts", label: "Accounts", icon: KeyRound },
]

function hashView(): View | null {
  const hash = window.location.hash.replace("#", "")
  return NAVIGATION.some((item) => item.id === hash) ? (hash as View) : null
}

export function viewFromHash(): View {
  return hashView() ?? "overview"
}

/**
 * The same bundle serves the public landing page and the console. A console
 * view in the hash, or the /dashboard path the gateway has always exposed,
 * means the reader asked for the console rather than the marketing page.
 */
export function consoleRequested(): boolean {
  return hashView() !== null || window.location.pathname.replace(/\/+$/, "") === "/dashboard"
}
