import type { ReactNode } from "react"
import { useId } from "react"

type TextareaProps = {
  rows?: number
  placeholder?: string
  value: string
  onChange: (value: string) => void
  hint?: ReactNode
  inverse?: boolean
  id?: string
  "aria-label"?: string
  "data-testid"?: string
}

// 148px at rows=5 — the prototype's `hint-size` — which falls out of five
// 15px/1.65 lines plus 12px of vertical padding. Keep `p-3` and `text-body`
// together; changing either changes the specified height.
export function Textarea({
  rows = 5,
  placeholder,
  value,
  onChange,
  hint,
  inverse = false,
  ...rest
}: TextareaProps) {
  const generatedId = useId()
  const hintId = hint ? `${rest.id ?? generatedId}-hint` : undefined

  return (
    <div className="flex w-full flex-col gap-1.5">
      <textarea
        {...rest}
        rows={rows}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={hintId}
        className={[
          "w-full resize-none rounded-control border p-3 font-ui text-body",
          "transition-colors duration-hover ease-in",
          "focus-visible:outline-none focus-visible:shadow-focus",
          inverse
            ? "border-inverse bg-white/5 text-text-inverse placeholder:text-text-inverse-muted"
            : "border-subtle bg-white text-text-body placeholder:text-text-faint",
        ].join(" ")}
      />
      {hint ? (
        <div
          id={hintId}
          className={[
            "font-data text-[12px]",
            inverse ? "text-text-inverse-muted" : "text-text-muted",
          ].join(" ")}
        >
          {hint}
        </div>
      ) : null}
    </div>
  )
}
