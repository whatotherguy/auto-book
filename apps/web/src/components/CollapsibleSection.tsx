import { PropsWithChildren, ReactNode, useEffect, useId, useState } from "react"

export function CollapsibleSection({
  title,
  subtitle,
  actions,
  defaultCollapsed = false,
  storageKey,
  className = "",
  children
}: PropsWithChildren<{
  title: string
  subtitle?: string
  actions?: ReactNode
  defaultCollapsed?: boolean
  storageKey?: string
  className?: string
}>) {
  const panelId = useId()
  const [collapsed, setCollapsed] = useState(() => {
    if (!storageKey || typeof window === "undefined") {
      return defaultCollapsed
    }

    const savedValue = window.localStorage.getItem(storageKey)
    if (savedValue == null) {
      return defaultCollapsed
    }

    return savedValue === "true"
  })

  useEffect(() => {
    if (!storageKey) {
      return
    }

    window.localStorage.setItem(storageKey, String(collapsed))
  }, [collapsed, storageKey])

  return (
    <div className={`card collapsible-card ${collapsed ? "collapsed" : ""} ${className}`.trim()}>
      <div className="collapsible-header">
        <button
          type="button"
          className="collapsible-toggle"
          onClick={() => setCollapsed((current) => !current)}
          aria-expanded={!collapsed}
          aria-controls={panelId}
        >
          <span className="collapsible-toggle-text">
            <span className="collapsible-title">{title}</span>
            {subtitle ? <span className="collapsible-subtitle">{subtitle}</span> : null}
          </span>
          <span className="collapsible-chevron" aria-hidden="true">
            {collapsed ? "+" : "-"}
          </span>
        </button>
        {actions ? <div className="collapsible-actions">{actions}</div> : null}
      </div>
      {!collapsed ? (
        <div id={panelId} className="collapsible-body">
          {children}
        </div>
      ) : null}
    </div>
  )
}
