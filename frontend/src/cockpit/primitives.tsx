/* ============================================================
   Cockpit shared UI primitives — ported from the design prototype.
   ============================================================ */
/* eslint-disable react-refresh/only-export-components */
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react"

import { Icon } from "@/cockpit/icon"
import {
  BAND_TONE,
  classify,
  entColor,
  type EntropyBand,
} from "@/cockpit/format"
import {
  AUTONOMY,
  CAT_ICON,
  COMPONENTS,
  DEFAULT_CONFIDENCE_FLOOR,
  STATUS_ICON,
  STATUS_TONE,
  type AutonomyMode,
  type EntropyComponentKey,
} from "@/cockpit/model"

/* ---------- language / repo dot ---------- */
export function RepoDot({ color }: { color?: string }) {
  return (
    <span
      style={{
        background: color || "#6b7178",
        borderRadius: "50%",
        flex: "none",
        height: 9,
        width: 9,
      }}
    />
  )
}

export function RepoName({
  name,
  color,
  mono = true,
}: {
  name: string
  color?: string
  mono?: boolean
}) {
  return (
    <span className="repo-cell">
      <RepoDot color={color} />
      <span
        className={mono ? "mono" : ""}
        style={{ color: "var(--fg)", fontSize: 13, fontWeight: 500 }}
      >
        {name}
      </span>
    </span>
  )
}

/* ---------- badges ---------- */
export function Badge({
  tone = "slate",
  children,
  icon,
  dot,
  lg,
  className,
}: {
  tone?: string
  children?: ReactNode
  icon?: string
  dot?: boolean
  lg?: boolean
  className?: string
}) {
  return (
    <span
      className={`badge ${tone}${dot ? " dot" : ""}${lg ? " lg" : ""}${
        className ? " " + className : ""
      }`}
    >
      {icon && <Icon name={icon} size={lg ? 13 : 12} />}
      {children}
    </span>
  )
}

export function StatusBadge({ status, lg }: { status: string; lg?: boolean }) {
  return (
    <Badge icon={STATUS_ICON[status]} lg={lg} tone={STATUS_TONE[status] || "slate"}>
      {status}
    </Badge>
  )
}

export function RiskBadge({ risk }: { risk: string }) {
  const tone = risk === "low" ? "green" : risk === "medium" ? "amber" : "red"
  return <Badge tone={tone}>{risk} risk</Badge>
}

export function ConfidenceBadge({
  value,
  floor = DEFAULT_CONFIDENCE_FLOOR,
}: {
  value: number
  floor?: number
}) {
  const tone = value >= floor ? "green" : value >= 75 ? "amber" : "red"
  return <Badge tone={tone}>{value}%</Badge>
}

export function AutonomyBadge({ mode }: { mode: AutonomyMode }) {
  const a = AUTONOMY[mode]
  return (
    <Badge
      icon={
        mode === "autonomous"
          ? "Bot"
          : mode === "assisted"
            ? "UserCheck"
            : "FileText"
      }
      tone={a.color}
    >
      {a.label}
    </Badge>
  )
}

export function CategoryBadge({ cat }: { cat: string }) {
  return (
    <Badge icon={CAT_ICON[cat] || "FileText"} tone="slate">
      {cat.replace(/_/g, " ")}
    </Badge>
  )
}

export function EntropyBadge({ score }: { score: number | null }) {
  if (score == null) return <Badge tone="slate">No baseline</Badge>
  const band: EntropyBand = classify(score)
  return (
    <Badge tone={BAND_TONE[band.key]}>
      {score} · {band.label}
    </Badge>
  )
}

export function Delta({
  value,
  invert = true,
  suffix = "",
}: {
  value: number | null
  invert?: boolean
  suffix?: string
}) {
  if (value == null || value === 0)
    return (
      <span className="delta flat">
        <Icon name="Minus" size={11} />0{suffix}
      </span>
    )
  const worse = invert ? value > 0 : value < 0
  const cls = worse ? "up" : "down"
  const arrow = value > 0 ? "ArrowUp" : "ArrowDown"
  return (
    <span className={`delta ${cls}`}>
      <Icon name={arrow} size={11} />
      {Math.abs(value)}
      {suffix}
    </span>
  )
}

