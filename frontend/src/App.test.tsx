import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import App from "@/App.tsx"

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
  it("renders the required first-report dashboard sections", async () => {
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
})
