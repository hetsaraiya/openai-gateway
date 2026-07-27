import { cn } from "../lib/utils"
import { GatewayMark } from "./gateway-mark"

export function BrandMark({ className, size = 36 }: { className?: string; size?: number }) {
  return (
    <span
      className={cn("grid shrink-0 place-items-center rounded-lg border border-line bg-inset text-accent", className)}
      style={{ width: size, height: size }}
    >
      <GatewayMark size={Math.round(size * 0.74)} />
    </span>
  )
}

export function Brand({ subtitle = "Operations console" }: { subtitle?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <BrandMark />
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold tracking-[-0.01em] text-ink">OpenAI Gateway</p>
        <p className="truncate text-[12px] text-subtle">{subtitle}</p>
      </div>
    </div>
  )
}