/* ---------- sparkline ---------- */
export function Sparkline({
  data,
  width = 80,
  height = 24,
  color,
}: {
  data: number[]
  width?: number
  height?: number
  color?: string
}) {
  if (!data || data.length < 2)
    return <span className="faint mono tiny">—</span>
  const min = Math.min(...data)
  const max = Math.max(...data)
  const rng = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * (width - 2) + 1
    const y = height - 2 - ((v - min) / rng) * (height - 4)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const last = data[data.length - 1]
  const c = color || entColor(last)
  const [lx, ly] = pts[pts.length - 1].split(",")
  return (
    <svg
      className="spark"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
    >
      <polyline
        fill="none"
        points={pts.join(" ")}
        stroke={c}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <circle cx={lx} cy={ly} fill={c} r="2" />
    </svg>
  )
}

/* ---------- entropy gauge (270° arc) ---------- */
export function EntropyGauge({
  score,
  size = 168,
  stroke = 13,
  showClass = true,
}: {
  score: number | null
  size?: number
  stroke?: number
  showClass?: boolean
}) {
  const r = (size - stroke) / 2
  const cx = size / 2
  const cy = size / 2
  const C = 2 * Math.PI * r
  const sweep = 0.75
  const trackLen = C * sweep
  const valLen = score == null ? 0 : (score / 100) * trackLen
  const color = entColor(score)
  const band = score == null ? null : classify(score)
  const numSize = size * 0.3
  return (
    <div className="gauge" style={{ height: size, width: size }}>
      <svg height={size} style={{ transform: "rotate(135deg)" }} width={size}>
        <circle
          cx={cx}
          cy={cy}
          fill="none"
          r={r}
          stroke="var(--panel-3)"
          strokeDasharray={`${trackLen} ${C}`}
          strokeLinecap="round"
          strokeWidth={stroke}
        />
        <circle
          cx={cx}
          cy={cy}
          fill="none"
          r={r}
          stroke={color}
          strokeDasharray={`${valLen} ${C}`}
          strokeLinecap="round"
          strokeWidth={stroke}
          style={{ transition: "stroke-dasharray .6s cubic-bezier(.2,.7,.2,1)" }}
        />
      </svg>
      <div className="g-val">
        <div className="g-num" style={{ color, fontSize: numSize }}>
          {score == null ? "—" : score}
        </div>
        {showClass &&
          (band ? (
            <div className="g-class" style={{ color }}>
              {band.label}
            </div>
          ) : (
            <div className="g-class faint">No baseline</div>
          ))}
        {showClass && <div className="g-of">/ 100 entropy</div>}
      </div>
    </div>
  )
}

