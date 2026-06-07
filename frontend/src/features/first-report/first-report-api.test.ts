import { describe, expect, it, vi } from "vitest"

import firstReportFixture from "../../../../fixtures/contracts/first_report_fixture.json"
import {
  buildApiUrl,
  fetchFirstReport,
  FirstReportContractError,
  FirstReportNotReadyError,
  FirstReportRequestError,
} from "./first-report-api"

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

describe("first report API", () => {
  it("builds first-report URLs from the configured API base", () => {
    expect(buildApiUrl("/reports/first/", "http://localhost:8000/api/v1")).toBe(
      "http://localhost:8000/api/v1/reports/first/"
    )
    expect(buildApiUrl("reports/first/", "/api/v1/")).toBe(
      "/api/v1/reports/first/"
    )
  })

  it("fetches and validates the first-report contract", async () => {
    const fetcher = fetcherReturning(jsonResponse(firstReportFixture))

    await expect(
      fetchFirstReport({
        apiBaseUrl: "http://localhost:8000/api/v1",
        fetcher,
      })
    ).resolves.toMatchObject({
      entropy_report: {
        entropy_report_id: "entropy_demo",
      },
    })
  })

  it("fetches the promoted repository baseline report when requested", async () => {
    const fetcher = fetcherReturning(jsonResponse(firstReportFixture))

    await fetchFirstReport({
      apiBaseUrl: "/api/v1",
      baseline: true,
      fetcher,
      repositoryId: "repo-1",
    })

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/reports/repository/repo-1/baseline/",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      })
    )
  })

  it("treats 404 as first report not ready", async () => {
    await expect(
      fetchFirstReport({
        fetcher: fetcherReturning(new Response(null, { status: 404 })),
      })
    ).rejects.toBeInstanceOf(FirstReportNotReadyError)
  })

  it("treats non-404 failures as API request errors", async () => {
    await expect(
      fetchFirstReport({
        fetcher: fetcherReturning(
          jsonResponse(
            { code: "server_error", message: "Server error.", details: {} },
            { status: 500, statusText: "Server Error" }
          )
        ),
      })
    ).rejects.toBeInstanceOf(FirstReportRequestError)
  })

  it("rejects API responses that drift from the shared contract", async () => {
    const payload = {
      ...firstReportFixture,
      entropy_report: {
        ...firstReportFixture.entropy_report,
        score: undefined,
      },
    }

    await expect(
      fetchFirstReport({ fetcher: fetcherReturning(jsonResponse(payload)) })
    ).rejects.toBeInstanceOf(FirstReportContractError)
  })

  it("rejects unsupported shared contract versions", async () => {
    const payload = {
      ...firstReportFixture,
      entropy_report: {
        ...firstReportFixture.entropy_report,
        schema_version: "2.0",
      },
    }

    await expect(
      fetchFirstReport({ fetcher: fetcherReturning(jsonResponse(payload)) })
    ).rejects.toBeInstanceOf(FirstReportContractError)
  })

  it("rejects ratio fields outside the shared contract range", async () => {
    const payload = {
      ...firstReportFixture,
      repository_constitution: {
        ...firstReportFixture.repository_constitution,
        completeness_score: 1.1,
      },
    }

    await expect(
      fetchFirstReport({ fetcher: fetcherReturning(jsonResponse(payload)) })
    ).rejects.toBeInstanceOf(FirstReportContractError)
  })
})
