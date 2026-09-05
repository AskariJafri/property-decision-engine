/** The analysis page: score, money, why, risks, and the working. */

"use client";

import { COMPONENT_LABELS, type AnalyzeResponse } from "@/lib/api";
import { Figure, LowConfidence, Unavailable, formatCad } from "@/components/DataState";

export function BuyScore({ result }: { result: AnalyzeResponse }) {
  // The withheld case is the interesting one, so it is written first.
  if (result.buy_score === null) {
    return (
      <section className="border border-caution/40 bg-caution/5 rounded-lg p-6">
        <h2 className="text-sm uppercase tracking-wide text-caution">No Buy Score</h2>
        <p className="mt-2 max-w-prose text-ink">{result.score_withheld_reason}</p>
        <p className="mt-2 max-w-prose text-sm text-muted">
          The individual scores and every dollar figure below still stand on their own.
        </p>
      </section>
    );
  }

  const verdict =
    result.buy_score >= 80
      ? "Strong fit"
      : result.buy_score >= 65
        ? "Workable, with things to check"
        : result.buy_score >= 50
          ? "Marginal"
          : "Poor fit";

  return (
    <section className="border border-line rounded-lg p-6">
      <div className="flex items-baseline gap-4">
        <span className="text-6xl font-semibold tabular-nums" data-testid="buy-score">
          {result.buy_score}
        </span>
        <span className="text-2xl text-muted tabular-nums">/100</span>
      </div>
      <p className="mt-1 text-lg" data-testid="verdict">
        {verdict}
      </p>
      <p className="mt-2 text-sm text-muted">
        {Math.round(result.confidence * 100)}% confidence · model {result.scoring_model_version} ·
        rules {result.rule_set}
      </p>
    </section>
  );
}

