import { describe, expect, it, vi } from "vitest"

import automationSettingsFixture from "../../../../fixtures/contracts/repository_automation_settings.json"
import {
  AutomationContractError,
  AutomationRequestError,
  fetchRepositoryAutomation,
  parseRepositoryAutomationResponse,
  triggerRepositorySession,
  updateRepositoryAutomation,
} from "./automation-api"

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
    },
    status: 200,
    ...init,
  })
}

function fetcherReturning(response: Response) {
  return vi.fn(async () => response) as unknown as typeof fetch
}

describe("automation API", () => {
  it("fetches repository automation with credentials enabled", async () => {
    const fetcher = fetcherReturning(jsonResponse(automationPayload()))

    await expect(
      fetchRepositoryAutomation("org-1", "repo-1", { fetcher })
    ).resolves.toMatchObject({
      policy: {
        autonomy_mode: "conservative",
        commit_threshold: 10,
      },
      effective: {
        can_create_autonomous_prs: false,
      },
    })

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/organizations/org-1/repositories/repo-1/automation/"
      ),
      expect.objectContaining({
        credentials: "include",
        headers: { Accept: "application/json" },
        method: "GET",
      })
    )
  })

  it("parses the shared repository automation settings fixture", () => {
    expect(parseRepositoryAutomationResponse(automationSettingsFixture)).toMatchObject({
      schema_version: "1.0",
      policy: {
        autonomy_mode: "conservative",
      },
    })
  })

  it("updates repository automation with a CSRF token", async () => {
    document.cookie = "csrftoken=test-token"
    const fetcher = fetcherReturning(jsonResponse(automationPayload()))

    await updateRepositoryAutomation(
      "org-1",
      "repo-1",
      { scheduled_trigger_enabled: false, commit_threshold: 3 },
      { fetcher }
    )

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/organizations/org-1/repositories/repo-1/automation/"
      ),
      expect.objectContaining({
        body: JSON.stringify({
          scheduled_trigger_enabled: false,
          commit_threshold: 3,
        }),
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRFToken": "test-token",
        }),
        method: "PATCH",
      })
    )
    document.cookie = "csrftoken=; Max-Age=0"
  })

  it("triggers a manual session", async () => {
    const fetcher = fetcherReturning(
      jsonResponse({
        trigger: {
          gardening_session_id: "session-1",
          status: "queued",
          deduped: false,
        },
      })
    )

    await expect(
      triggerRepositorySession("org-1", "repo-1", { fetcher })
    ).resolves.toMatchObject({
      trigger: {
        gardening_session_id: "session-1",
      },
    })

    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/organizations/org-1/repositories/repo-1/automation/trigger/"
      ),
      expect.objectContaining({
        body: JSON.stringify({}),
        method: "POST",
      })
    )
  })

  it("rejects failures and contract drift", async () => {
    await expect(
      fetchRepositoryAutomation("org-1", "repo-1", {
        fetcher: fetcherReturning(new Response(null, { status: 403 })),
      })
    ).rejects.toBeInstanceOf(AutomationRequestError)

    expect(() => parseRepositoryAutomationResponse({ policy: {} })).toThrow()

    await expect(
      fetchRepositoryAutomation("org-1", "repo-1", {
        fetcher: fetcherReturning(
          new Response("not json", {
            headers: { "Content-Type": "application/json" },
            status: 200,
          })
        ),
      })
    ).rejects.toBeInstanceOf(AutomationContractError)
  })
})

export function automationPayload() {
  return {
    schema_version: "1.0",
    repository: {
      id: "repo-1",
      full_name: "acme/api",
      default_branch: "main",
      html_url: "https://github.com/acme/api",
    },
    baseline: {
      analysis_id: "analysis-1",
      commit_sha: "abc123baseline",
      source: "first_scan",
      promoted_at: "2026-06-06T08:00:00Z",
    },
    policy: {
      id: "policy-1",
      autonomy_mode: "conservative",
      manual_trigger_enabled: true,
      scheduled_trigger_enabled: false,
      commit_trigger_enabled: false,
      risky_module_trigger_enabled: false,
      pr_opened_trigger_enabled: false,
      ci_failure_trigger_enabled: false,
      commit_threshold: 10,
      created_at: "2026-06-06T08:00:00Z",
      updated_at: "2026-06-06T08:00:00Z",
    },
    effective: {
      autonomous_pr_add_on_enabled: true,
      can_create_autonomous_prs: false,
      pr_creation_status:
        "Repository autonomy mode is Conservative; sessions report recommendations without PR creation.",
      default_commit_threshold: 10,
      confidence_threshold: 0.9,
    },
    permissions: {
      can_edit: true,
      can_trigger_manual_session: true,
    },
    recent_sessions: [
      {
        id: "session-1",
        status: "completed",
        trigger: { type: "schedule" },
        baseline_analysis_id: "analysis-1",
        current_analysis_id: "analysis-2",
        current_commit_sha: "def456current",
        has_drift_report: true,
        created_at: "2026-06-06T08:00:00Z",
        started_at: "2026-06-06T08:01:00Z",
        finished_at: "2026-06-06T08:02:00Z",
        last_error: "",
      },
    ],
    recent_pr_plans: [
      {
        id: "plan-1",
        title: "Refresh docs",
        blocked: false,
        block_reason: null,
        approval_status: "approved",
        execution_status: "succeeded",
        created_pr_url: "https://github.com/acme/api/pull/1",
        terminal_outcome: "merged",
        terminal_outcome_at: "2026-06-06T09:00:00Z",
        confidence: 0.94,
        confidence_threshold: 0.9,
        created_at: "2026-06-06T08:02:00Z",
      },
    ],
  }
}
