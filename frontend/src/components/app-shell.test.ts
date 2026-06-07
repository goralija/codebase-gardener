import { describe, expect, it } from "vitest"

import { NAV_ITEMS } from "./app-nav"

describe("AppShell navigation", () => {
  it("keeps global navigation repository-agnostic", () => {
    expect(NAV_ITEMS.map((item) => item.label)).toEqual([
      "Overview",
      "Automation",
      "GitHub",
    ])
    expect(NAV_ITEMS.some((item) => item.to === "/report")).toBe(false)
  })
})
