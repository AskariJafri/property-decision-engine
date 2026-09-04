"use client";

/**
 * One page: your situation, the property, and the answer.
 *
 * Progressive disclosure rather than fifty questions — the form asks for what the
 * engines actually consume and nothing else, and every field that is missing shows
 * up in "what we could not check" rather than being silently defaulted.
 */

import { useState } from "react";

import { Factors, Money, NotChecked, BuyScore, ScoreBreakdown, Working } from "@/components/Analysis";
import { analyze, type AnalyzeResponse } from "@/lib/api";

const DOLLARS = (value: string) => Math.round(Number(value.replace(/[^0-9.]/g, "")) * 100);

const INITIAL = {
  price: "850000",
  jurisdiction: "ON/Toronto",
  kind: "detached",
  squareFeet: "1450",
  yearBuilt: "1998",
  bedrooms: "3",
  income: "190000",
  debts: "450",
  down: "120000",
  savings: "160000",
  emergency: "15000",
  budget: "6000",
  firstTime: true,
  rate: "4.09",
  amortization: "25",
  minBedrooms: "3",
  maxCommute: "45",
  commute: "38",
};

export default function Home() {
  const [form, setForm] = useState(INITIAL);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof INITIAL) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: event.target.value });

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(
        await analyze({
          property: {
            purchase_price_cents: DOLLARS(form.price),
            jurisdiction: form.jurisdiction,
            property_kind: form.kind,
            square_feet: Number(form.squareFeet) || null,
            year_built: Number(form.yearBuilt) || null,
            bedrooms: Number(form.bedrooms) || null,
            has_parking: true,
          },
          buyer: {
            gross_annual_income_cents: DOLLARS(form.income),
            household_income_cents: DOLLARS(form.income),
            monthly_debt_payments_cents: DOLLARS(form.debts),
            down_payment_cents: DOLLARS(form.down),
            available_savings_cents: DOLLARS(form.savings),
            emergency_fund_cents: DOLLARS(form.emergency),
            desired_max_monthly_cents: DOLLARS(form.budget),
            first_time_buyer: form.firstTime,
            residency_status: "citizen_or_pr",
          },
          terms: {
            contract_rate: String(Number(form.rate) / 100),
            amortization_years: Number(form.amortization),
          },
          preferences: {
            min_bedrooms: Number(form.minBedrooms) || null,
            requires_parking: true,
            max_commute_minutes: Number(form.maxCommute) || null,
            commute_minutes: Number(form.commute) || null,
            goal: "primary_residence",
            time_horizon: "5_to_10",
            risk_posture: "balanced",
          },
          comparables: [],
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <form onSubmit={onSubmit} className="space-y-6">
        <p className="max-w-prose text-muted">
          Give us the property and your situation. Every number below is computed, sourced and
          shown with its working — and anything we cannot determine is named rather than guessed.
        </p>

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="text-sm uppercase tracking-wide text-muted mb-2">The property</legend>
          <Field label="Asking price" value={form.price} onChange={set("price")} />
          <Field label="Square feet" value={form.squareFeet} onChange={set("squareFeet")} />
          <Field label="Year built" value={form.yearBuilt} onChange={set("yearBuilt")} />
          <Field label="Bedrooms" value={form.bedrooms} onChange={set("bedrooms")} />
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="text-sm uppercase tracking-wide text-muted mb-2">
            Your situation
          </legend>
          <Field label="Household income" value={form.income} onChange={set("income")} />
          <Field label="Down payment" value={form.down} onChange={set("down")} />
          <Field label="Savings available" value={form.savings} onChange={set("savings")} />
          <Field label="Monthly debts" value={form.debts} onChange={set("debts")} />
          <Field label="Emergency fund" value={form.emergency} onChange={set("emergency")} />
          <Field label="Max monthly budget" value={form.budget} onChange={set("budget")} />
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="text-sm uppercase tracking-wide text-muted mb-2">The mortgage</legend>
          <Field label="Rate (%)" value={form.rate} onChange={set("rate")} />
          <Field label="Amortization (years)" value={form.amortization} onChange={set("amortization")} />
          <label className="flex items-end gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.firstTime}
              onChange={(event) => setForm({ ...form, firstTime: event.target.checked })}
            />
            First-time buyer
          </label>
        </fieldset>

        <button
          type="submit"
          disabled={busy}
          className="bg-accent text-white px-5 py-2 rounded disabled:opacity-50"
        >
          {busy ? "Analysing…" : "Analyse this property"}
        </button>

        {error && <p className="text-alarm text-sm">{error}</p>}
      </form>

      {result && (
        <div className="space-y-8">
          <BuyScore result={result} />
          <Money result={result} />
          <Factors result={result} />
          <ScoreBreakdown scores={result.scores} />
          <NotChecked result={result} />
          <Working result={result} />
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <input
        value={value}
        onChange={onChange}
        inputMode="decimal"
        className="border border-line rounded px-3 py-2 tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
    </label>
  );
}
