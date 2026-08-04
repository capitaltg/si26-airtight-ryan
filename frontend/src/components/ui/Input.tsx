import type { InputHTMLAttributes } from "react"
import { forwardRef } from "react"

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "className"> & {
  invalid?: boolean
  className?: string
}

// The single-line counterpart to Textarea, sharing its control radius, token
// border, and focus ring. Replaces PersonaForm's FIELD class constant. 38px to
// match Button size="md", so a control row lines up.
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid = false, type = "text", className, ...rest },
  ref,
) {
  return (
    <input
      {...rest}
      ref={ref}
      type={type}
      aria-invalid={invalid || undefined}
      className={[
        "h-[38px] w-full rounded-control border bg-white px-3 font-ui text-body-sm",
        "text-text-body placeholder:text-text-faint",
        "transition-colors duration-hover ease-in",
        "focus-visible:outline-none focus-visible:shadow-focus",
        "disabled:cursor-not-allowed disabled:opacity-50",
        invalid ? "border-crimson-700" : "border-subtle",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    />
  )
})
