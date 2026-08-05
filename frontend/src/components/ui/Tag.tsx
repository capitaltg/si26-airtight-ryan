import type { ReactNode } from "react"

import { Icon, type IconName } from "./Icon"

type TagProps = {
  muted?: boolean
  selected?: boolean
  icon?: IconName
  onClick?: () => void
  className?: string
  children: ReactNode
  "data-testid"?: string
}

// 24px pill, per the prototype's `hint-size`. Used both as a static topic label
// and as an archive filter control, so it renders a <button> only when it is
// given an onClick — a static tag must not land in the tab order.
export function Tag({
  muted = false,
  selected = false,
  icon,
  onClick,
  className,
  children,
  ...rest
}: TagProps) {
  const classes = [
    "inline-flex h-6 items-center gap-1.5 rounded-pill px-2.5",
    "font-ui text-micro font-semibold uppercase",
    "transition-colors duration-hover ease-in",
    selected
      ? "bg-navy-800 text-text-inverse"
      : muted
        ? "bg-sand-200 text-text-muted"
        : "border border-subtle bg-white text-text-body",
    className,
  ]
    .filter(Boolean)
    .join(" ")

  const content = (
    <>
      {icon ? <Icon name={icon} size={14} /> : null}
      {children}
    </>
  )

  if (!onClick) {
    return (
      <span {...rest} className={classes}>
        {content}
      </span>
    )
  }

  return (
    <button
      {...rest}
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`${classes} focus-visible:outline-none focus-visible:shadow-focus`}
    >
      {content}
    </button>
  )
}
