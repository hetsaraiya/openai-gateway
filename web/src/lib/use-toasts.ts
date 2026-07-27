import { useCallback, useEffect, useRef, useState } from "react"

export type ToastTone = "info" | "success" | "danger"
export type Toast = { id: number; tone: ToastTone; message: string }

const DISMISS_AFTER = 4500
const MAX_VISIBLE = 3

/** Transient feedback: one queue, auto-dismissed, timers cleared on unmount. */
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<number[]>([])
  const nextId = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = nextId.current++
      setToasts((current) => [...current, { id, tone, message }].slice(-MAX_VISIBLE))
      timers.current.push(window.setTimeout(() => dismiss(id), DISMISS_AFTER))
    },
    [dismiss],
  )

  useEffect(() => {
    const pending = timers.current
    return () => pending.forEach(window.clearTimeout)
  }, [])

  return { toasts, push, dismiss }
}
