import type { ButtonHTMLAttributes } from "react"

import { Icon, type IconName } from "./Icon"

export type ButtonVariant = "primary" | "secondary" | "ghost" | "inverse" | "danger"
export type ButtonSize = "sm" | "md" | "lg"

// Heights are the prototype's `hint-size` values, not a guess.
const SIZES: Record<ButtonSize, string> = {
  sm: "h-[30px] px-3 text-body-sm",
  md: "h-[38px] px-4 text-body-sm",
  lg: "h-[48px] px-6 text-body",
}

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-crimson-700 text-text-inverse hover:bg-crimson-600 border border-crimson-700",
  secondary: "bg-white text-text-strong border border-subtle hover:bg-sand-50",
  ghost: "bg-transparent text-text-muted border border-transparent hover:bg-sand-200",
  // A fifth variant, not a modifier on the other four — confirmed by counting
  // attribute usage across the prototype's 143 component instances.
  inverse: "bg-white/10 text-text-inverse border border-inverse hover:bg-white/20",
  // Not specified by the handoff. Crimson-on-crimson would be indistinguishable
  // from `primary`, and the design allows at most one accent per view, so
  // danger is the outlined form. See the plan's Deviations §3.
  danger: "bg-transparent text-crimson-700 border border-crimson-700 hover:bg-crimson-100",
}

// Every native button attribute passes through: 39 call sites across the app
// need `title`, `autoFocus`, `onKeyDown`, and `aria-*` that a hand-listed prop
// type cannot express.
type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & {
  variant?: ButtonVariant
  size?: ButtonSize
  block?: boolean
  iconLeft?: IconName
  iconRight?: IconName
  className?: string
}

export function Button({
  variant = "secondary",
  size = "md",
  block = false,
  iconLeft,
  iconRight,
  // A bare <button> inside a form defaults to `submit`; three PersonaForm call
  // sites rely on this staying `button` unless asked otherwise.
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  const iconSize = size === "lg" ? 20 : 17
  return (
    <button
      {...rest}
      type={type}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-control font-ui font-semibold",
        "transition-colors duration-hover ease-in",
        "focus-visible:outline-none focus-visible:shadow-focus",
        "disabled:cursor-not-allowed disabled:opacity-50",
        SIZES[size],
        VARIANTS[variant],
        block ? "w-full" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {iconLeft ? <Icon name={iconLeft} size={iconSize} /> : null}
      {children}
      {iconRight ? <Icon name={iconRight} size={iconSize} /> : null}
    </button>
  )
}
