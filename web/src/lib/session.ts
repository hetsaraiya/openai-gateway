/**
 * Keeps the gateway key across reloads so the console isn't re-authenticated on
 * every refresh. Stored with an explicit expiry; the window slides forward on
 * each successful authenticated request, so it lapses after two days of disuse.
 */
const STORAGE_KEY = "gateway-session"

export const SESSION_DAYS = 2
const TTL_MS = SESSION_DAYS * 24 * 60 * 60 * 1000

type StoredSession = { key: string; expiresAt: number }

function read(): StoredSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== "object" || parsed === null) return null
    const { key, expiresAt } = parsed as Partial<StoredSession>
    if (typeof key !== "string" || !key || typeof expiresAt !== "number") return null
    return { key, expiresAt }
  } catch {
    // Blocked storage or a malformed entry: fall back to asking for the key.
    return null
  }
}

export function loadSession(): string | null {
  const stored = read()
  if (!stored) return null
  if (Date.now() >= stored.expiresAt) {
    clearSession()
    return null
  }
  return stored.key
}

export function saveSession(key: string) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ key, expiresAt: Date.now() + TTL_MS }))
  } catch {
    // Storage can be unavailable in private windows; the key still works for this tab.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing to clear.
  }
}
