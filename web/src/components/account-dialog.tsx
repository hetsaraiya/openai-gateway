import { ArrowUpRight, LoaderCircle, Plus } from "lucide-react"
import { useState } from "react"

import { ApiError, startDeviceLogin, type Login } from "../lib/api"
import { Button } from "./ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTrigger } from "./ui/dialog"
import { Field, Input } from "./ui/input"

const VALID_ID = /^[A-Za-z0-9_-]+$/

export function AccountDialog({
  gatewayKey,
  disabled,
  onLoginStarted,
}: {
  gatewayKey: string
  disabled: boolean
  onLoginStarted: (login: Login) => void
}) {
  const [open, setOpen] = useState(false)
  const [account, setAccount] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const trimmed = account.trim()
  const invalid = trimmed.length > 0 && !VALID_ID.test(trimmed)

  function reset(next: boolean) {
    setOpen(next)
    if (!next) {
      setAccount("")
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
      onLoginStarted(await startDeviceLogin(trimmed, gatewayKey))
      reset(false)
    } catch (cause) {
      setError((cause as ApiError).message)
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        <Button disabled={disabled}>
          <Plus size={16} aria-hidden="true" />
          Connect account
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader
          title="Connect a ChatGPT account"
          description="Name the account, then finish the OpenAI device sign-in in your browser."
        />
        <form className="mt-6" onSubmit={submit} noValidate>
          <Field
            label="Account identifier"
            htmlFor="account-id"
            hint="Letters, numbers, hyphens, and underscores. Used only inside the gateway."
            error={error || (invalid ? "Use only letters, numbers, hyphens, and underscores." : "")}
          >
            <Input
              id="account-id"
              name="account-id"
              value={account}
              onChange={(event) => setAccount(event.target.value)}
              placeholder="engineering-team"
              autoComplete="off"
              spellCheck={false}
              autoFocus
              aria-describedby="account-id-hint"
              aria-invalid={invalid || Boolean(error) ? true : undefined}
            />
          </Field>

          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => reset(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || invalid || busy}>
              {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> : <ArrowUpRight size={16} aria-hidden="true" />}
              {busy ? "Starting…" : "Continue to OpenAI"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
