import type { ReactNode } from "react"

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="tooltip-wrapper">
      {children}
      <span className="tooltip-text" role="tooltip">{text}</span>
    </span>
  )
}
