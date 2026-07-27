/**
 * The gateway mark: many streams converging through an open ring and leaving as
 * one. Drawn on the same 24-unit grid and stroke weight as the console's icons,
 * and inked with `currentColor` so it follows the active theme.
 */
export function GatewayMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4.45 6.4a9.4 9.4 0 0 1 15.1 0" />
      <path d="M4.45 17.6a9.4 9.4 0 0 0 15.1 0" />
      <path d="M1.7 9.2h6.5l3.4 2.8" />
      <path d="M1.7 14.8h6.5l3.4-2.8" />
      <path d="M1.7 12h18" />
      <path d="m18.1 8.7 3.3 3.3-3.3 3.3" />
    </svg>
  )
}
