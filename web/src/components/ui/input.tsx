import type { InputHTMLAttributes, ReactNode } from "react"

import { cn } from "../../lib/utils"

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink shadow-panel outline-none transition-[border-color,box-shadow] duration-150",
        "placeholder:text-subtle hover:border-line-strong",
        "focus:border-accent focus:ring-2 focus:ring-accent/25",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}

/** Label + control + hint/error, so forms stay consistent without repeating markup. */
export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: string
  htmlFor: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-hint`} role="alert" className="text-[13px] leading-5 text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${htmlFor}-hint`} className="text-[13px] leading-5 text-subtle">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
