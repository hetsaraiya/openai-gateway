import { cva, type VariantProps } from "class-variance-authority"
import type { ButtonHTMLAttributes } from "react"

import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-medium whitespace-nowrap transition-[background-color,color,border-color,box-shadow,opacity] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:pointer-events-none disabled:opacity-45 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-fg shadow-panel hover:bg-accent-hover",
        secondary: "border border-line bg-surface text-ink shadow-panel hover:border-line-strong hover:bg-elevated",
        ghost: "text-muted hover:bg-inset hover:text-ink",
        subtle: "bg-accent-soft text-accent-text hover:brightness-110",
        danger: "border border-danger/25 bg-danger-soft text-danger hover:border-danger/40",
      },
      size: {
        sm: "h-8 px-3 text-[13px]",
        default: "h-10 px-4",
        lg: "h-11 px-5",
        icon: "size-10",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
)

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
