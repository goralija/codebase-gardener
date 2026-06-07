import { describe, expect, it } from "vitest"

import firstReportFixture from "../../../../fixtures/contracts/first_report_fixture.json"
import { parseFirstReport } from "./first-report-contract"
import {
  buildFirstReportViewModel,
  formatConfidence,
  formatDuration,
  formatEntropyDelta,
  type FirstReportFixture,
} from "./first-report-view-model"

describe("first report view model", () => {
  it("formats report-level metrics and empty states from the fixture", () => {
    const view = buildFirstReportViewModel(firstReportFixture)

    expect(view.entropy.overall).toBe("34")
    expect(view.entropy.classification).toBe("Warning")
    expect(view.entropy.forecast.confidence).toBe("62%")
    expect(view.architecture.hasViolations).toBe(false)
    expect(view.architecture.violationCount).toBe(0)
    expect(view.constitution.completeness).toBe("78%")
    expect(view.constitution.openQuestionCount).toBe(0)
    expect(view.session.status).toBe("Completed")
    expect(view.session.duration).toBe("8 min")
    expect(view.opportunities).toHaveLength(1)
    expect(view.opportunities[0]).toMatchObject({
      title: "Archive stale seed specification",
      confidence: "94%",
      expectedEntropyDelta: "-2.1",
    })
    expect(view.prPlans[0]).toMatchObject({
      title: "Archive stale seed specification",
      branchName: "gardener/docs-archive-seed-spec",
      blocked: false,
    })
  })

  it("formats shared dashboard values consistently", () => {
    expect(formatConfidence(0.945)).toBe("95%")
    expect(formatEntropyDelta(2)).toBe("+2")
    expect(formatEntropyDelta(-2.1)).toBe("-2.1")
    expect(formatDuration("2026-06-05T12:00:00Z", "2026-06-05T12:00:42Z")).toBe(
      "42 sec"
    )
  })

  it("does not count constitution boundary rules as violations", () => {
    const report = {
      ...firstReportFixture,
      repository_constitution: {
        ...firstReportFixture.repository_constitution,
        architecture_boundaries: [
          {
            rule_id: "arch_001",
            description:
              "Frontend must not import backend persistence modules.",
            forbidden_from: ["frontend/src/**"],
            forbidden_to: ["backend/apps/**/models.py"],
            evidence: [],
          },
        ],
      },
    } as FirstReportFixture

    const view = buildFirstReportViewModel(report)

    expect(view.architecture.boundaryRuleCount).toBe(1)
    expect(view.architecture.violationCount).toBe(0)
    expect(view.architecture.hasViolations).toBe(false)
  })

  it("accepts real session trigger metadata without an actor", () => {
    const report = {
      ...firstReportFixture,
      gardening_session_result: {
        ...firstReportFixture.gardening_session_result,
        trigger: {
          type: "manual",
          source: "manual",
          source_view: "repository_automation",
          subject_type: "manual",
          subject_id: "user-1",
        },
      },
    }

    const parsed = parseFirstReport(report)
    const view = buildFirstReportViewModel(parsed)

    expect(view.session.trigger).toBe("Manual")
    expect(view.session.actor).toBe("system")
  })

  it("surfaces entropy contributors and constitution questions", () => {
    const report = {
      ...firstReportFixture,
      repository_constitution: {
        ...firstReportFixture.repository_constitution,
        open_questions: [
          {
            question_id: "q_001",
            severity: "blocking",
            question: "Which modules are protected from autonomous refactors?",
            evidence: [
              {
                source_type: "file",
                path: "GARDENER.md",
                section: "Protected modules",
                line_start: 4,
                line_end: 8,
                summary: "Protected module ownership is incomplete.",
              },
            ],
          },
        ],
      },
      entropy_report: {
        ...firstReportFixture.entropy_report,
        top_contributors: [
          {
            kind: "testing_gap",
            summary: "Critical flows lack Playwright coverage.",
            impact: 5,
            evidence: [
              {
                source_type: "file",
                path: "docs/12-testing-strategy.md",
                section: "Required test areas",
                line_start: 20,
                line_end: 40,
                summary: "Dashboard flows need UI coverage.",
              },
            ],
          },
        ],
      },
    } as FirstReportFixture

    const view = buildFirstReportViewModel(report)

    expect(view.entropy.topContributors[0]).toMatchObject({
      kind: "Testing Gap",
      summary: "Critical flows lack Playwright coverage.",
      impact: "5",
      evidenceCount: 1,
      evidence: [
        {
          path: "docs/12-testing-strategy.md",
          summary: "Dashboard flows need UI coverage.",
        },
      ],
    })
    expect(view.constitution.openQuestions[0]).toMatchObject({
      severity: "Blocking",
      question: "Which modules are protected from autonomous refactors?",
      evidenceCount: 1,
      evidence: [
        {
          path: "GARDENER.md",
          summary: "Protected module ownership is incomplete.",
        },
      ],
    })
  })
})
