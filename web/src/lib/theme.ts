import { useCallback, useEffect, useState } from "react"

export type Theme = "light" | "dark"

const STORAGE_KEY = "gateway-theme"

/** Light is the designed default; the OS preference no longer overrides it. */
const DEFAULT_THEME: Theme = "light"

function storedTheme(): Theme | null {
  const value = localStorage.getItem(STORAGE_KEY)
  return value === "light" || value === "dark" ? value : null
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark")
}

export function useTheme() {
  // Dark is opt-in: it lasts only as long as the reader's stored choice.
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? DEFAULT_THEME)

  useEffect(() => {
    apply(theme)
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark"
      localStorage.setItem(STORAGE_KEY, next)
      return next
    })
  }, [])

  return { theme, toggle }
}
