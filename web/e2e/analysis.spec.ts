import { expect, test } from "@playwright/test";

test.describe("analysis", () => {
  test("a complete analysis renders with its working", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /analyse this property/i }).click();

    // The score, and the verdict beside it. Targeted by test id rather than by
    // text: "marginal" also appears in the trace table's bracket formulas, and a
    // selector that loose would pass for the wrong reason.
    await expect(page.getByTestId("buy-score")).toBeVisible();
    await expect(page.getByTestId("verdict")).toHaveText(
      /strong fit|workable|marginal|poor fit/i,
    );

    // The money a buyer actually needs. Scoped to the summary panel, because the
    // same phrases appear again as step names inside the working table.
    const costs = page.getByRole("heading", { name: "What it costs" }).locator("..");
    await expect(costs.getByText("Monthly ownership cost")).toBeVisible();
    await expect(costs.getByText("Cash needed to close")).toBeVisible();

    // The qualification caveat travels with the number (COMPLIANCE.md §1).
    await expect(page.getByText(/only a lender or licensed mortgage broker/i)).toBeVisible();

    // Missing data is named, not hidden.
    await expect(page.getByRole("heading", { name: /what we could not check/i })).toBeVisible();
    await expect(page.getByText("Data unavailable").first()).toBeVisible();

    // And the arithmetic is inspectable.
    await expect(page.getByText(/show the working/i)).toBeVisible();
  });

  test("a fair value is always a range, never a point", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /analyse this property/i }).click();
    await expect(page.getByText(/\$[\d,]+ – \$[\d,]+/)).toBeVisible();
  });

  test("an impossible down payment is refused with a readable reason", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Down payment").fill("10000");
    await page.getByRole("button", { name: /analyse this property/i }).click();
    await expect(page.getByText(/below the .* minimum/i)).toBeVisible();
  });
});
