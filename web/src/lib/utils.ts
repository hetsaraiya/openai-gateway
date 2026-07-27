import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function compactNumber(value: number | undefined) {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value ?? 0)
}

export function fullNumber(value: number | undefined) {
  return new Intl.NumberFormat().format(value ?? 0)
}

export function timeOfDay(value: Date) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(value)
}

/** "just now" / "4m ago" — kept short so it can sit inline next to a refresh button. */
export function relativeTime(from: Date, now: Date) {
  const seconds = Math.max(0, Math.round((now.getTime() - from.getTime()) / 1000))
  if (seconds < 45) return "just now"
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return timeOfDay(from)
}
