import { ListChecks } from "lucide-react"

import type { FirstReportViewModel } from "../first-report-view-model"
import { Badge, Panel } from "../components/report-primitives"

type SessionPanelProps = {
  session: FirstReportViewModel["session"]
}

export function SessionPanel({ session }: SessionPanelProps) {
  return (
    <Panel icon={ListChecks} title="Session status">
      <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="grid gap-3 text-sm">
          <SummaryRow label="Trigger" value={session.trigger} />
          <SummaryRow label="Duration" value={session.duration} />
          <SummaryRow label="Errors" value={session.errorCount} />
          <SummaryRow label="Deferred" value={session.deferredCount} last />
        </div>
        <div className="grid gap-3">
          {session.phaseResults.map((phase) => (
            <div key={phase.phase} className="border-b pb-3 last:border-b-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{phase.phase}</span>
                <Badge>{phase.status}</Badge>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {phase.summary}
              </p>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  )
}

function SummaryRow({
  label,
  last = false,
  value,
}: {
  label: string
  last?: boolean
  value: string | number
}) {
  return (
    <div
      className={
        last ? "flex justify-between" : "flex justify-between border-b pb-2"
      }
    >
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
