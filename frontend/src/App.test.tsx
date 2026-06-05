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
  it("renders first-report fixture data", async () => {
    renderApp()

    expect(
      await screen.findByRole("heading", { name: "Codebase Gardener" })
    ).toBeInTheDocument()
    expect(screen.getByText("34")).toBeInTheDocument()
    expect(screen.getAllByText("Archive stale seed specification")).toHaveLength(2)
  })
})
