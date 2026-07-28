import { LoaderCircle, Trash2 } from "lucide-react"
import { useState } from "react"

import type { Gateway } from "../lib/api"
import { Button } from "./ui/button"
import { Dialog, DialogClose, DialogContent, DialogHeader, DialogTrigger } from "./ui/dialog"

export function DeleteAccountDialog({
  account,
  onDelete,
}: {
  account: Gateway
  onDelete: (accountId: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState("")

  function handleOpenChange(nextOpen: boolean) {
    if (deleting) return
    setOpen(nextOpen)
    if (!nextOpen) setError("")
  }

  async function confirmDelete() {
    setDeleting(true)
    setError("")
    try {
      await onDelete(account.id)
      setOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The account could not be deleted. Try again.")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-subtle hover:bg-danger-soft hover:text-danger"
          aria-label={`Delete ${account.id}`}
        >
          <Trash2 size={15} aria-hidden="true" />
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader
          title={`Delete ${account.id}?`}
          description="This removes the account from routing and permanently deletes its stored credential file. You will need to connect it again to restore access."
        />

        <div className="mt-5 rounded-lg border border-danger/20 bg-danger-soft px-3.5 py-3">
          <p className="text-sm font-medium text-danger">This action cannot be undone.</p>
          <p className="mt-1 text-[13px] leading-5 text-muted">
            Other configured accounts will continue handling gateway traffic.
          </p>
        </div>

        {error && (
          <p className="mt-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}

        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <DialogClose asChild>
            <Button variant="secondary" disabled={deleting}>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="danger" onClick={confirmDelete} disabled={deleting}>
            {deleting ? (
              <LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <Trash2 size={16} aria-hidden="true" />
            )}
            {deleting ? "Deleting account…" : "Delete account"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
