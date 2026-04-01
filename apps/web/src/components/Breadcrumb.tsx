type BreadcrumbItem = {
  label: string
  onClick?: () => void
}

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <ol className="breadcrumb-list">
        {items.map((item, i) => {
          const isLast = i === items.length - 1
          return (
            <li key={i} className="breadcrumb-item">
              {isLast || !item.onClick ? (
                <span className={isLast ? "breadcrumb-current" : "breadcrumb-label"}>
                  {item.label}
                </span>
              ) : (
                <button type="button" className="breadcrumb-link" onClick={item.onClick}>
                  {item.label}
                </button>
              )}
              {!isLast ? <span className="breadcrumb-sep" aria-hidden="true">/</span> : null}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
