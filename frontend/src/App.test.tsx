import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import firstReportFixture from "../../fixtures/contracts/first_report_fixture.json"
import App from "@/App.tsx"

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
    },
    status: 200,
    ...init,
  })
}

function mockFirstReportResponse(response: Response | Promise<Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response)
  )
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  )
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders the required first-report dashboard sections from the API", async () => {
    mockFirstReportResponse(jsonResponse(firstReportFixture))

    renderApp()

    expect(
      await screen.findByRole("heading", { name: "First report" })
    ).toBeInTheDocument()
    expect(screen.getByText("Repository Entropy Score")).toBeInTheDocument()
    expect(screen.getByText("Constitution Coverage")).toBeInTheDocument()
    expect(screen.getAllByText("Session Status")).toHaveLength(1)
    expect(
      screen.getByRole("heading", { name: "Architecture violations" })
    ).toBeInTheDocument()
    expect(screen.getByText(/No architecture violations/)).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Constitution questions" })
    ).toBeInTheDocument()
    expect(
      screen.getByText("No open constitution questions in this report.")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Session status" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Maintenance opportunities" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Focused PR plans" })
    ).toBeInTheDocument()
    expect(
      screen.getAllByText("Archive stale seed specification")
    ).toHaveLength(2)
    expect(
      screen.getByText("gardener/docs-archive-seed-spec")
    ).toBeInTheDocument()
  })

  it("shows a loading state while the first report is requested", async () => {
    let resolveResponse: (response: Response) => void
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveResponse = resolve
    })
    mockFirstReportResponse(pendingResponse)

    renderApp()

    expect(
      screen.getByRole("heading", { name: "Loading first report" })
    ).toBeInTheDocument()

    resolveResponse!(jsonResponse(firstReportFixture))
    expect(
      await screen.findByRole("heading", { name: "First report" })
    ).toBeInTheDocument()
  })

  it("shows the first-report empty state for a 404 response", async () => {
    mockFirstReportResponse(
      jsonResponse(
        {
          code: "not_found",
          message: "First report not found.",
          details: {},
        },
        { status: 404 }
      )
    )

    renderApp()

    expect(
      await screen.findByRole("heading", {
        name: "First report is not ready",
      })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Retry first report" })
    ).toBeInTheDocument()
  })

  it("shows the first-report error state for invalid API data", async () => {
    mockFirstReportResponse(jsonResponse({ repository_constitution: {} }))

    renderApp()

    expect(
      await screen.findByRole("heading", {
        name: "Could not load first report",
      })
    ).toBeInTheDocument()
    expect(
      screen.getByText(/does not match the shared contract/)
    ).toBeInTheDocument()
  })
})
