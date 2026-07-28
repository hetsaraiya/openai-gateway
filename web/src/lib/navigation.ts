import { KeyRound, LayoutDashboard, type LucideIcon } from "lucide-react"

export type View = "overview" | "accounts"

export const NAVIGATION: { id: View; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Model catalog", icon: LayoutDashboard },
  { id: "accounts", label: "Accounts", icon: KeyRound },
]

export function viewFromHash(): View {
  const hash = window.location.hash.replace("#", "")
  return NAVIGATION.some((item) => item.id === hash) ? (hash as View) : "overview"
}
