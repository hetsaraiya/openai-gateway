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
  owned_by?: string
  display_name?: string
  description?: string
  context_window?: number
  max_context_window?: number
  supported_endpoints?: string[]
  input_modalities?: string[]
  output_modalities?: string[]
  supported_in_api?: boolean
  prompt_caching?: boolean
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
  provider: "codex" | "xai" | "cursor"
  status: LoginStatus
  verification_url?: string
  user_code?: string
  error?: string
}

export type ChatMessage = {
  role: "user" | "assistant"
  content: string
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
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause
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

export function startProviderDeviceLogin(provider: "xai" | "cursor", accountId: string, key: string) {
  return request<Login>(
    `/admin/providers/${provider}/accounts/${encodeURIComponent(accountId)}/login/device`,
    key,
    { method: "POST" },
  )
}

export function addProviderKey(
  provider: "opencode-go" | "gemini",
  payload: { api_key: string; identifier?: string; label?: string },
  key: string,
) {
  return request<{ status: "ok"; id: string; label?: string; replaced: boolean; provider: string }>(
    `/v1/admin/${provider}/keys`,
    key,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  )
}

export async function createChatCompletion(
  model: string,
  messages: ChatMessage[],
  key: string,
  signal?: AbortSignal,
) {
  const result = await request<{
    choices?: { message?: { content?: string | { type?: string; text?: string }[] } }[]
  }>("/v1/chat/completions", key, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, messages, stream: false }),
    signal,
  })
  const content = result.choices?.[0]?.message?.content
  if (typeof content === "string") return content
  if (Array.isArray(content)) return content.map((part) => part.text ?? "").join("")
  throw new ApiError("The model returned an empty response.", 502)
}

export function fetchLogin(loginId: string, key: string) {
  return request<Login>(`/admin/logins/${encodeURIComponent(loginId)}`, key)
}

export function deleteAccount(accountId: string, key: string) {
  return request<{ status: "ok"; account: string; deleted: true }>(
    `/admin/accounts/${encodeURIComponent(accountId)}`,
    key,
    { method: "DELETE" },
  )
}

export function testAccount(accountId: string, key: string) {
  return request<{ status: "ok"; account: string; provider: string; latency_ms: number }>(
    `/admin/accounts/${encodeURIComponent(accountId)}/test`,
    key,
    { method: "POST" },
  )
}

export function providerFor(model: Model) {
  if (model.gateway) return model.gateway
  if (model.id.startsWith("opencode-go/")) return "opencode-go"
  if (model.id.startsWith("xai/")) return "xai"
  if (model.id.startsWith("gemini/")) return "gemini"
  return "codex"
}

export function providerLabel(provider: string) {
  if (provider === "codex") return "OpenAI"
  if (provider === "opencode-go") return "OpenCode Go"
  if (provider === "xai") return "xAI"
  if (provider === "cursor") return "Cursor"
  if (provider === "gemini") return "Google Gemini"
  return provider
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ")
}

export function contextWindow(model: Model) {
  return model.context_window ?? model.max_context_window
}
