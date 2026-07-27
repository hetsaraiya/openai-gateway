import { CircleAlert, CircleCheck, Info, X } from "lucide-react"

import type { Toast, ToastTone } from "../../lib/use-toasts"
import { cn } from "../../lib/utils"

const ICONS: Record<ToastTone, { icon: typeof Info; color: string }> = {
  info: { icon: Info, color: "text-accent-text" },
  success: { icon: CircleCheck, color: "text-success" },
  danger: { icon: CircleAlert, color: "text-danger" },
}

export function ToastRegion({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div
      className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col items-end gap-2 sm:bottom-6 sm:left-auto sm:right-6 sm:max-w-sm"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((toast) => {
        const { icon: Icon, color } = ICONS[toast.tone]
        return (
          <div
            key={toast.id}
            className="pointer-events-auto flex w-full animate-toast-in items-start gap-3 rounded-xl border border-line bg-elevated px-4 py-3 shadow-float"
          >
            <Icon size={17} className={cn("mt-px shrink-0", color)} aria-hidden="true" />
            <p className="min-w-0 flex-1 text-[13px] leading-5 text-ink">{toast.message}</p>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="-mr-1 -mt-0.5 shrink-0 rounded-md p-1 text-subtle transition-colors hover:bg-inset hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              aria-label="Dismiss notification"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
