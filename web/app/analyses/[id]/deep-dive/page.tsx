"use client";

/**
 * The Deep Dive report. Printable: "Download PDF" uses the browser's own
 * print-to-PDF, with a print stylesheet that drops navigation and ads, so the
 * PDF is exactly the page the buyer read.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { formatCad } from "@/components/DataState";
import { DataLabel, DataLegend, MissingInfo } from "@/components/Insights";
import { priceLabel, useCheckout } from "@/components/Monetization";
import { LoadingOr, RequireAuth } from "@/components/RequireAuth";
import { useSession } from "@/components/Session";
import { ApiError, apiFetch, track, type DataBasis, type MissingItem } from "@/lib/api";
import { DISCLAIMER } from "@/lib/copy";

interface Outcome {
  rate: number;
  home_value_cents: number;
  selling_costs_cents: number;
  mortgage_balance_cents: number;
  equity_after_sale_cents: number;
  net_cost_cents: number;
  net_cost_with_opportunity_cents: number;
}
interface Horizon {
  years: number;
  mortgage_payments_cents: number;
  interest_paid_cents: number;
  principal_repaid_cents: number;
  mortgage_balance_cents: number;
  property_tax_cents: number;
  insurance_cents: number;
  condo_fees_cents: number;
  utilities_cents: number;
  maintenance_cents: number;
  carrying_costs_cents: number;
  total_outlay_cents: number;
  opportunity_cost_cents: number;
  outcomes: Outcome[];
}
interface CostBlock {
  monthly_cents: number;
  ten_year_cents: number;
  basis: DataBasis;
  growth: number;
  note?: string;
  applies?: boolean;
}
interface Report {
  title: string;
  as_of: string;
  summary: Record<string, number>;
  projection: {
    horizons: Horizon[];
    yearly: {
      year: number;
      interest_cents: number;
      principal_cents: number;
      balance_cents: number;
      carrying_costs_cents: number;
      cumulative_outlay_cents: number;
    }[];
  };
  rate_sensitivity: {
    rate: number;
    monthly_payment_cents: number;
    change_cents: number;
    five_year_interest_cents: number;
  }[];
  down_payment_scenarios: {
    label: string;
    is_yours: boolean;
    down_payment_cents: number;
    down_payment_share: number;
    insurance_premium_cents: number;
    mortgage_principal_cents: number;
    monthly_payment_cents: number;
    monthly_carrying_cost_cents: number;
    cash_required_cents: number;
    five_year_interest_cents: number;
  }[];
  closing_costs: {
    lines: { key: string; label: string; amount_cents: number; basis: DataBasis }[];
    total_cents: number;
  };
  opportunity_cost: {
    upfront_cents: number;
    assumed_return: number;
    five_year_cents: number;
    ten_year_cents: number;
    note: string;
  };
  property_tax: CostBlock;
  condo_fee: CostBlock;
  insurance: CostBlock;
  maintenance: CostBlock;
  cash_flow: {
    monthly_breakdown: { key: string; label: string; amount_cents: number | null; basis: DataBasis }[];
    personal: { lines: { key: string; label: string; amount_cents: number | null; basis: DataBasis }[] } | null;
  };
  risk: {
    qualification: {
      may_qualify: boolean;
      gds: number;
      tds: number;
      gds_limit: number;
      tds_limit: number;
      stressed_rate: number;
      disclaimer: string;
    } | null;
    risks: { category: string; status: string; severity: string; explanation: string }[];
    negative_factors: { sentence: string }[];
  };
  missing_info: MissingItem[];
  questions: string[];
  assumptions: { key: string; label: string; value: string; basis: DataBasis; rationale?: string }[];
  notes: string[];
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export default function DeepDivePage() {
  return <RequireAuth>{() => <DeepDive />}</RequireAuth>;
}

function DeepDive() {
  const { id } = useParams<{ id: string }>();
  const { config } = useSession();
  const [report, setReport] = useState<Report | null>(null);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { busy, error: checkoutError, buy } = useCheckout();

  useEffect(() => {
    track("deep_dive_viewed");
    apiFetch<Report>(`/analyses/${id}/deep-dive`)
      .then(setReport)
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.status === 402) setLocked(true);
        else setError(caught instanceof Error ? caught.message : "Could not load the report.");
      });
  }, [id]);

  if (locked) {
    const product = config?.products.find((p) => p.key === "deep_dive");
    return (
      <section className="mx-auto max-w-2xl rounded-lg border border-line p-6" data-testid="deep-dive-locked">
        <Link href={`/analyses/${id}`} className="text-sm text-muted hover:text-ink">
          ← Back to the analysis
        </Link>
        <h1 className="mt-3 text-xl font-semibold">Deep Dive Report</h1>
        <p className="mt-2 text-sm text-muted">
          The complete ownership picture for this property, built from the same inputs and
          rules as your free analysis:
        </p>
        <ul className="mt-3 grid gap-1 text-sm sm:grid-cols-2">
          {[
            "5- and 10-year ownership projections",
            "Resale and appreciation scenarios, including none",
            "Interest-rate sensitivity",
            "Down-payment scenarios",
            "Closing-cost breakdown",
            "Opportunity cost of the down payment",
            "Property tax, condo fee, insurance and maintenance impact",
            "Monthly cash flow and risk analysis",
            "Missing-information checklist and questions to ask",
            "Every assumption labelled, and a PDF",
          ].map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-good" aria-hidden>
                ✓
              </span>
              {item}
            </li>
          ))}
        </ul>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => {
              track("upgrade_clicked", { from: "deep_dive_locked" });
              buy("deep_dive", id);
            }}
            className="rounded bg-accent px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {busy ? "Opening checkout…" : `Unlock for ${product ? priceLabel(product) : "…"}`}
          </button>
          <Link href="/pricing" className="text-sm text-accent hover:underline">
            Professional includes every Deep Dive
          </Link>
        </div>
        {checkoutError && <p className="mt-3 text-sm text-caution">{checkoutError}</p>}
        <p className="mt-4 text-xs text-muted">
          Payment is handled on Stripe&apos;s secure page. The report unlocks once Stripe confirms
          the payment.
        </p>
      </section>
    );
  }

  return (
    <LoadingOr error={error} ready={report !== null}>
      {report && <ReportView report={report} id={id} />}
    </LoadingOr>
  );
}

function Money({ cents }: { cents: number | null | undefined }) {
  return <span className="tabular-nums">{formatCad(cents)}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid">
      <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">{title}</h2>
      {children}
    </section>
  );
}

function ReportView({ report, id }: { report: Report; id: string }) {
  const s = report.summary;
  return (
    <article className="space-y-10" data-testid="deep-dive-report">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href={`/analyses/${id}`} className="text-sm text-muted hover:text-ink print:hidden">
            ← Back to the analysis
          </Link>
          <p className="mt-2 text-xs uppercase tracking-widest text-accent">Deep Dive Report</p>
          <h1 className="text-2xl font-semibold">{report.title}</h1>
          <p className="text-xs text-muted">Rules and prices as of {report.as_of}</p>
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded border border-line px-3 py-1.5 text-sm print:hidden"
        >
          Download PDF
        </button>
      </div>

      <DataLegend />

      <Section title="Summary">
        <dl className="grid gap-3 sm:grid-cols-4">
          {[
            ["Purchase price", s.purchase_price_cents, "user_provided"],
            ["Down payment", s.down_payment_cents, "user_provided"],
            ["Mortgage (incl. insurance)", s.mortgage_principal_cents, "known"],
            ["Monthly payment", s.monthly_payment_cents, "known"],
            ["Monthly carrying cost", s.monthly_carrying_cost_cents, "estimated"],
            ["Closing costs", s.closing_costs_cents, "estimated"],
            ["Cash required upfront", s.cash_required_cents, "estimated"],
          ].map(([label, cents, basis]) => (
            <div key={label as string} className="border-b border-line pb-2">
              <dt className="flex items-center gap-2 text-xs text-muted">
                {label} <DataLabel basis={basis as DataBasis} />
              </dt>
              <dd className="text-lg">
                <Money cents={cents as number} />
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-xs text-muted">
          At {(s.contract_rate * 100).toFixed(2)}% over {s.amortization_years} years.
        </p>
      </Section>

      <Section title="Total cost of ownership">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-1 font-normal"></th>
                {report.projection.horizons.map((h) => (
                  <th key={h.years} className="py-1 font-normal">
                    {h.years} years
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["Mortgage payments", "mortgage_payments_cents"],
                  ["  of which interest", "interest_paid_cents"],
                  ["  of which principal (your equity)", "principal_repaid_cents"],
                  ["Property tax", "property_tax_cents"],
                  ["Insurance", "insurance_cents"],
                  ["Condo fees", "condo_fees_cents"],
                  ["Utilities", "utilities_cents"],
                  ["Maintenance", "maintenance_cents"],
                  ["Total paid out, incl. down payment and closing", "total_outlay_cents"],
                  ["Mortgage still owed", "mortgage_balance_cents"],
                ] as [string, keyof Horizon][]
              )
                .filter(([, key]) => key !== "condo_fees_cents" || report.condo_fee.applies)
                .map(([label, key]) => (
                  <tr key={key} className="border-t border-line">
                    <td className="whitespace-pre py-1.5 pr-4">{label}</td>
                    {report.projection.horizons.map((h) => (
                      <td key={h.years} className="py-1.5 pr-4">
                        {(key === "condo_fees_cents" && report.condo_fee.basis === "unavailable") ||
                        (key === "property_tax_cents" && report.property_tax.basis === "unavailable") ? (
                          <span className="italic text-muted">Unavailable — not included</span>
                        ) : (
                          <Money cents={h[key] as number} />
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Resale and appreciation scenarios">
        <p className="mb-2 max-w-prose text-xs text-muted">
          What a sale might return after selling costs and the remaining mortgage, and the net
          cost of having owned the home. Appreciation rates are assumptions, not predictions; 0%
          shows the outcome if prices do not rise at all.
        </p>
        {report.projection.horizons.map((h) => (
          <div key={h.years} className="mb-4 overflow-x-auto">
            <h3 className="mb-1 text-sm font-medium">After {h.years} years</h3>
            <table className="w-full min-w-[560px] text-sm tabular-nums">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-1 font-normal">Appreciation / yr</th>
                  <th className="py-1 font-normal">Home value</th>
                  <th className="py-1 font-normal">Selling costs</th>
                  <th className="py-1 font-normal">Equity after sale</th>
                  <th className="py-1 font-normal">Net cost of owning</th>
                </tr>
              </thead>
              <tbody>
                {h.outcomes.map((o) => (
                  <tr key={o.rate} className="border-t border-line">
                    <td className="py-1.5">
                      {pct(Number(o.rate))} <DataLabel basis="assumption" />
                    </td>
                    <td className="py-1.5"><Money cents={o.home_value_cents} /></td>
                    <td className="py-1.5"><Money cents={o.selling_costs_cents} /></td>
                    <td className="py-1.5"><Money cents={o.equity_after_sale_cents} /></td>
                    <td className="py-1.5"><Money cents={o.net_cost_cents} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Section>

      <Section title="Opportunity cost of the down payment">
        <p className="text-sm">
          <Money cents={report.opportunity_cost.upfront_cents} /> upfront could have earned about{" "}
          <Money cents={report.opportunity_cost.five_year_cents} /> over 5 years and{" "}
          <Money cents={report.opportunity_cost.ten_year_cents} /> over 10 years{" "}
          <DataLabel basis="assumption" />
        </p>
        <p className="mt-1 text-xs text-muted">{report.opportunity_cost.note}</p>
      </Section>

      <Section title="Interest-rate sensitivity">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-1 font-normal">Rate</th>
              <th className="py-1 font-normal">Monthly payment</th>
              <th className="py-1 font-normal">Change</th>
              <th className="py-1 font-normal">Interest over 5 years</th>
            </tr>
          </thead>
          <tbody>
            {report.rate_sensitivity.map((r) => (
              <tr key={r.rate} className="border-t border-line">
                <td className="py-1.5">{(Number(r.rate) * 100).toFixed(2)}%</td>
                <td className="py-1.5"><Money cents={r.monthly_payment_cents} /></td>
                <td className="py-1.5">
                  {r.change_cents === 0 ? "—" : `${r.change_cents > 0 ? "+" : "−"}${formatCad(Math.abs(r.change_cents))}`}
                </td>
                <td className="py-1.5"><Money cents={r.five_year_interest_cents} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Down-payment scenarios">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-1 font-normal">Down payment</th>
                <th className="py-1 font-normal">CMHC premium</th>
                <th className="py-1 font-normal">Mortgage</th>
                <th className="py-1 font-normal">Monthly payment</th>
                <th className="py-1 font-normal">Cash upfront</th>
                <th className="py-1 font-normal">Interest, 5 yrs</th>
              </tr>
            </thead>
            <tbody>
              {report.down_payment_scenarios.map((d) => (
                <tr key={d.down_payment_cents} className={`border-t border-line ${d.is_yours ? "font-medium" : ""}`}>
                  <td className="py-1.5">
                    <Money cents={d.down_payment_cents} /> ({pct(d.down_payment_share)}) · {d.label}
                  </td>
                  <td className="py-1.5"><Money cents={d.insurance_premium_cents} /></td>
                  <td className="py-1.5"><Money cents={d.mortgage_principal_cents} /></td>
                  <td className="py-1.5"><Money cents={d.monthly_payment_cents} /></td>
                  <td className="py-1.5"><Money cents={d.cash_required_cents} /></td>
                  <td className="py-1.5"><Money cents={d.five_year_interest_cents} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Closing costs">
        <ul>
          {report.closing_costs.lines.map((line) => (
            <li key={line.key} className="flex justify-between gap-4 border-b border-line py-1.5 text-sm">
              <span className="flex flex-wrap items-center gap-2">
                {line.label} <DataLabel basis={line.basis} />
              </span>
              <Money cents={line.amount_cents} />
            </li>
          ))}
          <li className="flex justify-between py-1.5 text-sm font-semibold">
            <span>Total</span>
            <Money cents={report.closing_costs.total_cents} />
          </li>
        </ul>
      </Section>

      <Section title="Recurring costs over ten years">
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ["Property tax", report.property_tax],
              ["Condo fee", report.condo_fee],
              ["Insurance", report.insurance],
              ["Maintenance", report.maintenance],
            ] as [string, CostBlock][]
          )
            .filter(([label, block]) => label !== "Condo fee" || block.applies)
            .map(([label, block]) => (
              <div key={label} className="rounded border border-line p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{label}</span>
                  <DataLabel basis={block.basis} />
                </div>
                {block.basis === "unavailable" ? (
                  <p className="mt-1 text-muted">Not available — not included in the totals.</p>
                ) : (
                  <p className="mt-1 tabular-nums">
                    <Money cents={block.monthly_cents} /> a month now ·{" "}
                    <Money cents={block.ten_year_cents} /> over ten years at {pct(block.growth)} a
                    year growth <DataLabel basis="assumption" />
                  </p>
                )}
                {block.note && <p className="mt-1 text-xs text-muted">{block.note}</p>}
              </div>
            ))}
        </div>
      </Section>

      <Section title="Monthly cash flow">
        <ul>
          {[...report.cash_flow.monthly_breakdown, ...(report.cash_flow.personal?.lines ?? [])].map(
            (line) => (
              <li key={line.key} className="flex justify-between gap-4 border-b border-line py-1.5 text-sm">
                <span className="flex flex-wrap items-center gap-2">
                  {line.label} <DataLabel basis={line.basis} />
                </span>
                {line.amount_cents === null ? (
                  <span className="italic text-muted">Unavailable</span>
                ) : (
                  <Money cents={line.amount_cents} />
                )}
              </li>
            ),
          )}
        </ul>
      </Section>

      <Section title="Risk analysis">
        {report.risk.qualification && (
          <p className="text-sm tabular-nums">
            {report.risk.qualification.may_qualify ? "Likely to qualify" : "Unlikely to qualify"}{" "}
            at the stress-test rate of {pct(report.risk.qualification.stressed_rate)} · GDS{" "}
            {pct(report.risk.qualification.gds)} of {pct(report.risk.qualification.gds_limit)} · TDS{" "}
            {pct(report.risk.qualification.tds)} of {pct(report.risk.qualification.tds_limit)}
          </p>
        )}
        <ul className="mt-2 space-y-1 text-sm">
          {report.risk.negative_factors.map((f, i) => (
            <li key={i}>⚠ {f.sentence}</li>
          ))}
          {report.risk.risks.map((r, i) => (
            <li key={`r${i}`}>
              ⚠ {r.category} ({r.status}): {r.explanation}
            </li>
          ))}
          {report.risk.negative_factors.length + report.risk.risks.length === 0 && (
            <li className="text-muted">No specific risk flags were raised from the data available.</li>
          )}
        </ul>
        {report.risk.qualification && (
          <p className="mt-2 text-xs text-muted">{report.risk.qualification.disclaimer}</p>
        )}
      </Section>

      <MissingInfo items={report.missing_info} />

      <Section title="Questions to ask">
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {report.questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ol>
      </Section>

      <Section title="Detailed assumptions">
        <ul className="space-y-1.5 text-sm">
          {report.assumptions.map((a) => (
            <li key={a.key} className="flex flex-wrap items-baseline gap-2">
              <DataLabel basis={a.basis} />
              <span className="font-medium">{a.label}:</span>
              <span>{a.value}</span>
              {a.rationale && <span className="text-xs text-muted">— {a.rationale}</span>}
            </li>
          ))}
        </ul>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
          {report.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </Section>

      <p className="border-t border-line pt-4 text-xs text-muted">{DISCLAIMER}</p>
    </article>
  );
}
