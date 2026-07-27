import { cn } from "../../lib/utils"

export function Skeleton({ className }: { className?: string }) {
  return <span className={cn("block animate-pulse rounded-md bg-inset motion-reduce:animate-none", className)} aria-hidden="true" />
}

/** Placeholder rows used while the first dashboard payload is in flight. */
export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="divide-y divide-line">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center justify-between gap-4 px-5 py-4">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-40 max-w-full" />
            <Skeleton className="h-3 w-24 max-w-full" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      ))}
    </div>
  )
}
