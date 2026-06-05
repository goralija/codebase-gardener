import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

type StatCardProps = {
  icon: LucideIcon
  label: string
  value: string | number
  detail: string
}

type PanelProps = {
  icon: LucideIcon
  title: string
  children: ReactNode
}

type EvidenceItem = {
  id: string
  path: string
  summary: string
}

export function StatCard({ icon: Icon, label, value, detail }: StatCardProps) {
  return (
    <div className="rounded-md border bg-card p-4 text-card-foreground">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase">
        <Icon className="size-4" />
        {label}
      </div>
      <div className="mt-3 text-3xl font-semibold">{value}</div>
      <p className="mt-1 text-sm leading-5 text-muted-foreground">{detail}</p>
    </div>
  )
}

export function Panel({ icon: Icon, title, children }: PanelProps) {
  return (
    <section className="rounded-md border bg-card p-5 text-card-foreground">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Icon className="size-4 text-primary" />
        <h2>{title}</h2>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/30 p-4 text-sm leading-6 text-muted-foreground">
      {children}
    </div>
  )
}

export function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded-md border px-2 py-1 text-xs font-medium whitespace-nowrap text-muted-foreground">
      {children}
    </span>
  )
}

export function PathList({ paths }: { paths: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {paths.map((path) => (
        <span
          key={path}
          className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
        >
          {path}
        </span>
      ))}
    </div>
  )
}

export function EvidenceList({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return null
  }

  return (
    <div className="mt-3 grid gap-2">
      {evidence.map((item) => (
        <div
          key={item.id}
          className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground"
        >
          <span className="font-medium text-foreground">{item.path}: </span>
          {item.summary}
        </div>
      ))}
    </div>
  )
}
