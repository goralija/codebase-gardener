import { GitBranch, Sprout } from "lucide-react"

import type { FirstReportViewModel } from "../first-report-view-model"
import { Badge, Panel, PathList } from "../components/report-primitives"

type MaintenancePanelsProps = {
  opportunities: FirstReportViewModel["opportunities"]
  prPlans: FirstReportViewModel["prPlans"]
}

export function MaintenancePanels({
  opportunities,
  prPlans,
}: MaintenancePanelsProps) {
  return (
    <section className="grid gap-4 xl:grid-cols-2">
      <Panel icon={Sprout} title="Maintenance opportunities">
        <div className="grid gap-4">
          {opportunities.map((opportunity) => (
            <article
              key={opportunity.id}
              className="rounded-md border bg-background p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{opportunity.category}</Badge>
                <Badge>{opportunity.riskTier}</Badge>
                <Badge>{opportunity.confidence} confidence</Badge>
              </div>
              <h3 className="mt-3 text-lg font-semibold">
                {opportunity.title}
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {opportunity.summary}
              </p>
              <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
                <span>
                  Entropy delta:{" "}
                  <span className="font-medium">
                    {opportunity.expectedEntropyDelta}
                  </span>
                </span>
                <span>
                  Evidence items:{" "}
                  <span className="font-medium">
                    {opportunity.evidenceCount}
                  </span>
                </span>
              </div>
              <PathList paths={opportunity.affectedPaths} />
              <div className="mt-3 flex flex-wrap gap-2">
                {opportunity.requiredChecks.map((check) => (
                  <Badge key={check}>{check}</Badge>
                ))}
              </div>
            </article>
          ))}
        </div>
      </Panel>

      <Panel icon={GitBranch} title="Focused PR plans">
        <div className="grid gap-4">
          {prPlans.map((plan) => (
            <article
              key={plan.id}
              className="rounded-md border bg-background p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{plan.riskTier}</Badge>
                <Badge>{plan.confidence} confidence</Badge>
                <Badge>{plan.blocked ? "Blocked" : "Ready"}</Badge>
              </div>
              <h3 className="mt-3 text-lg font-semibold">{plan.title}</h3>
              <p className="mt-2 text-sm leading-6 break-words text-muted-foreground">
                {plan.branchName}
              </p>
              <div className="mt-4 grid gap-3 text-sm">
                <PrBodyLine label="Goal" value={plan.bodySections.goal} />
                <PrBodyLine
                  label="Evidence"
                  value={plan.bodySections.evidence}
                />
                <PrBodyLine
                  label="Verification"
                  value={plan.bodySections.verification}
                />
              </div>
              <PathList paths={plan.changedPaths} />
              <div className="mt-3 flex flex-wrap gap-2">
                {plan.requiredChecks.map((check) => (
                  <Badge key={check}>{check}</Badge>
                ))}
              </div>
            </article>
          ))}
        </div>
      </Panel>
    </section>
  )
}

function PrBodyLine({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="font-medium">{label}: </span>
      <span className="text-muted-foreground">{value}</span>
    </div>
  )
}
