import type { ReactNode } from "react"
import { useEffect } from "react"

type SheetProps = {
  open: boolean
  onClose: () => void
  label: string
  className?: string
  /** The caller supplies its own sticky header. */
  children: ReactNode
  "data-testid"?: string
}

// The right-anchored drawer extracted from RubricPanel, which is the only
// consumer today. Backdrop click and Escape both close, because RubricPanel
// already behaves that way and the e2e suite depends on it.
export function Sheet({ open, onClose, label, className, children, ...rest }: SheetProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        data-testid={rest["data-testid"] ? `${rest["data-testid"]}-backdrop` : undefined}
        className="absolute inset-0 bg-scrim"
        onClick={onClose}
        aria-hidden="true"
      />
      <dialog
        {...rest}
        open
        aria-label={label}
        className={[
          "relative m-0 flex h-full w-full max-w-md flex-col overflow-y-auto",
          "bg-white p-0 text-text-body shadow-overlay",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {children}
      </dialog>
    </div>
  )
}
