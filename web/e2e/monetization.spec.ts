import { expect, test } from "@playwright/test";

import { analyzeViaApi, signUp } from "./helpers";

test.describe("landing and accounts", () => {
  test("the landing page states the offer and leads to a free analysis", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", {
        name: /before you make an offer, know what this home will really cost you/i,
      }),
    ).toBeVisible();
    await expect(page.getByText("5 free analyses. No credit card required.").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /built for canadian homebuyers/i })).toBeVisible();

    await page.getByRole("link", { name: "Analyze a Property — Free" }).first().click();
    await expect(page).toHaveURL(/\/analyze/);
    await expect(page.getByRole("link", { name: /create a free account/i })).toBeVisible();
  });

  test("sign up in the browser, analyse, and watch the counter move", async ({ page }) => {
    await page.goto("/signup?next=/analyze");
    await page.getByLabel("Email").fill(`e2e-ui-${Date.now()}@example.com`);
    await page.getByLabel("Password").fill("correct horse battery");
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page).toHaveURL(/\/analyze/);

    await expect(page.getByTestId("usage-meter").first()).toContainText("5 of 5 free analyses remaining");
    await page.getByRole("button", { name: /analyse this property/i }).click();
    await expect(page.getByTestId("buy-score")).toBeVisible();
    await expect(page.getByTestId("usage-meter").first()).toContainText("4 of 5 free analyses remaining");

    // The free result is genuinely useful: labelled costs, fit, gaps, and a Deep Dive offer.
    await expect(page.getByRole("heading", { name: "Monthly carrying cost" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /fits your situation/i })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /things to investigate before making an offer/i }),
    ).toBeVisible();
    await expect(page.getByText(/want the complete 10-year analysis/i)).toBeVisible();
  });
});

test.describe("free limit", () => {
  test("after five analyses the limit screen replaces the form, without a popup", async ({
    page,
    context,
  }) => {
    await signUp(page);
    for (let i = 0; i < 5; i++) await analyzeViaApi(page.request, context, 800_000 + i * 10_000);

    // The server refuses the sixth, whatever the page does.
    const refused = await page.request.post("/api/v1/properties/analyze", {
      data: {},
      headers: { "X-CSRF-Token": (await context.cookies()).find((c) => c.name === "pde_csrf")!.value },
    });
    expect([402, 422]).toContain(refused.status());

    await page.goto("/analyze");
    const limit = page.getByTestId("limit-reached");
    await expect(limit).toBeVisible();
    await expect(limit).toContainText("You've used your 5 free property analyses.");
    await expect(limit).toContainText("Continue analyzing properties with Property Decision Engine.");
    for (const option of ["Deep Dive Report", "Property Watch", "Professional", "Upgrade"]) {
      await expect(limit.getByText(option, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByRole("button", { name: /analyse this property/i })).toBeDisabled();
  });
});

test.describe("derived views", () => {
  test("offer scenarios, comparison and a locked Deep Dive", async ({ page, context }) => {
    await signUp(page);
    const a = await analyzeViaApi(page.request, context, 850_000);
    const b = await analyzeViaApi(page.request, context, 925_000);

    await page.goto(`/analyses/${a}/offers`);
    await page.getByRole("button", { name: /compare these offers/i }).click();
    await expect(page.getByTestId("offer-scenario")).toHaveCount(3);
    await expect(page.getByText(/not a recommendation/i)).toBeVisible();

    await page.goto(`/compare?ids=${a},${b}`);
    await expect(page.getByTestId("comparison-table")).toBeVisible();
    await expect(page.getByRole("heading", { name: "How they differ" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Key trade-offs" })).toBeVisible();

    await page.goto(`/analyses/${a}/deep-dive`);
    await expect(page.getByTestId("deep-dive-locked")).toBeVisible();
    await expect(page.getByRole("button", { name: /unlock for \$9\.99 CAD/i })).toBeVisible();

    // Comparing and viewing cost nothing: still three left.
    const me = await (await page.request.get("/api/v1/me")).json();
    expect(me.usage.free_remaining).toBe(3);
  });

  test("checkout says plainly when payments are not configured", async ({ page, context }) => {
    await signUp(page);
    const a = await analyzeViaApi(page.request, context, 850_000);
    await page.goto(`/analyses/${a}/deep-dive`);
    await page.getByRole("button", { name: /unlock for/i }).click();
    await expect(page.getByText(/payments are not set up yet/i)).toBeVisible();
  });
});

test.describe("roles and ads", () => {
  test("an ordinary user cannot use the admin console", async ({ page }) => {
    await signUp(page);
    expect((await page.request.get("/api/v1/admin/overview")).status()).toBe(403);
    await page.goto("/admin");
    await expect(page.getByTestId("admin-forbidden")).toBeVisible();
  });

  test("ads are labelled and kept out of the figures", async ({ page, context }) => {
    await signUp(page);
    const a = await analyzeViaApi(page.request, context, 850_000);
    await page.goto(`/analyses/${a}`);
    await expect(page.getByRole("heading", { name: "What it costs" })).toBeVisible();

    const slots = page.locator("[data-ad-slot]");
    await expect(slots.first()).toBeVisible();
    for (const slot of await slots.all()) {
      await expect(slot.getByText("Advertisement")).toBeVisible();
    }
    // No ad inside the money panel.
    const costs = page.getByRole("heading", { name: "What it costs" }).locator("..");
    await expect(costs.locator("[data-ad-slot]")).toHaveCount(0);
  });
});

test.describe("mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("pages fit a phone without sideways scrolling", async ({ page, context }) => {
    await page.goto("/");
    const fits = () =>
      page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    expect(await fits()).toBe(true);

    await signUp(page);
    const a = await analyzeViaApi(page.request, context, 850_000);
    for (const path of ["/analyze", "/dashboard", `/analyses/${a}`, "/pricing"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      expect(await fits(), path).toBe(true);
    }
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  });
});
