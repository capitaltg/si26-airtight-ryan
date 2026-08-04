import type { ReactNode } from "react"
import { useEffect } from "react"

const SIZES = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl" } as const

type ModalProps = {
  open: boolean
  /** Omit for a dialog that must be answered: without it there is no Escape. */
  onClose?: () => void
  label: string
  size?: keyof typeof SIZES
  className?: string
  children: ReactNode
  /** Kept in the API because DiscardRecordingDialog already sets it. */
  "aria-modal"?: "true"
  "data-testid"?: string
}

// Native <dialog open> rather than showModal(), matching what
// DiscardRecordingDialog and RubricPanel already do — showModal() moves focus
// and installs the browser's own backdrop, which would change behavior the e2e
// suite asserts. This component owns the scrim token and the Escape listener so
// the four dialog sites stop duplicating both. Backdrop-click-to-close is
// deliberately absent: no call site has it today.
export function Modal({
  open,
  onClose,
  label,
  size = "sm",
  className,
  children,
  ...rest
}: ModalProps) {
  useEffect(() => {
    if (!open || !onClose) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      data-testid={rest["data-testid"] ? `${rest["data-testid"]}-scrim` : undefined}
      className="fixed inset-0 z-40 flex items-center justify-center bg-scrim p-4"
    >
      <dialog
        {...rest}
        open
        aria-label={label}
        className={[
          "relative m-0 w-full space-y-3 rounded-card bg-white p-4 text-text-body shadow-overlay",
          SIZES[size],
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
