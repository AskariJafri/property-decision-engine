import type { APIRequestContext, BrowserContext, Page } from "@playwright/test";

let counter = 0;

/** A fresh account per test, created through the real API so the session cookie lands in the browser. */
export async function signUp(page: Page): Promise<string> {
  counter += 1;
  const email = `e2e-${Date.now()}-${process.pid}-${counter}@example.com`;
  const response = await page.request.post("/api/v1/auth/signup", {
    data: { email, password: "correct horse battery" },
  });
  if (!response.ok()) throw new Error(`signup failed: ${response.status()} ${await response.text()}`);
  return email;
}

export async function csrf(context: BrowserContext): Promise<Record<string, string>> {
  const cookie = (await context.cookies()).find((c) => c.name === "pde_csrf");
  return { "X-CSRF-Token": cookie?.value ?? "" };
}

/** The same request the form sends, at a chosen price. */
export function analysisBody(priceDollars: number) {
  return {
    property: {
      purchase_price_cents: priceDollars * 100,
      jurisdiction: "ON/Toronto",
      property_kind: "detached",
      square_feet: 1450,
      year_built: 1998,
      bedrooms: 3,
      bathrooms: "2.5",
      has_parking: true,
    },
    buyer: {
      gross_annual_income_cents: 19_000_000,
      household_income_cents: 19_000_000,
      monthly_debt_payments_cents: 45_000,
      down_payment_cents: 12_000_000,
      available_savings_cents: 16_000_000,
      emergency_fund_cents: 1_500_000,
      first_time_buyer: true,
      residency_status: "citizen_or_pr",
    },
    terms: { contract_rate: "0.0409", amortization_years: 25 },
  };
}

export async function analyzeViaApi(
  request: APIRequestContext,
  context: BrowserContext,
  priceDollars: number,
): Promise<string> {
  const response = await request.post("/api/v1/properties/analyze", {
    data: analysisBody(priceDollars),
    headers: await csrf(context),
  });
  if (!response.ok()) throw new Error(`analyze failed: ${response.status()} ${await response.text()}`);
  return (await response.json()).analysis_id;
}
