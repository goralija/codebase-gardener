import { expect, test } from "@playwright/test"

test("loads the fixture-backed dashboard shell", async ({ page }) => {
  await page.goto("/")

  await expect(page.getByRole("heading", { name: "Codebase Gardener" })).toBeVisible()
  await expect(page.getByText("Repository Entropy Score")).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Archive stale seed specification" }).first()
  ).toBeVisible()
})
