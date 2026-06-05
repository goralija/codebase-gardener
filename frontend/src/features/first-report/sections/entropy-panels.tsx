import { Gauge, SearchCheck } from "lucide-react"

import type { FirstReportViewModel } from "../first-report-view-model"
import {
  Badge,
  EmptyState,
  EvidenceList,
  Panel,
  PathList,
} from "../components/report-primitives"

type EntropyPanelsProps = {
  entropy: FirstReportViewModel["entropy"]
  logicalSystems: FirstReportViewModel["logicalSystems"]
}

export function EntropyPanels({ entropy, logicalSystems }: EntropyPanelsProps) {
  return (
    <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <Panel icon={Gauge} title="Entropy breakdown">
        <div className="grid gap-3 sm:grid-cols-2">
          {entropy.components.map((component) => (
            <div
              key={component.name}
              className="flex items-center justify-between border-b pb-2 text-sm"
            >
              <span className="text-muted-foreground">{component.name}</span>
              <span className="font-medium">{component.value}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-md bg-muted/40 p-4 text-sm leading-6 text-muted-foreground">
          Forecast confidence {entropy.forecast.confidence}:{" "}
          {entropy.forecast.summary}
        </div>
        {entropy.topContributorCount === 0 ? (
          <div className="mt-3">
            <EmptyState>
              No top entropy contributors are present in this report.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-4 grid gap-3">
            {entropy.topContributors.map((contributor) => (
              <div
                key={contributor.id}
                className="rounded-md border bg-background p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{contributor.kind}</Badge>
                  <Badge>{contributor.impact} impact</Badge>
                  <Badge>{contributor.evidenceCount} evidence items</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  {contributor.summary}
                </p>
                <EvidenceList evidence={contributor.evidence} />
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel icon={SearchCheck} title="Logical systems">
        <div className="grid gap-4">
          {logicalSystems.map((system) => (
            <div key={system.id} className="border-b pb-3 last:border-b-0">
              <div className="font-medium">{system.name}</div>
              <PathList paths={system.paths} />
            </div>
          ))}
        </div>
      </Panel>
    </section>
  )
}
