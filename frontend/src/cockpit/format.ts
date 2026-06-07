/* ============================================================
   Cockpit formatters + entropy helpers
   Ported from the design prototype, adapted to real API data.
   ============================================================ */

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return "—"
  const s = Math.round((Date.now() - then) / 1000)
  if (s < 60) return `${Math.max(s, 0)}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h ago`
  const d = Math.round(h / 24)
  return `${d}d ago`
}

export function shortTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  })
}

export function duration(
  start: string | null | undefined,
  end: string | null | undefined
): string {
  if (!start || !end) return "—"
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (Number.isNaN(ms) || ms < 0) return "—"
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  if (m === 0) return `${s}s`
  return `${m}m ${String(s).padStart(2, "0")}s`
}

export function fmt(n: number | null | undefined): string {
  if (n == null) return "—"
  return n.toLocaleString("en-US")
}

export function pct(ratio: number | null | undefined): number | null {
  if (ratio == null) return null
  // Confidence / coverage arrive as 0..1 ratios; entropy already 0..100.
  return Math.round(ratio <= 1 ? ratio * 100 : ratio)
}

export function entColor(score: number | null | undefined): string {
  if (score == null) return "var(--fg-4)"
  if (score < 30) return "var(--e-low)"
  if (score < 50) return "var(--e-mod)"
  if (score < 70) return "var(--e-elev)"
  return "var(--e-high)"
}

export type EntropyBand = {
  key: "low" | "mod" | "elev" | "high"
  label: string
}

export function classify(score: number): EntropyBand {
  if (score < 30) return { key: "low", label: "Low" }
  if (score < 50) return { key: "mod", label: "Moderate" }
  if (score < 70) return { key: "elev", label: "Elevated" }
  return { key: "high", label: "High" }
}

export const BAND_TONE: Record<EntropyBand["key"], string> = {
  elev: "amber",
  high: "red",
  low: "green",
  mod: "blue",
}

/** Map a backend risk_tier (or plain low/medium/high) to a risk level. */
export function riskFromTier(tier: string | null | undefined): string {
  if (!tier) return "medium"
  const t = tier.toLowerCase()
  if (t.includes("tier_1") || t === "low") return "low"
  if (t.includes("tier_3") || t === "high") return "high"
  if (t.includes("tier_2") || t === "medium") return "medium"
  return "medium"
}

/** Humanise a snake_case category/string into Title Case words. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—"
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
