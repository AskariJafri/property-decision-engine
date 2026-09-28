"use client";

/**
 * The free analysis's plain-language layer: where each figure came from, what the
 * home means for the buyer's own budget, how rates move it, and what is still
 * unknown. Everything is rendered from the server's result; nothing is computed
 * here except formatting.
 */

import { formatCad } from "@/components/DataState";
import type { AnalyzeResponse, DataBasis, MissingItem, MonthlyLine } from "@/lib/api";
import { BASIS_LABELS } from "@/lib/copy";

const BASIS_STYLES: Record<DataBasis, string> = {
  known: "border-good/30 text-good",
  user_provided: "border-accent/30 text-accent",
  estimated: "border-caution/40 text-caution",
  assumption: "border-caution/40 text-caution",
  unavailable: "border-line text-muted",
};

/** KNOWN / ESTIMATED / USER-PROVIDED / ASSUMPTION, beside the figure it describes. */
export function DataLabel({ basis }: { basis: DataBasis }) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${BASIS_STYLES[basis]}`}
    >
      {BASIS_LABELS[basis] ?? basis}
    </span>
  );
}

export function DataLegend() {
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <DataLabel basis="known" /> from published rules and your inputs
      <DataLabel basis="user_provided" /> as you entered it
      <DataLabel basis="estimated" /> derived with a stated method
      <DataLabel basis="assumption" /> a planning default you can replace
    </p>
  );
}

function LineRow({ line }: { line: MonthlyLine }) {
  return (
    <li className="flex items-start justify-between gap-4 border-b border-line py-2">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm">{line.label}</span>
          <DataLabel basis={line.basis} />
        </div>
        {line.note && <p className="mt-0.5 max-w-prose text-xs text-muted">{line.note}</p>}
      </div>
      <span className="whitespace-nowrap text-sm tabular-nums">
        {line.amount_cents === null ? (
          <span className="italic text-muted">Unavailable</span>
        ) : (
          formatCad(line.amount_cents, true)
        )}
      </span>
    </li>
  );
}

export function MonthlyBreakdown({ result }: { result: AnalyzeResponse }) {
  if (!result.monthly_breakdown?.length) return null;
  return (
    <section>
      <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Monthly carrying cost</h2>
      <ul>
        {result.monthly_breakdown.map((line) => (
          <LineRow key={line.key} line={line} />
        ))}
        <li className="flex justify-between py-2 font-semibold">
          <span className="text-sm">Total per month</span>
          <span className="text-sm tabular-nums">
            {formatCad(result.money.monthly_ownership_cost_cents, true)}
          </span>
        </li>
      </ul>
      <div className="mt-2">
        <DataLegend />
      </div>
    </section>
  );
}

export function PersonalFitSection({ result }: { result: AnalyzeResponse }) {
  const fit = result.personal;
  if (!fit) return null;
  return (
    <section>
      <h2 className="mb-1 text-sm uppercase tracking-wide text-muted">
        How this property fits your situation
      </h2>
      <p className="mb-2 text-xs text-muted">{fit.note}</p>
      <ul>
        {fit.lines.map((line) => (
          <LineRow key={line.key} line={line} />
        ))}
      </ul>
      <p className="mt-2 text-sm tabular-nums text-muted">
        Housing would be {(fit.housing_share_of_gross * 100).toFixed(1)}% of gross income
        {fit.emergency_months !== null &&
          ` · your emergency fund covers about ${fit.emergency_months.toFixed(1)} months of housing and debt payments`}
        .
      </p>
    </section>
  );
}

export function RateScenarios({ result }: { result: AnalyzeResponse }) {
  if (!result.rate_scenarios?.length) return null;
  return (
    <section>
      <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">If rates were higher</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm tabular-nums">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-1 pr-4 font-normal">Rate</th>
              <th className="py-1 pr-4 font-normal">Mortgage payment</th>
              <th className="py-1 pr-4 font-normal">Monthly carrying cost</th>
              <th className="py-1 font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            {result.rate_scenarios.map((row, index) => (
              <tr key={row.rate} className="border-t border-line">
                <td className="py-1.5 pr-4">
                  {(row.rate * 100).toFixed(2)}%{index === 0 ? " (yours)" : ""}
                </td>
                <td className="py-1.5 pr-4">{formatCad(row.monthly_payment_cents, true)}</td>
                <td className="py-1.5 pr-4">{formatCad(row.monthly_ownership_cost_cents, true)}</td>
                <td className="py-1.5">
                  {row.change_cents === 0 ? "—" : `+${formatCad(row.change_cents, true)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-muted">
        Same price, down payment and amortization; only the rate changes. Renewal rates are
        unknown — this shows the sensitivity, not a forecast.
      </p>
    </section>
  );
}

const SEVERITY: Record<MissingItem["severity"], string> = {
  high: "text-alarm",
  medium: "text-caution",
  low: "text-muted",
};

export function MissingInfo({ items }: { items: MissingItem[] }) {
  if (!items?.length) return null;
  return (
    <section>
      <h2 className="mb-1 text-sm uppercase tracking-wide text-muted">
        Things to investigate before making an offer
      </h2>
      <p className="mb-3 max-w-prose text-xs text-muted">
        What this analysis could not know. Nothing here is assumed about the home — each item
        is a question worth asking.
      </p>
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.key} className="rounded border border-line p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium">{item.title}</span>
              <span className={`text-[10px] uppercase tracking-wide ${SEVERITY[item.severity]}`}>
                {item.severity} priority
              </span>
            </div>
            <p className="mt-1 text-sm">
              <span className="text-xs uppercase tracking-wide text-muted">Why it matters · </span>
              {item.why_it_matters}
            </p>
            <p className="mt-1 text-sm">
              <span className="text-xs uppercase tracking-wide text-muted">What to ask for · </span>
              {item.what_to_ask_for}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