export function ScoreBreakdown({ scores }: { scores: AnalyzeResponse["scores"] }) {
  return (
    <section>
      <h2 className="text-sm uppercase tracking-wide text-muted mb-3">Score breakdown</h2>
      <ul className="space-y-3">
        {scores.map((score) => (
          <li key={score.component} className="border-b border-line pb-3">
            <div className="flex justify-between items-baseline gap-4">
              <span>{COMPONENT_LABELS[score.component] ?? score.component}</span>
              {score.available && score.subscore !== null ? (
                <LowConfidence confidence={score.confidence}>
                  {score.subscore.toFixed(0)}
                </LowConfidence>
              ) : (
                <Unavailable reason={score.unavailable_reason ?? "not computed"} />
              )}
            </div>
            {score.available && (
              <div className="mt-1 h-1 bg-line rounded">
                <div
                  className="h-1 bg-accent rounded"
                  style={{ width: `${Math.min(100, score.subscore ?? 0)}%` }}
                />
              </div>
            )}
            <p className="mt-1 text-xs text-muted tabular-nums">
              weight {(score.effective_weight * 100).toFixed(0)}%
              {score.effective_weight !== score.base_weight &&
                ` (base ${(score.base_weight * 100).toFixed(0)}%)`}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Money({ result }: { result: AnalyzeResponse }) {
  const { money, fair_value, qualification } = result;
  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div>
        <h2 className="text-sm uppercase tracking-wide text-muted mb-2">What it costs</h2>
        <Figure label="Purchase price" cents={money.purchase_price_cents} />
        <Figure label="Down payment" cents={money.down_payment_cents} />
        <Figure label="Mortgage" cents={money.mortgage_principal_cents} />
        {money.insurance_premium_cents > 0 && (
          <Figure label="Insurance premium (financed)" cents={money.insurance_premium_cents} />
        )}
        <Figure
          label="Monthly ownership cost"
          cents={money.monthly_ownership_cost_cents}
          decimals
        />
        <Figure label="Closing costs" cents={money.closing_costs_cents} decimals />
        <Figure label="Cash needed to close" cents={money.cash_required_cents} decimals />
        {money.cash_shortfall_cents > 0 && (
          <p className="mt-2 text-sm text-alarm">
            {formatCad(money.cash_shortfall_cents)} short of the savings on file.
          </p>
        )}
      </div>

      <div>
        <h2 className="text-sm uppercase tracking-wide text-muted mb-2">What it is worth</h2>
        <div className="border-b border-line py-2">
          <span className="text-xs uppercase tracking-wide text-muted">
            Estimated fair value
          </span>
          <p className="text-lg tabular-nums">
            {formatCad(fair_value.low_cents)} – {formatCad(fair_value.high_cents)}
          </p>
          <p className="text-xs text-muted mt-1 max-w-prose">
            {Math.round(fair_value.confidence * 100)}% confidence · {fair_value.note}
          </p>
        </div>

        <h2 className="text-sm uppercase tracking-wide text-muted mt-6 mb-2">
          Mortgage qualification
        </h2>
        <p className="tabular-nums">
          {qualification.may_qualify ? "Likely to qualify" : "Unlikely to qualify"} · GDS{" "}
          {(qualification.gds * 100).toFixed(1)}% of {(qualification.gds_limit * 100).toFixed(0)}% ·
          TDS {(qualification.tds * 100).toFixed(1)}% of{" "}
          {(qualification.tds_limit * 100).toFixed(0)}%
        </p>
        <p className="text-xs text-muted mt-1">
          Stress-tested at {(qualification.stressed_rate * 100).toFixed(2)}%.
        </p>
        {qualification.blocking_reasons.map((reason) => (
          <p key={reason} className="text-sm text-alarm mt-1">
            {reason}
          </p>
        ))}
        {/* The caveat travels with the number, per COMPLIANCE.md §1. */}
        <p className="text-xs text-muted mt-2 max-w-prose">{qualification.disclaimer}</p>
      </div>
    </section>
  );
}

export function Factors({ result }: { result: AnalyzeResponse }) {
  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div>
        <h2 className="text-sm uppercase tracking-wide text-good mb-2">Why we like it</h2>
        <ul className="space-y-2">
          {result.factors.positive.map((factor, index) => (
            <li key={index} className="text-sm max-w-prose">
              ✓ {factor.sentence}
            </li>
          ))}
          {result.factors.positive.length === 0 && (
            <li className="text-sm text-muted">Nothing stood out in this property's favour.</li>
          )}
        </ul>
      </div>
      <div>
        <h2 className="text-sm uppercase tracking-wide text-caution mb-2">What concerns us</h2>
        <ul className="space-y-2">
          {result.factors.negative.map((factor, index) => (
            <li key={index} className="text-sm max-w-prose">
              ⚠ {factor.sentence}
            </li>
          ))}
          {result.factors.negative.length === 0 && (
            <li className="text-sm text-muted">Nothing counted against it.</li>
          )}
        </ul>
      </div>
    </section>
  );
}

/**
 * The AI narration, kept visibly apart from everything above it.
 *
 * The whole product rests on a reader being able to tell a computed figure from
 * an inferred sentence, so this never adopts the styling of the analysis: it is
 * boxed, labelled with the model that wrote it, and stated to have contributed no
 * numbers. When it is absent it says why, because silence here would leave a
 * reader unsure whether an explanation was even attempted.
 */
export function Explanation({ result }: { result: AnalyzeResponse }) {
  const { explanation, explanation_unavailable_reason: reason } = result;

  if (!explanation) {
    if (!reason) return null;
    return (
      <section className="border border-line rounded-lg p-4">
        <h2 className="text-sm uppercase tracking-wide text-muted mb-2">In plain language</h2>
        <p className="text-sm text-muted max-w-prose">{reason}</p>
      </section>
    );
  }

  const lists: [string, string[]][] = [
    ["What works", explanation.pros],
    ["What does not", explanation.cons],
    ["Ask the realtor", explanation.questions],
    ["What would change this", explanation.what_would_change_this],
  ];

  return (
    <section className="border border-line rounded-lg p-4">
      <div className="flex flex-wrap items-baseline gap-2 mb-2">
        <h2 className="text-sm uppercase tracking-wide text-muted">In plain language</h2>
        <span className="text-xs uppercase tracking-wide text-caution border border-caution/40 rounded px-1.5 py-0.5">
          AI-inferred
        </span>
      </div>

      <p className="text-sm max-w-prose">{explanation.summary}</p>

      <div className="grid gap-6 md:grid-cols-2 mt-4">
        {lists
          .filter(([, items]) => items.length > 0)
          .map(([heading, items]) => (
            <div key={heading}>
              <h3 className="text-xs uppercase tracking-wide text-muted mb-1">{heading}</h3>
              <ul className="space-y-1">
                {items.map((item, index) => (
                  <li key={index} className="text-sm max-w-prose">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
      </div>

      {/* Written next to the prose rather than in a footnote: it is the reason
          this section is safe to read at all. */}
      <p className="text-xs text-muted mt-4 max-w-prose">
        Written by {explanation.model_id} from the figures above. It contributed no numbers, and
        every figure it mentions was checked against the analysis before this was shown.
      </p>
    </section>
  );
}

export function NotChecked({ result }: { result: AnalyzeResponse }) {
  if (result.unavailable.length === 0) return null;
  return (
    <section className="border border-line rounded-lg p-4 bg-line/20">
      <h2 className="text-sm uppercase tracking-wide text-muted mb-2">What we could not check</h2>
      <ul className="space-y-1">
        {result.unavailable.map((item, index) => (
          <li key={index} className="text-sm text-muted max-w-prose">
            {item.component ? `${COMPONENT_LABELS[item.component] ?? item.component}: ` : ""}
            {item.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Working({ result }: { result: AnalyzeResponse }) {
  return (
    <details className="border border-line rounded-lg p-4">
      <summary className="cursor-pointer text-sm uppercase tracking-wide text-muted">
        Show the working ({result.traces.length} steps, {result.assumptions.length} assumptions)
      </summary>
      <table className="mt-4 w-full text-xs">
        <thead className="text-left text-muted">
          <tr>
            <th className="py-1">Step</th>
            <th className="py-1">Formula</th>
            <th className="py-1 text-right">Result</th>
          </tr>
        </thead>
        <tbody>
          {result.traces.map((trace, index) => (
            <tr key={index} className="border-t border-line">
              <td className="py-1 pr-3">{trace.name}</td>
              <td className="py-1 pr-3 font-mono text-muted">{trace.formula}</td>
              <td className="py-1 text-right tabular-nums">
                {trace.unit === "cents" && typeof trace.output === "number"
                  ? formatCad(trace.output, true)
                  : String(trace.output)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {result.assumptions.length > 0 && (
        <>
          <h3 className="mt-6 text-xs uppercase tracking-wide text-muted">Assumptions</h3>
          <ul className="mt-2 space-y-2">
            {result.assumptions.map((assumption, index) => (
              <li key={index} className="text-xs max-w-prose">
                <span className="font-mono">{assumption.key}</span> — {assumption.rationale}
              </li>
            ))}
          </ul>
        </>
      )}
    </details>
  );
}
