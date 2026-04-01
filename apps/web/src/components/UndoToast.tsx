import { useEffect, useRef, useState } from "react"

export type UndoToastData = {
  id: number
  message: string
  onUndo: () => void
}

let toastIdCounter = 0
export function nextToastId() {
  return ++toastIdCounter
}

export function UndoToast({
  toast,
  onDismiss,
}: {
  toast: UndoToastData | null
  onDismiss: () => void
}) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (toast) {
      setVisible(true)
      if (timerRef.current != null) window.clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => {
        setVisible(false)
        window.setTimeout(onDismiss, 300)
      }, 4000)
    } else {
      setVisible(false)
    }

    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current)
    }
  }, [toast?.id])

  if (!toast) return null

  return (
    <div className={`undo-toast ${visible ? "undo-toast-visible" : ""}`}>
      <span className="undo-toast-message">{toast.message}</span>
      <button
        type="button"
        className="undo-toast-action"
        onClick={() => {
          toast.onUndo()
          setVisible(false)
          if (timerRef.current != null) window.clearTimeout(timerRef.current)
          window.setTimeout(onDismiss, 300)
        }}
      >
        Undo
      </button>
    </div>
  )
}
