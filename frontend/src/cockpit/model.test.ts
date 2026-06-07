import { describe, expect, it } from "vitest"

import firstReportFixture from "../../../fixtures/contracts/first_report_fixture.json"
import automationFixture from "../../../fixtures/contracts/repository_automation_settings.json"
import { parseRepositoryAutomationResponse } from "@/features/automation/automation-api"
import {
  parseFirstReport,
  type FirstReport,
} from "@/features/first-report/first-report-contract"
import {
  constitutionFromReport,
  oppsFromReport,
  plansFromReport,
  systemsFromReport,
} from "./model"

function reportWith(overrides: Partial<FirstReport>): FirstReport {
  return parseFirstReport({
    ...firstReportFixture,
    ...overrides,
  })
}

describe("cockpit model mapping", () => {
  it("marks logical systems protected when glob prefixes overlap", () => {
    const report = parseFirstReport(firstReportFixture)

    const systems = systemsFromReport(report)

    expect(systems.find((system) => system.name === "Backend")?.protected).toBe(
      true
    )
  })

  it("keeps PR execution state from automation when report has plan details", () => {
    const automation = parseRepositoryAutomationResponse({
      ...automationFixture,
      recent_pr_plans: [
        {
          ...automationFixture.recent_pr_plans[0],
          created_pr_url: "https://github.com/acme/api/pull/99",
          terminal_outcome: null,
          terminal_outcome_at: null,
        },
      ],
    })
    const report = parseFirstReport(firstReportFixture)

    const plans = plansFromReport(report, automation)

    expect(plans[0]).toMatchObject({
      confidenceFloor: 90,
      prUrl: "https://github.com/acme/api/pull/99",
      status: "open",
    })
  })

  it("keeps PR blocked state from automation when report has plan details", () => {
    const automation = parseRepositoryAutomationResponse({
      ...automationFixture,
      recent_pr_plans: [
        {
          ...automationFixture.recent_pr_plans[0],
          block_reason: "Protected path changed.",
          blocked: true,
          created_pr_url: null,
          terminal_outcome: null,
          terminal_outcome_at: null,
        },
      ],
    })
    const report = parseFirstReport(firstReportFixture)

    const plans = plansFromReport(report, automation)

    expect(plans[0]).toMatchObject({
      blocked: "Protected path changed.",
      status: "blocked",
    })
  })

  it("falls back to effective confidence threshold when plan threshold is absent", () => {
    const planWithoutThreshold = {
      ...firstReportFixture.maintenance_pr_plans[0],
    }
    delete planWithoutThreshold.confidence_threshold
    const automation = parseRepositoryAutomationResponse({
      ...automationFixture,
      effective: {
        ...automationFixture.effective,
        confidence_threshold: 0.95,
      },
      recent_pr_plans: [],
    })
    const report = reportWith({
      maintenance_pr_plans: [planWithoutThreshold],
    })

    const plans = plansFromReport(report, automation)

    expect(plans[0].confidenceFloor).toBe(95)
  })

  it("uses automation confidence threshold for opportunities", () => {
    const automation = parseRepositoryAutomationResponse({
      ...automationFixture,
      effective: {
        ...automationFixture.effective,
        confidence_threshold: 0.95,
      },
    })
    const report = parseFirstReport(firstReportFixture)

    const opportunities = oppsFromReport(report, automation)

    expect(opportunities[0].confidence).toBe(94)
    expect(opportunities[0].confidenceFloor).toBe(95)
  })

  it("does not label an empty normalized constitution as source truth", () => {
    const report = reportWith({
      repository_constitution: {
        ...firstReportFixture.repository_constitution,
        allowed_fixes: {
          advisory: [],
          assisted: [],
          autonomous: [],
        },
        completeness_score: 0,
        protected_modules: [],
      },
    })

    const constitution = constitutionFromReport(report)

    expect(constitution.hasSourceTruth).toBe(false)
  })
})
