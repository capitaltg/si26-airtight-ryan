import type { SelectHTMLAttributes } from "react"
import { forwardRef } from "react"

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "className"> & {
  className?: string
}

// The native select on the token control surface: same radius, border, and focus
// ring as Input, with `pr-8` leaving room for the platform arrow.
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select
      {...rest}
      ref={ref}
      className={[
        "h-[38px] w-full rounded-control border border-subtle bg-white pl-3 pr-8",
        "font-ui text-body-sm text-text-body",
        "transition-colors duration-hover ease-in",
        "focus-visible:outline-none focus-visible:shadow-focus",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </select>
  )
})
