import { useCallback, useEffect, useState } from "react"

export type Theme = "light" | "dark"

const STORAGE_KEY = "gateway-theme"

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function storedTheme(): Theme | null {
  const value = localStorage.getItem(STORAGE_KEY)
  return value === "light" || value === "dark" ? value : null
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark")
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme())

  useEffect(() => {
    apply(theme)
  }, [theme])

  // Follow the OS only while the reader has not made an explicit choice.
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const sync = () => {
      if (!storedTheme()) setTheme(media.matches ? "dark" : "light")
    }
    media.addEventListener("change", sync)
    return () => media.removeEventListener("change", sync)
  }, [])

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark"
      localStorage.setItem(STORAGE_KEY, next)
      return next
    })
  }, [])

  return { theme, toggle }
}
