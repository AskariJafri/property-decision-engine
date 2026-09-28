"use client";

/**
 * Compare Properties: side by side, how they differ, and the trade-offs.
 * Deliberately no "best" — the buyer's priorities decide which trade-off wins.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { formatCad } from "@/components/DataState";
import { RequireAuth } from "@/components/RequireAuth";
import { ApiError, apiFetch, type AnalysisSummary } from "@/lib/api";

interface Column {
  analysis_id: string;
  label: string;
  buy_score: number | null;
  purchase_price_cents: number;
  down_payment_cents: number;
  mortgage_principal_cents: number;
  monthly_payment_cents: number;
  monthly_property_tax_cents: number;
  property_tax_basis: string;
  monthly_condo_fee_cents: number;
  condo_fee_basis: string;
  monthly_insurance_cents: number;
  monthly_maintenance_cents: number;
  monthly_carrying_cost_cents: number;
  closing_costs_cents: number;
  cash_required_cents: number;
  five_year_outlay_cents: number;
  ten_year_outlay_cents: number;
  ten_year_equity: { rate: number; equity_after_sale_cents: number }[];
  risks: { category: string; explanation: string }[];
  negative_factors: string[];
  missing_info: string[];
}

interface Comparison {
  columns: Column[];
  differences: { metric: string; sentence: string }[];
  trade_offs: string[];
  notes: string[];
}

const ROWS: [string, keyof Column, (keyof Column)?][] = [
  ["Purchase price", "purchase_price_cents"],
  ["Down payment", "down_payment_cents"],
  ["Mortgage (incl. insurance)", "mortgage_principal_cents"],
  ["Monthly mortgage payment", "monthly_payment_cents"],
  ["Property tax / month", "monthly_property_tax_cents", "property_tax_basis"],
  ["Condo fee / month", "monthly_condo_fee_cents", "condo_fee_basis"],
  ["Insurance / month (assumption)", "monthly_insurance_cents"],
  ["Maintenance / month (assumption)", "monthly_maintenance_cents"],
  ["Monthly carrying cost", "monthly_carrying_cost_cents"],
  ["Closing costs", "closing_costs_cents"],
  ["Cash required upfront", "cash_required_cents"],
  ["5-year total outlay", "five_year_outlay_cents"],
  ["10-year total outlay", "ten_year_outlay_cents"],
];

export default function ComparePage() {
  return (
    <RequireAuth>
      {() => (
        <Suspense>
          <Compare />
        </Suspense>
      )}
    </RequireAuth>
  );
}

function Compare() {
  const params = useSearchParams();
  const [selected, setSelected] = useState<string[]>(
    (params.get("ids") ?? "").split(",").filter(Boolean),
  );
  const [available, setAvailable] = useState<AnalysisSummary[]>([]);
  const [max, setMax] = useState(5);
  const [result, setResult] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch<{ analyses: AnalysisSummary[]; usage: { compare_max: number } }>("/analyses")
      .then((body) => {
        setAvailable(body.analyses);
        setMax(body.usage.compare_max);
      })
      .catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => {
    if (selected.length < 2) {
      setResult(null);
      return;
    }
    setBusy(true);
    setError(null);
    apiFetch<Comparison>("/comparisons", { body: { analysis_ids: selected } })
      .then(setResult)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not compare."))
      .finally(() => setBusy(false));
  }, [selected]);

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : current.length < max ? [...current, id] : current,
    );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Compare properties</h1>
        <p className="text-sm text-muted">
          Choose 2–{max} properties you have analysed. Comparing never uses a credit.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {available.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => toggle(a.id)}
            className={`rounded-full border px-3 py-1 text-xs ${selected.includes(a.id) ? "border-accent bg-accent/10 text-accent" : "border-line text-muted"}`}
          >
            {a.title ?? "Property"} · {formatCad(a.purchase_price_cents)}
          </button>
        ))}
        {available.length === 0 && (
          <p className="text-sm text-muted">
            No analyses yet. <Link href="/analyze" className="text-accent">Analyze a property</Link> first.
          </p>
        )}
      </div>

      {error && <p className="text-sm text-alarm">{error}</p>}
      {busy && <p className="text-sm text-muted">Comparing…</p>}

      {result && (
        <>
          <section className="overflow-x-auto" data-testid="comparison-table">
            <table className="w-full min-w-[640px] text-sm tabular-nums">
              <thead>
                <tr className="text-left">
                  <th className="py-2 pr-4 text-xs font-normal uppercase tracking-wide text-muted"></th>
                  {result.columns.map((c) => (
                    <th key={c.analysis_id} className="py-2 pr-4 align-bottom font-medium">
                      <Link href={`/analyses/${c.analysis_id}`} className="hover:underline">
                        {c.label}
                      </Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map(([label, key, basisKey]) => (
                  <tr key={key} className="border-t border-line">
                    <td className="py-1.5 pr-4 text-muted">{label}</td>
                    {result.columns.map((c) => {
                      const basis = basisKey ? String(c[basisKey]) : null;
                      return (
                        <td key={c.analysis_id} className="py-1.5 pr-4">
                          {basis === "not_applicable"
                            ? "—"
                            : basis === "unavailable"
                              ? <span className="italic text-muted">Unavailable</span>
                              : formatCad(c[key] as number)}
                          {basis === "estimated" && <span className="ml-1 text-[10px] text-caution">est.</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr className="border-t border-line">
                  <td className="py-1.5 pr-4 text-muted">10-year equity after sale, by appreciation</td>
                  {result.columns.map((c) => (
                    <td key={c.analysis_id} className="py-1.5 pr-4 text-xs">
                      {c.ten_year_equity.map((e) => (
                        <div key={e.rate}>
                          {(e.rate * 100).toFixed(0)}%: {formatCad(e.equity_after_sale_cents)}
                        </div>
                      ))}
                    </td>
                  ))}
                </tr>
                <tr className="border-t border-line align-top">
                  <td className="py-1.5 pr-4 text-muted">Risk factors</td>
                  {result.columns.map((c) => (
                    <td key={c.analysis_id} className="py-1.5 pr-4 text-xs">
                      {[...c.negative_factors, ...c.risks.map((r) => r.explanation)].slice(0, 5).map((r) => (
                        <div key={r}>⚠ {r}</div>
                      ))}
                      {c.negative_factors.length + c.risks.length === 0 && <span className="text-muted">None flagged</span>}
                    </td>
                  ))}
                </tr>
                <tr className="border-t border-line align-top">
                  <td className="py-1.5 pr-4 text-muted">Missing information</td>
                  {result.columns.map((c) => (
                    <td key={c.analysis_id} className="py-1.5 pr-4 text-xs">
                      {c.missing_info.slice(0, 6).map((m) => (
                        <div key={m}>• {m}</div>
                      ))}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </section>

          <section className="grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">How they differ</h2>
              <ul className="space-y-2 text-sm">
                {result.differences.map((d) => (
                  <li key={d.metric}>{d.sentence}</li>
                ))}
                {result.differences.length === 0 && <li className="text-muted">No material differences.</li>}
              </ul>
            </div>
            <div>
              <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Key trade-offs</h2>
              <ul className="space-y-2 text-sm">
                {result.trade_offs.map((t) => (
                  <li key={t}>{t}</li>
                ))}
                {result.trade_offs.length === 0 && (
                  <li className="text-muted">No clear trade-offs — one does not cost more monthly while costing less upfront.</li>
                )}
              </ul>
            </div>
          </section>
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
            {result.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
