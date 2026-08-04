import { Icon, type IconName } from "./Icon"

type IconButtonProps = {
  name: IconName
  "aria-label": string
  onClick?: () => void
  inverse?: boolean
  className?: string
  "data-testid"?: string
}

// A distinct component rather than a Button variant — confirmed by counting
// attribute usage across the prototype's instances. Used for the two drawer
// close controls.
export function IconButton({
  name,
  onClick,
  inverse = false,
  className,
  ...rest
}: IconButtonProps) {
  return (
    <button
      {...rest}
      type="button"
      onClick={onClick}
      className={[
        "inline-flex h-8 w-8 items-center justify-center rounded-control border",
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
