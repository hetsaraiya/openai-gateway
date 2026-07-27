import gatewayMark from "../assets/gateway-mark.png"
import { cn } from "../lib/utils"

export function BrandMark({ className, size = 36 }: { className?: string; size?: number }) {
  return (
    <span
      className={cn("grid shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-inset", className)}
      style={{ width: size, height: size }}
    >
      <img src={gatewayMark} width={size} height={size} alt="" aria-hidden="true" className="size-full object-cover" />
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