/* ---------- radar (6 components) ---------- */
export function Radar({
  components,
  size = 260,
  color = "var(--accent)",
}: {
  components: Record<EntropyComponentKey, number> | null
  size?: number
  color?: string
}) {
  const comps = COMPONENTS
  const padX = 80
  const padY = 36
  const W = size + padX * 2
  const H = size + padY * 2
  const cx = W / 2
  const cy = H / 2
  const R = size * 0.34
  // Components arrive as small risk contributions; scale to the radar so the
  // shape is legible while staying proportional to the real values.
  const values = comps.map((c) => (components ? components[c.key] : 0))
  const maxVal = Math.max(10, ...values)
  const angle = (i: number) =>
    ((-90 + i * (360 / comps.length)) * Math.PI) / 180
  const pt = (i: number, v: number): [number, number] => [
    cx + Math.cos(angle(i)) * R * (v / maxVal),
    cy + Math.sin(angle(i)) * R * (v / maxVal),
  ]
  const ring = (frac: number) =>
    comps.map((_, i) => pt(i, maxVal * frac).join(",")).join(" ")
  const valPts = comps.map((_, i) => pt(i, values[i]))
  const poly = valPts.map((p) => p.join(",")).join(" ")
  const anchorFor = (x: number) =>
    x < cx - 2 ? "end" : x > cx + 2 ? "start" : "middle"
  return (
    <svg
      className="radar"
      height={H}
      style={{ display: "block", height: "auto", maxWidth: "100%" }}
      viewBox={`0 0 ${W} ${H}`}
      width={W}
    >
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon
          fill="none"
          key={f}
          points={ring(f)}
          stroke="var(--border)"
          strokeWidth="1"
        />
      ))}
      {comps.map((c, i) => {
        const [x, y] = pt(i, maxVal)
        return (
          <line
            key={c.key}
            stroke="var(--border)"
            strokeWidth="1"
            x1={cx}
            x2={x}
            y1={cy}
            y2={y}
          />
        )
      })}
      <polygon
        fill={color}
        fillOpacity="0.16"
        points={poly}
        stroke={color}
        strokeWidth="1.5"
      />
      {valPts.map((p, i) => (
        <circle cx={p[0]} cy={p[1]} fill={color} key={i} r="2.5" />
      ))}
      {comps.map((c, i) => {
        const [x, y] = pt(i, maxVal * 1.18)
        return (
          <text
            dominantBaseline="middle"
            fill="var(--fg-3)"
            fontFamily="var(--mono)"
            fontSize="10.5"
            key={c.key}
            textAnchor={anchorFor(x)}
            x={x}
            y={y}
          >
            {c.label}
          </text>
        )
      })}
    </svg>
  )
}

