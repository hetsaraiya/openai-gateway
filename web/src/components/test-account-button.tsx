import { Check, CircleAlert, LoaderCircle, X } from "lucide-react"
import { useState } from "react"

import { cn } from "../lib/utils"
import { Button } from "./ui/button"

type TestState = "idle" | "testing" | "success" | "failure"

export function TestAccountButton({
  accountId,
  onTest,
}: {
  accountId: string
  onTest: (accountId: string) => Promise<void>
}) {
  const [state, setState] = useState<TestState>("idle")

  async function test() {
    setState("testing")
    try {
      await onTest(accountId)
      setState("success")
    } catch {
      setState("failure")
    }
  }

  const label =
    state === "testing"
      ? `Testing ${accountId}`
      : state === "success"
        ? `${accountId} passed its connection test`
        : state === "failure"
          ? `${accountId} failed its connection test`
          : `Test ${accountId}`

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={() => void test()}
      disabled={state === "testing"}
      className={cn(
        "text-subtle",
        state === "success" && "text-success hover:bg-success-soft hover:text-success",
        state === "failure" && "text-danger hover:bg-danger-soft hover:text-danger",
        state === "idle" && "hover:bg-warning-soft hover:text-warning",
      )}
      aria-label={label}
      title={label}
    >
      {state === "testing" ? (
        <LoaderCircle size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
      ) : state === "success" ? (
        <Check size={15} aria-hidden="true" />
      ) : state === "failure" ? (
        <X size={15} aria-hidden="true" />
      ) : (
        <CircleAlert size={15} aria-hidden="true" />
      )}
    </Button>
  )
}
