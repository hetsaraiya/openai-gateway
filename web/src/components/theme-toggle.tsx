import { Moon, Sun } from "lucide-react"

import type { Theme } from "../lib/theme"
import { Button } from "./ui/button"

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const nextTheme = theme === "dark" ? "light" : "dark"
  return (
    <Button variant="ghost" size="icon" onClick={onToggle} aria-label={`Switch to ${nextTheme} theme`} title={`Switch to ${nextTheme} theme`}>
      {theme === "dark" ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
    </Button>
  )
}