/* ---------- component bars ---------- */
export function ComponentBars({
  components,
}: {
  components: Record<EntropyComponentKey, number> | null
}) {
  if (!components) return null
  const maxVal = Math.max(10, ...COMPONENTS.map((c) => components[c.key]))
  return (
    <div>
      {COMPONENTS.map((c) => {
        const v = components[c.key]
        const width = Math.round((v / maxVal) * 100)
        return (
          <div className="cbar" key={c.key}>
            <div className="cb-label">
              <Icon color="var(--fg-3)" name={c.icon} size={13} />
              {c.label}
            </div>
            <div className="meter">
              <span style={{ background: entColor(v), width: width + "%" }} />
            </div>
            <div className="cb-val" style={{ color: entColor(v) }}>
              {v}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- toggle ---------- */
export function Switch({
  on,
  onClick,
}: {
  on: boolean
  onClick?: () => void
}) {
  return (
    <button
      aria-pressed={on}
      className={`switch${on ? " on" : ""}`}
      onClick={onClick}
      type="button"
    />
  )
}

/* ---------- stat card ---------- */
export function Stat({
  label,
  icon,
  value,
  unit,
  foot,
  accent,
  onClick,
  tone,
}: {
  label: string
  icon: string
  value: ReactNode
  unit?: ReactNode
  foot?: ReactNode
  accent?: string
  onClick?: () => void
  tone?: string
}) {
  return (
    <div className={`stat${onClick ? " link" : ""}`} onClick={onClick}>
      {accent && <span className="s-accent" style={{ background: accent }} />}
      <div className="s-label">
        <Icon name={icon} size={13} />
        {label}
      </div>
      <div className="s-val" style={{ color: tone }}>
        {value}
        {unit && <span className="s-unit">{unit}</span>}
      </div>
      {foot && <div className="s-foot">{foot}</div>}
    </div>
  )
}

/* ---------- empty state ---------- */
export function Empty({
  icon = "Inbox",
  title,
  sub,
  action,
}: {
  icon?: string
  title: string
  sub?: string
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <div className="e-ico">
        <Icon name={icon} size={22} />
      </div>
      <div className="e-title">{title}</div>
      {sub && <div className="e-sub">{sub}</div>}
      {action}
    </div>
  )
}

/* ---------- dropdown selector ---------- */
export function useClickOutside(
  ref: React.RefObject<HTMLElement | null>,
  onClose: () => void
) {
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [ref, onClose])
}

export type SelectorOption = {
  value: string
  label: string
  icon?: string
  meta?: string
}

export function Selector({
  icon,
  label,
  value,
  options,
  onChange,
  align = "left",
  width = 240,
}: {
  icon?: string
  label?: string
  value: string
  options: SelectorOption[]
  onChange: (value: string) => void
  align?: "left" | "right"
  width?: number
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useClickOutside(ref, () => setOpen(false))
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        className="selector"
        onClick={() => setOpen((o) => !o)}
        type="button"
      >
        {icon && <Icon className="s-ico" name={icon} size={14} />}
        {label && (
          <span className="muted" style={{ fontSize: 12 }}>
            {label}
          </span>
        )}
        <span className="mono" style={{ fontWeight: 500 }}>
          {value}
        </span>
        <Icon className="chev" name="ChevronDown" size={14} />
      </button>
      {open && (
        <div className="menu" style={{ [align]: 0, top: 38, width } as CSSProperties}>
          {options.map((o) => (
            <button
              className={`menu-item${o.value === value ? " on" : ""}`}
              key={o.value}
              onClick={() => {
                onChange(o.value)
                setOpen(false)
              }}
              type="button"
            >
              {o.icon && <Icon name={o.icon} size={15} />}
              <span style={{ flex: 1 }}>{o.label}</span>
              {o.value === value && <Icon name="Check" size={14} />}
              {o.meta && <span className="faint mono tiny">{o.meta}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------- segmented filter ---------- */
export function SegX({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string; count?: number }[]
}) {
  return (
    <div className="segx">
      {options.map((o) => (
        <button
          className={value === o.value ? "on" : ""}
          key={o.value}
          onClick={() => onChange(o.value)}
          type="button"
        >
          {o.label}
          {o.count != null && (
            <span style={{ marginLeft: 5, opacity: 0.6 }}>{o.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

/* ---------- drawer / modal shells ---------- */
export function Drawer({
  children,
  onClose,
  width,
}: {
  children: ReactNode
  onClose: () => void
  width?: number
}) {
  useEffect(() => {
    function esc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", esc)
    return () => document.removeEventListener("keydown", esc)
  }, [onClose])
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="drawer" style={width ? { width } : undefined}>
        {children}
      </div>
    </>
  )
}

export function Modal({
  children,
  onClose,
  width,
}: {
  children: ReactNode
  onClose: () => void
  width?: number
}) {
  useEffect(() => {
    function esc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", esc)
    return () => document.removeEventListener("keydown", esc)
  }, [onClose])
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="modal" style={width ? { width } : undefined}>
        {children}
      </div>
    </>
  )
}

/* ---------- loaders ---------- */
export function RunLoader({
  title = "Working…",
  sub,
  min = 240,
}: {
  title?: string
  sub?: string
  min?: number
}) {
  return (
    <div
      className="card"
      style={{
        display: "grid",
        gap: 16,
        minHeight: min,
        padding: 28,
        placeItems: "center",
      }}
    >
      <div className="row gap10">
        <Icon className="spin" color="var(--accent-2)" name="Loader" size={20} />
        <span className="b6">{title}</span>
      </div>
      {sub && <div className="tiny muted mono">{sub}</div>}
      <div style={{ display: "grid", gap: 9, maxWidth: 360, width: "62%" }}>
        <div className="skel" style={{ height: 11, width: "100%" }} />
        <div className="skel" style={{ height: 11, width: "82%" }} />
        <div className="skel" style={{ height: 11, width: "91%" }} />
        <div className="skel" style={{ height: 11, width: "70%" }} />
      </div>
    </div>
  )
}
