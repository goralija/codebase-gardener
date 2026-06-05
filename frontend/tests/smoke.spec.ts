import { expect, test } from "@playwright/test"

test("loads the fixture-backed dashboard shell", async ({ page }) => {
  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "First report" })
  ).toBeVisible()
  await expect(page.getByText("Repository Entropy Score")).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Architecture violations" })
  ).toBeVisible()
  await expect(page.getByText(/No architecture violations/)).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Constitution questions" })
  ).toBeVisible()
  await expect(
    page.getByText("No open constitution questions in this report.")
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Session status" })
  ).toBeVisible()
  await expect(
    page
      .getByRole("heading", { name: "Archive stale seed specification" })
      .first()
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Focused PR plans" })
  ).toBeVisible()
})
