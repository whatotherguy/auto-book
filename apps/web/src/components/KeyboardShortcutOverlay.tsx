import { useEffect, useState } from "react"

const SHORTCUTS = [
  { key: "J", description: "Next issue" },
  { key: "K", description: "Previous issue" },
  { key: "A", description: "Approve current issue" },
  { key: "R", description: "Reject current issue" },
  { key: "Space", description: "Play / Pause audio" },
  { key: "?", description: "Toggle this help" },
]

export function KeyboardShortcutOverlay() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return
      if (event.key === "?" || (event.key === "/" && event.shiftKey)) {
        event.preventDefault()
        setVisible((v) => !v)
      }
      if (event.key === "Escape" && visible) {
        setVisible(false)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [visible])

  return (
    <>
      <button
        type="button"
        className="shortcut-help-trigger"
        onClick={() => setVisible((v) => !v)}
        aria-label="Keyboard shortcuts"
        title="Keyboard shortcuts (?)"
      >
        ?
      </button>
      {visible ? (
        <>
          <div className="shortcut-overlay-backdrop" onClick={() => setVisible(false)} />
          <div className="shortcut-overlay" role="dialog" aria-label="Keyboard shortcuts">
            <strong>Keyboard Shortcuts</strong>
            <ul className="shortcut-list">
              {SHORTCUTS.map((s) => (
                <li key={s.key}>
                  <span>{s.description}</span>
                  <span className="shortcut-key">{s.key}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </>
  )
}
