import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import type { ReactNode } from "react"

import { cn } from "../../lib/utils"

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export function DialogContent({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 overscroll-contain bg-canvas/70 backdrop-blur-[3px] data-[state=open]:animate-overlay-in" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overscroll-contain",
          "rounded-xl border border-line bg-surface p-6 shadow-float outline-none data-[state=open]:animate-panel-in",
          className,
        )}
      >
        {children}
        <DialogPrimitive.Close
          className="absolute right-4 top-4 inline-flex size-8 items-center justify-center rounded-md text-subtle transition-colors hover:bg-inset hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-label="Close dialog"
        >
          <X size={16} aria-hidden="true" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export function DialogHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="pr-8">
      <DialogPrimitive.Title className="text-base font-semibold tracking-[-0.01em] text-ink">{title}</DialogPrimitive.Title>
      <DialogPrimitive.Description className="mt-1.5 text-sm leading-6 text-muted">{description}</DialogPrimitive.Description>
    </div>
  )
}
