import type { ButtonHTMLAttributes } from "react"

import { Icon, type IconName } from "./Icon"

const ICON_SIZES = { sm: "h-7 w-7", md: "h-8 w-8" } as const

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & {
  name: IconName
  "aria-label": string
  size?: keyof typeof ICON_SIZES
  inverse?: boolean
  className?: string
}

// A distinct component rather than a Button variant — confirmed by counting
// attribute usage across the prototype's instances. Used for the two drawer
// close controls. `sm` is the in-row size for a control sitting beside 13px text.
export function IconButton({
  name,
  size = "md",
  inverse = false,
  className,
  ...rest
}: IconButtonProps) {
  return (
    <button
      {...rest}
      type="button"
      className={[
        "inline-flex items-center justify-center rounded-control border",
        ICON_SIZES[size],
        "transition-colors duration-hover ease-in",
        "focus-visible:outline-none focus-visible:shadow-focus",
        inverse
          ? "border-inverse text-text-inverse hover:bg-white/10"
          : "border-transparent text-text-muted hover:bg-sand-200",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <Icon name={name} />
    </button>
  )
}
