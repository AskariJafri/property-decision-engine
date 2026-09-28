"use client";

/**
 * Offer Scenarios: the financial consequences of each possible offer.
 *
 * It shows what each price means for the down payment, mortgage, cash and monthly
 * cost. It never suggests which to offer — that depends on the market, the
 * seller and the buyer, none of which a calculator can see.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { formatCad } from "@/components/DataState";
import { RequireAuth } from "@/components/RequireAuth";
import { ApiError, apiFetch, type SavedAnalysis } from "@/lib/api";

interface OfferRow {
  price_cents: number;
  difference_from_asking_cents: number;
  down_payment_cents: number;
  minimum_down_payment_cents: number;
  error?: string;
  mortgage_principal_cents?: number;
  insurance_premium_cents?: number;
  monthly_payment_cents?: number;
  closing_costs_cents?: number;
  cash_required_cents?: number;
  cash_shortfall_cents?: number;
  monthly_carrying_cost_cents?: number;
  may_qualify?: boolean;
  rate_sensitivity?: { rate: number; monthly_payment_cents: number; monthly_carrying_cost_cents: number }[];
}

interface OffersResponse {
  asking_price_cents: number;
  contract_rate: number;
  scenarios: OfferRow[];
  note: string;
}

const toCents = (value: string) => Math.round(Number(value.replace(/[^0-9.]/g, "")) * 100);

export default function OffersPage() {
  return <RequireAuth>{() => <Offers />}</RequireAuth>;
}

function Offers() {
  const { id } = useParams<{ id: string }>();
  const [analysis, setAnalysis] = useState<SavedAnalysis | null>(null);
  const [prices, setPrices] = useState<string[]>(["", "", ""]);
  const [mode, setMode] = useState<"same_amount" | "same_percent">("same_amount");
  const [result, setResult] = useState<OffersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch<SavedAnalysis>(`/analyses/${id}`)
      .then((a) => {
        setAnalysis(a);
        const asking = a.money.purchase_price_cents / 100;
        setPrices([asking * 0.97, asking, asking * 1.03].map((p) => String(Math.round(p / 1000) * 1000)));
      })
      .catch((caught: Error) => setError(caught.message));
  }, [id]);

  async function run(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const cents = prices.filter((p) => p.trim()).map(toCents).filter((c) => c > 0);
      setResult(
        await apiFetch<OffersResponse>(`/analyses/${id}/offers`, {
          body: { prices_cents: cents, down_payment_mode: mode },
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not run the scenarios.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/analyses/${id}`} className="text-sm text-muted hover:text-ink">
          ← Back to the analysis
        </Link>
        <h1 className="mt-2 text-xl font-semibold">Offer scenarios</h1>
        {analysis && (
          <p className="text-sm text-muted">
            {analysis.title} · asking {formatCad(analysis.money.purchase_price_cents)}
          </p>
        )}
      </div>

      <form onSubmit={run} className="space-y-4 rounded-lg border border-line p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {prices.map((price, index) => (
            <label key={index} className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wide text-muted">Offer {index + 1}</span>
              <input
                value={price}
                inputMode="decimal"
                onChange={(e) => setPrices(prices.map((p, i) => (i === index ? e.target.value : p)))}
                className="rounded border border-line px-3 py-2 tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          {prices.length < 6 && (
            <button type="button" onClick={() => setPrices([...prices, ""])} className="text-accent">
              + Add a price
            </button>
          )}
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === "same_amount"} onChange={() => setMode("same_amount")} />
            Keep my down payment amount
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === "same_percent"} onChange={() => setMode("same_percent")} />
            Keep my down payment percentage
          </label>
        </div>
        <button
          type="submit"
          disabled={busy || !analysis || !prices.some((p) => p.trim())}
          className="rounded bg-accent px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {busy ? "Calculating…" : "Compare these offers"}
        </button>
        <p className="text-xs text-muted">Uses no analysis credit.</p>
      </form>

      {error && <p className="text-sm text-alarm">{error}</p>}

      {result && (
        <section className="space-y-3">
          <p className="max-w-prose text-sm text-muted">{result.note}</p>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {result.scenarios.map((row) => (
              <div key={row.price_cents} className="rounded-lg border border-line p-4 text-sm" data-testid="offer-scenario">
                <p className="text-lg font-semibold tabular-nums">{formatCad(row.price_cents)}</p>
                <p className="text-xs text-muted tabular-nums">
                  {row.difference_from_asking_cents === 0
                    ? "At asking"
                    : `${formatCad(Math.abs(row.difference_from_asking_cents))} ${row.difference_from_asking_cents < 0 ? "below" : "above"} asking`}
                </p>
                {row.error ? (
                  <p className="mt-3 text-caution">{row.error}</p>
                ) : (
                  <dl className="mt-3 space-y-1 tabular-nums">
                    {(
                      [
                        ["Down payment", row.down_payment_cents],
                        ["Mortgage (incl. insurance)", row.mortgage_principal_cents],
                        ["CMHC premium", row.insurance_premium_cents],
                        ["Monthly payment", row.monthly_payment_cents],
                        ["Closing costs", row.closing_costs_cents],
                        ["Total cash required", row.cash_required_cents],
                        ["Monthly carrying cost", row.monthly_carrying_cost_cents],
                      ] as [string, number | undefined][]
                    ).map(([label, cents]) => (
                      <div key={label} className="flex justify-between gap-2 border-b border-line py-1">
                        <dt className="text-muted">{label}</dt>
                        <dd>{formatCad(cents)}</dd>
                      </div>
                    ))}
                    {(row.cash_shortfall_cents ?? 0) > 0 && (
                      <p className="pt-1 text-caution">
                        {formatCad(row.cash_shortfall_cents)} more cash than your savings on file.
                      </p>
                    )}
                    <p className="pt-2 text-xs text-muted">
                      If rates were higher:{" "}
                      {row.rate_sensitivity?.map((r) => `${(r.rate * 100).toFixed(2)}% → ${formatCad(r.monthly_payment_cents)}/mo`).join(" · ")}
                    </p>
                    <p className="text-xs text-muted">
                      Stress test: {row.may_qualify ? "likely to qualify" : "unlikely to qualify"} (estimate)
                    </p>
                  </dl>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
