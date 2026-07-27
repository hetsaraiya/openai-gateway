export type Gateway = {
  id: string
  provider: string
  plan?: string
  active: boolean
  used_today?: number
}

export type Model = {
  id: string
  gateway?: string
  context_window?: number
  max_context_window?: number
  supported_endpoints?: string[]
}

export type Provider = {
  id: string
  accounts: number
  active_accounts: number
  supported_endpoints: string[]
}

export type Dashboard = {
  status: { strategy: string }
  gateways: Gateway[]
  models: Model[]
  providers: Provider[]
  model_error?: string | null
}

export type LoginStatus = "starting" | "pending" | "complete" | "failed"

export type Login = {
  id: string
  account_id: string
  status: LoginStatus
  verification_url?: string
  user_code?: string
  error?: string
}

const UNREACHABLE = "The gateway could not be reached. Check your connection and try again."

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

/** Pulls the message out of the gateway's `{ error: { message } }` envelope. */
async function errorFrom(response: Response) {
  const body: unknown = await response.json().catch(() => null)
  if (body && typeof body === "object" && "error" in body) {
    const error = (body as { error?: { message?: string } }).error
    if (error?.message) return new ApiError(error.message, response.status)
  }
  return new ApiError(`Request failed (${response.status}).`, response.status)
}

async function request<T>(path: string, key: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { ...init, headers: { ...init?.headers, "X-Gateway-Key": key } })
  } catch {
    throw new ApiError(UNREACHABLE, 0)
  }
  if (!response.ok) throw await errorFrom(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function checkKey(key: string) {
  return request<void>("/dashboard/auth/check", key, { method: "POST" })
}

export function fetchDashboard(key: string) {
  return request<Dashboard>("/dashboard/data", key)
}

export function startDeviceLogin(accountId: string, key: string) {
  return request<Login>(`/admin/accounts/${encodeURIComponent(accountId)}/login/device`, key, { method: "POST" })
}

export function fetchLogin(loginId: string, key: string) {
  return request<Login>(`/admin/logins/${encodeURIComponent(loginId)}`, key)
}

export function providerFor(model: Model) {
  return model.gateway ?? (model.id.startsWith("opencode-go/") ? "opencode-go" : "codex")
}

export function contextWindow(model: Model) {
  return model.context_window ?? model.max_context_window
}
