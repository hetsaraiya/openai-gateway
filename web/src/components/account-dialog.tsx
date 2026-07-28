import { ArrowUpRight, KeyRound, LoaderCircle, Plus } from "lucide-react"
import { type ReactNode, useState } from "react"

import { addOpenCodeKey, addXAIKey, ApiError, providerLabel, startDeviceLogin, type Login } from "../lib/api"
import { Button } from "./ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTrigger } from "./ui/dialog"
import { Field, Input } from "./ui/input"

const VALID_ID = /^[A-Za-z0-9._-]+$/

export function AccountDialog({
  gatewayKey,
  disabled,
  provider = "codex",
  trigger,
  onLoginStarted,
  onAccountAdded,
}: {
  gatewayKey: string
  disabled: boolean
  provider?: string
  trigger?: ReactNode
  onLoginStarted: (login: Login) => void
  onAccountAdded?: (accountId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [account, setAccount] = useState("")
  const [label, setLabel] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const trimmed = account.trim()
  const isApiKeyProvider = provider === "opencode-go" || provider === "xai"
  const invalid = trimmed.length > 0 && !VALID_ID.test(trimmed)

  function reset(next: boolean) {
    setOpen(next)
    if (!next) {
      setAccount("")
      setLabel("")
      setApiKey("")
      setError("")
      setBusy(false)
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (invalid) return
    setError("")
    setBusy(true)
    try {
      if (isApiKeyProvider) {
        const addKey = provider === "xai" ? addXAIKey : addOpenCodeKey
        const result = await addKey(
          {
            api_key: apiKey.trim(),
            ...(trimmed ? { identifier: trimmed } : {}),
            ...(label.trim() ? { label: label.trim() } : {}),
          },
          gatewayKey,
        )
        onAccountAdded?.(result.id)
      } else {
        onLoginStarted(await startDeviceLogin(trimmed, gatewayKey))
      }
      reset(false)
    } catch (cause) {
      setError((cause as ApiError).message)
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button disabled={disabled}>
            <Plus size={16} aria-hidden="true" />
            Add account
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader
          title={`Add ${providerLabel(provider)} account`}
          description={
            isApiKeyProvider
              ? `Add an ${providerLabel(provider)} API key. It is stored securely by the gateway.`
              : "Name the account, then finish the secure OpenAI device sign-in in your browser."
          }
        />
        <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
          {isApiKeyProvider && (
            <Field
              label={provider === "xai" ? "Inference API key" : "Subscription API key"}
              htmlFor="provider-api-key"
              hint="The key is sent directly to your gateway and is never saved in this browser."
            >
              <Input
                id="provider-api-key"
                name="provider-api-key"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={provider === "xai" ? "xai-…" : "Enter API key"}
                autoComplete="off"
                spellCheck={false}
                autoFocus
              />
            </Field>
          )}

          <Field
            label="Account identifier"
            htmlFor="account-id"
            hint={
              isApiKeyProvider
                ? "Optional. Leave blank to generate a unique identifier."
                : "Letters, numbers, periods, hyphens, and underscores."
            }
            error={error || (invalid ? "Use only letters, numbers, periods, hyphens, and underscores." : "")}
          >
            <Input
              id="account-id"
              name="account-id"
              value={account}
              onChange={(event) => setAccount(event.target.value)}
              placeholder="engineering-team"
              autoComplete="off"
              spellCheck={false}
              autoFocus={!isApiKeyProvider}
              aria-describedby="account-id-hint"
              aria-invalid={invalid || Boolean(error) ? true : undefined}
            />
          </Field>

          {isApiKeyProvider && (
            <Field label="Display label" htmlFor="account-label" hint="Optional. Helps your team recognize this key.">
              <Input
                id="account-label"
                name="account-label"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="Production subscription"
                autoComplete="off"
              />
            </Field>
          )}

          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => reset(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={invalid || busy || (isApiKeyProvider ? !apiKey.trim() : !trimmed)}>
              {busy ? (
                <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
              ) : isApiKeyProvider ? (
                <KeyRound size={16} aria-hidden="true" />
              ) : (
                <ArrowUpRight size={16} aria-hidden="true" />
              )}
              {busy ? "Adding…" : isApiKeyProvider ? "Add API key" : "Continue to OpenAI"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
