import { useEffect, useRef, type ReactNode } from "react"

import { cn } from "../../lib/utils"

/**
 * Fades its children up the first time they scroll into view. The hidden state
 * lives in CSS behind `prefers-reduced-motion: no-preference`, so readers who
 * opt out — and anyone without JavaScript — see the content immediately.
 */
export function Reveal({ as: Tag = "section", className, children, ...rest }: { as?: "section" | "div"; className?: string; children: ReactNode } & Record<string, unknown>) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const show = () => node.setAttribute("data-shown", "true")
    if (typeof IntersectionObserver === "undefined") {
      show()
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          show()
          observer.disconnect()
        }
      },
      { threshold: 0.06, rootMargin: "0px 0px -6% 0px" },
    )

    // Anything already on screen at mount reveals without waiting for a scroll.
    if (node.getBoundingClientRect().top < window.innerHeight * 0.92) show()
    else observer.observe(node)

    return () => observer.disconnect()
  }, [])

  return (
    <Tag ref={ref as never} className={cn("reveal", className)} {...rest}>
      {children}
    </Tag>
  )
}
