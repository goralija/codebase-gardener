import { AlertTriangle, ClipboardList } from "lucide-react"

import type { FirstReportViewModel } from "../first-report-view-model"
import {
  Badge,
  EmptyState,
  EvidenceList,
  Panel,
  PathList,
} from "../components/report-primitives"

type ArchitectureConstitutionPanelsProps = {
  architecture: FirstReportViewModel["architecture"]
  constitution: FirstReportViewModel["constitution"]
}

export function ArchitectureConstitutionPanels({
  architecture,
  constitution,
}: ArchitectureConstitutionPanelsProps) {
  return (
    <section className="grid gap-4 xl:grid-cols-2">
      <Panel icon={AlertTriangle} title="Architecture violations">
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Metric
            label="total violations"
            value={architecture.violationCount}
          />
          <Metric
            label="dependency cycles"
            value={architecture.dependencyCycleCount}
          />
          <Metric
            label="boundary rules"
            value={architecture.boundaryRuleCount}
          />
        </div>
        {!architecture.hasViolations ? (
          <EmptyState>
            No architecture violations or dependency cycles are present in this
            report.
          </EmptyState>
        ) : null}
      </Panel>

      <Panel icon={ClipboardList} title="Constitution questions">
        <div className="grid gap-4 sm:grid-cols-2">
          <Metric
            label="source-truth coverage"
            value={constitution.completeness}
          />
          <Metric
            label="open questions"
            value={constitution.openQuestionCount}
          />
        </div>

        {constitution.hasOpenQuestions ? (
          <div className="mt-4 grid gap-3">
            {constitution.openQuestions.map((question) => (
              <div
                key={question.id}
                className="rounded-md border bg-background p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{question.severity}</Badge>
                  <Badge>{question.evidenceCount} evidence items</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  {question.question}
                </p>
                <EvidenceList evidence={question.evidence} />
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-4">
            <EmptyState>
              No open constitution questions in this report.
            </EmptyState>
          </div>
        )}

        <div className="mt-4 grid gap-4">
          {constitution.protectedModules.map((module) => (
            <div
              key={`${module.name}-${module.paths.join("|")}`}
              className="border-b pb-3 last:border-b-0"
            >
              <div className="flex flex-wrap items-center gap-2 sm:justify-between">
                <span className="font-medium">{module.name}</span>
                <Badge>protected module</Badge>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {module.reason}
              </p>
              <PathList paths={module.paths} />
            </div>
          ))}
          {constitution.neverTouch.map((item) => (
            <div key={item.path} className="border-b pb-3 last:border-b-0">
              <div className="flex flex-wrap items-center gap-2 sm:justify-between">
                <span className="font-medium">{item.path}</span>
                <Badge>never touch</Badge>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {item.reason}
              </p>
            </div>
          ))}
        </div>
      </Panel>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-2xl font-semibold">{value}</div>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}
