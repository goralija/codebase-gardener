import { useQuery } from "@tanstack/react-query"
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  ClipboardList,
  Gauge,
  GitBranch,
  GitPullRequest,
  ListChecks,
  SearchCheck,
  ShieldCheck,
  Sprout,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

import firstReportFixture from "../../fixtures/contracts/first_report_fixture.json"
import {
  buildFirstReportViewModel,
  type FirstReportFixture,
} from "@/lib/first-report"

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

function useFirstReportFixture() {
  return useQuery<FirstReportFixture>({
    queryKey: ["first-report-fixture"],
    queryFn: () => Promise.resolve(firstReportFixture),
  })
}

function StatCard({ icon: Icon, label, value, detail }: StatCardProps) {
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

function Panel({ icon: Icon, title, children }: PanelProps) {
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

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/30 p-4 text-sm leading-6 text-muted-foreground">
      {children}
    </div>
  )
}

function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded-md border px-2 py-1 text-xs font-medium whitespace-nowrap text-muted-foreground">
      {children}
    </span>
  )
}

function PathList({ paths }: { paths: string[] }) {
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

export function App() {
  const { data, isLoading } = useFirstReportFixture()
  const report = data ?? firstReportFixture
  const view = buildFirstReportViewModel(report)
  const prPlanCount = view.prPlans.length
  const focusedPrPlanLabel =
    prPlanCount === 1 ? "1 focused PR plan" : `${prPlanCount} focused PR plans`
  const selectedOpportunityLabel =
    view.session.selectedCount === 1
      ? "1 opportunity selected"
      : `${view.session.selectedCount} opportunities selected`

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-6 lg:px-8">
        <header className="border-b pb-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex max-w-3xl flex-col gap-3">
              <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Sprout className="size-4" />
                Repository report
              </div>
              <div>
                <h1 className="text-3xl font-semibold tracking-normal">
                  First report
                </h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                  {view.repository.id} at commit{" "}
                  {view.repository.shortCommitSha}. The latest session is{" "}
                  {view.session.status.toLowerCase()} with {focusedPrPlanLabel}.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              {isLoading ? (
                <>
                  <CircleDashed className="size-4 animate-spin" />
                  Loading report
                </>
              ) : (
                <>
                  <CheckCircle2 className="size-4 text-primary" />
                  Report ready
                </>
              )}
            </div>
          </div>
        </header>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            icon={Gauge}
            label="Repository Entropy Score"
            value={view.entropy.overall}
            detail={`${view.entropy.classification}; forecast ${view.entropy.forecast.predictedOverall} over ${view.entropy.forecast.horizonDays} days.`}
          />
          <StatCard
            icon={ShieldCheck}
            label="Constitution Coverage"
            value={view.constitution.completeness}
            detail={`${view.constitution.openQuestionCount} open constitution questions.`}
          />
          <StatCard
            icon={Activity}
            label="Session Status"
            value={view.session.status}
            detail={`${view.session.duration}; ${selectedOpportunityLabel}.`}
          />
          <StatCard
            icon={GitPullRequest}
            label="Focused PR Plans"
            value={prPlanCount}
            detail={`${prPlanCount} generated by the latest session.`}
          />
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <Panel icon={Gauge} title="Entropy breakdown">
            <div className="grid gap-3 sm:grid-cols-2">
              {view.entropy.components.map((component) => (
                <div
                  key={component.name}
                  className="flex items-center justify-between border-b pb-2 text-sm"
                >
                  <span className="text-muted-foreground">
                    {component.name}
                  </span>
                  <span className="font-medium">{component.value}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-md bg-muted/40 p-4 text-sm leading-6 text-muted-foreground">
              Forecast confidence {view.entropy.forecast.confidence}:{" "}
              {view.entropy.forecast.summary}
            </div>
            {view.entropy.topContributorCount === 0 ? (
              <div className="mt-3">
                <EmptyState>
                  No top entropy contributors are present in this report.
                </EmptyState>
              </div>
            ) : (
              <div className="mt-4 grid gap-3">
                {view.entropy.topContributors.map((contributor) => (
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
                    <div className="mt-3 grid gap-2">
                      {contributor.evidence.map((evidence) => (
                        <div
                          key={evidence.id}
                          className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground"
                        >
                          <span className="font-medium text-foreground">
                            {evidence.path}:{" "}
                          </span>
                          {evidence.summary}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel icon={SearchCheck} title="Logical systems">
            <div className="grid gap-4">
              {view.logicalSystems.map((system) => (
                <div key={system.id} className="border-b pb-3 last:border-b-0">
                  <div className="font-medium">{system.name}</div>
                  <PathList paths={system.paths} />
                </div>
              ))}
            </div>
          </Panel>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <Panel icon={AlertTriangle} title="Architecture violations">
            <div className="mb-4 grid gap-3 sm:grid-cols-3">
              <div>
                <div className="text-2xl font-semibold">
                  {view.architecture.violationCount}
                </div>
                <p className="text-sm text-muted-foreground">
                  total violations
                </p>
              </div>
              <div>
                <div className="text-2xl font-semibold">
                  {view.architecture.dependencyCycleCount}
                </div>
                <p className="text-sm text-muted-foreground">
                  dependency cycles
                </p>
              </div>
              <div>
                <div className="text-2xl font-semibold">
                  {view.architecture.boundaryRuleCount}
                </div>
                <p className="text-sm text-muted-foreground">boundary rules</p>
              </div>
            </div>
            {!view.architecture.hasViolations ? (
              <EmptyState>
                No architecture violations or dependency cycles are present in
                this report.
              </EmptyState>
            ) : null}
          </Panel>

          <Panel icon={ClipboardList} title="Constitution questions">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <div className="text-2xl font-semibold">
                  {view.constitution.completeness}
                </div>
                <p className="text-sm text-muted-foreground">
                  source-truth coverage
                </p>
              </div>
              <div>
                <div className="text-2xl font-semibold">
                  {view.constitution.openQuestionCount}
                </div>
                <p className="text-sm text-muted-foreground">open questions</p>
              </div>
            </div>
            {view.constitution.hasOpenQuestions ? (
              <div className="mt-4 grid gap-3">
                {view.constitution.openQuestions.map((question) => (
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
                    <div className="mt-3 grid gap-2">
                      {question.evidence.map((evidence) => (
                        <div
                          key={evidence.id}
                          className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground"
                        >
                          <span className="font-medium text-foreground">
                            {evidence.path}:{" "}
                          </span>
                          {evidence.summary}
                        </div>
                      ))}
                    </div>
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
              {view.constitution.protectedModules.map((module) => (
                <div
                  key={module.name}
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
              {view.constitution.neverTouch.map((item) => (
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

        <Panel icon={ListChecks} title="Session status">
          <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
            <div className="grid gap-3 text-sm">
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Trigger</span>
                <span className="font-medium">{view.session.trigger}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Duration</span>
                <span className="font-medium">{view.session.duration}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Errors</span>
                <span className="font-medium">{view.session.errorCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Deferred</span>
                <span className="font-medium">
                  {view.session.deferredCount}
                </span>
              </div>
            </div>
            <div className="grid gap-3">
              {view.session.phaseResults.map((phase) => (
                <div
                  key={phase.phase}
                  className="border-b pb-3 last:border-b-0"
                >
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

        <section className="grid gap-4 xl:grid-cols-2">
          <Panel icon={Sprout} title="Maintenance opportunities">
            <div className="grid gap-4">
              {view.opportunities.map((opportunity) => (
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
              {view.prPlans.map((plan) => (
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
                    <div>
                      <span className="font-medium">Goal: </span>
                      <span className="text-muted-foreground">
                        {plan.bodySections.goal}
                      </span>
                    </div>
                    <div>
                      <span className="font-medium">Evidence: </span>
                      <span className="text-muted-foreground">
                        {plan.bodySections.evidence}
                      </span>
                    </div>
                    <div>
                      <span className="font-medium">Verification: </span>
                      <span className="text-muted-foreground">
                        {plan.bodySections.verification}
                      </span>
                    </div>
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
      </div>
    </main>
  )
}

export default App
