import type { CSSProperties } from "react"
import { icons } from "lucide-react"

type IconProps = {
  name: string
  size?: number
  strokeWidth?: number
  className?: string
  style?: CSSProperties
  color?: string
}

/**
 * Thin wrapper around lucide-react's icon registry so the ported design can
 * keep referencing icons by string name (e.g. <Icon name="Sprout" />).
 * Falls back to a rounded square placeholder for unknown names, matching the
 * original prototype behaviour.
 */
export function Icon({
  name,
  size = 16,
  strokeWidth = 2,
  className,
  style,
  color,
}: IconProps) {
  const LucideIcon = (icons as Record<string, React.ComponentType<any>>)[name]
  const mergedStyle: CSSProperties = { flex: "none", color, ...style }

  if (!LucideIcon) {
    return (
      <svg
        aria-hidden="true"
        className={"ico" + (className ? " " + className : "")}
        fill="none"
        height={size}
        stroke="currentColor"
        strokeWidth={strokeWidth}
        style={mergedStyle}
        viewBox="0 0 24 24"
        width={size}
      >
        <rect height={16} rx={3} width={16} x={4} y={4} />
      </svg>
    )
  }

  return (
    <LucideIcon
      aria-hidden="true"
      className={"ico" + (className ? " " + className : "")}
      size={size}
      strokeWidth={strokeWidth}
      style={mergedStyle}
    />
  )
}
