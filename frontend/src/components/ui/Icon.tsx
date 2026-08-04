import {
  ChevronRight,
  CircleCheck,
  Clock,
  CornerDownRight,
  CornerUpRight,
  Download,
  FileCheck,
  Gavel,
  History,
  Info,
  Keyboard,
  List,
  Lock,
  Mic,
  Play,
  RotateCcw,
  Scale,
  Send,
  Settings,
  SlidersHorizontal,
  Smartphone,
  Square,
  Target,
  TriangleAlert,
  Users,
  X,
} from "lucide-react"

// The 26 icons the design handoff uses, keyed by their kebab Lucide names so
// call sites read the same as `docs/design/Airtight.dc.html`. Bundled rather
// than loaded from the prototype's CDN, per docs/design/README.md:123.
const ICONS = {
  "chevron-right": ChevronRight,
  "circle-check": CircleCheck,
  clock: Clock,
  "corner-down-right": CornerDownRight,
  "corner-up-right": CornerUpRight,
  download: Download,
  "file-check": FileCheck,
  gavel: Gavel,
  history: History,
  info: Info,
  keyboard: Keyboard,
  list: List,
  lock: Lock,
  mic: Mic,
  play: Play,
  "rotate-ccw": RotateCcw,
  scale: Scale,
  send: Send,
  settings: Settings,
  "sliders-horizontal": SlidersHorizontal,
  smartphone: Smartphone,
  square: Square,
  target: Target,
  "triangle-alert": TriangleAlert,
  users: Users,
  x: X,
} as const

export type IconName = keyof typeof ICONS

export const ICON_NAMES = Object.keys(ICONS) as IconName[]

type IconProps = {
  name: IconName
  /** Handoff sizes run 14–24px; 17px is the nav/button default. */
  size?: number
  /** Any CSS color; defaults to `currentColor` so icons inherit text color. */
  color?: string
  strokeWidth?: number
  className?: string
}

export function Icon({
  name,
  size = 17,
  color = "currentColor",
  strokeWidth = 1.75,
  className,
}: IconProps) {
  const Glyph = ICONS[name]
  return (
    <Glyph
      size={size}
      color={color}
      strokeWidth={strokeWidth}
      className={className}
      aria-hidden="true"
      focusable="false"
    />
  )
}
