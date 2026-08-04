import type { ReactNode, TextareaHTMLAttributes } from "react"
import { forwardRef, useId } from "react"

// Every native textarea attribute passes through — `onKeyDown` (Rehearsal's
// Cmd+Enter submit), `maxLength`, `disabled`, `autoFocus`. `onChange` keeps its
// string-valued signature: four call sites pass `(value) => setState(value)`.
type TextareaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "className"> & {
  value: string
  onChange: (value: string) => void
  hint?: ReactNode
  inverse?: boolean
  resize?: "none" | "vertical"
}

// 126px at rows=5: five 14px/1.43 lines plus `p-3`'s vertical padding and the
// border. The handoff specified 148px off a 15px/1.65 body; body type is now
// main's 14px/1.43, so the box follows it down. Keep `p-3` and `text-body`
// together; changing either changes the height.
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { rows = 5, value, onChange, hint, inverse = false, resize = "none", ...rest },
  ref,
) {
  const generatedId = useId()
  const hintId = hint ? `${rest.id ?? generatedId}-hint` : undefined

  return (
    <div className="flex w-full flex-col gap-1.5">
      <textarea
        // `aria-describedby` comes before the spread so a caller cannot clobber
        // the hint wiring, and `...rest` after it so every other attribute lands.
        aria-describedby={hintId}
        {...rest}
        ref={ref}
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={[
          "w-full rounded-control border p-3 font-ui text-body",
          resize === "none" ? "resize-none" : "resize-y",
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
            "font-data text-micro",
            inverse ? "text-text-inverse-muted" : "text-text-muted",
          ].join(" ")}
        >
          {hint}
        </div>
      ) : null}
    </div>
  )
})
