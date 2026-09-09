/**
 * The adjustment grid — the artifact a buyer can put in front of a seller.
 *
 * A fair-value range is a conclusion. This is the argument behind it, and the
 * argument is the part that survives contact with a listing agent: "your comp on
 * Oak sold for $910,000, but it is 70 square feet larger than this one, and at
 * the rate your own three sales imply that is $41,000 of the gap."
 *
 * So every row shows its arithmetic rather than a verdict. Adjustments are signed
 * in the appraisal convention — positive means the sale was *inferior* to the
 * subject and its price is adjusted up to stand in for it — which is the opposite
 * of the intuitive reading, and is why each line names both values rather than
 * only the difference.
 *
 * The section that matters most is the one listing what was *not* adjusted. A
 * grid with empty cells looks incomplete; a grid that silently omits the time
 * adjustment looks finished and is wrong. Naming the omission is the difference.
 */

import type { AdjustedComparable, ComparableGrid as Grid } from "@/lib/api";
import { formatCad } from "./DataState";

function signedCad(cents: number): string {
  const sign = cents > 0 ? "+" : cents < 0 ? "−" : "";
  return `${sign}${formatCad(Math.abs(cents))}`;
}

function Row({ row }: { row: AdjustedComparable }) {
  const moved = row.adjusted_price_cents - row.sale_price_cents;
  return (
    <div className={`border-b border-line py-3 ${row.included ? "" : "opacity-60"}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="font-medium">{row.address}</span>
        <span className="text-xs uppercase tracking-wide text-muted">
          sold {row.sale_date} · {Math.round(row.similarity * 100)}% similar
        </span>
      </div>

      <p className="mt-1 tabular-nums">
        {formatCad(row.sale_price_cents)}
        {moved !== 0 && (
          <>
            <span className="text-muted"> → </span>
            <span className="font-medium">{formatCad(row.adjusted_price_cents)}</span>
          </>
        )}
      </p>

      {row.adjustments.length > 0 && (
        <ul className="mt-2 space-y-1">
          {row.adjustments.map((a) => (
            <li key={a.attribute} className="text-xs">
              <span className="tabular-nums">{signedCad(a.amount_cents)}</span>{" "}
              <span className="text-muted">
                {a.attribute} — {a.comparable_value} against {a.subject_value}. {a.basis}.
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* Not styled as a warning. These are ordinary limits of the evidence, and
          dressing them as errors would train the reader to dismiss them. */}
      {row.unadjusted.map((u) => (
        <p key={u.attribute} className="mt-1 text-xs text-muted max-w-prose">
          <span className="uppercase tracking-wide">not priced</span> · {u.attribute}: {u.reason}
        </p>
      ))}

      {!row.included && <p className="mt-1 text-xs text-muted">{row.reason}</p>}
    </div>
  );
}

export function ComparableGrid({ grid }: { grid: Grid }) {
  if (grid.rows.length === 0) return null;

  const included = grid.rows.filter((r) => r.included);

  return (
    <section className="mt-8">
      <h2 className="text-sm uppercase tracking-wide text-muted mb-2">
        How the comparables were adjusted
      </h2>

      <p className="text-xs text-muted max-w-prose mb-3">
        Each sale is restated as an estimate of this property before anything averages
        them — added to where it was inferior, subtracted from where it was better. The
        adjusted figures are what the fair-value range is built on.
        {grid.price_per_square_foot_cents !== null && (
          <>
            {" "}
            Size is priced at {formatCad(grid.price_per_square_foot_cents, true)} per square
            foot, taken from the median of the sales you supplied.
          </>
        )}
      </p>

      <div>
        {grid.rows.map((row) => (
          <Row key={row.address} row={row} />
        ))}
      </div>

      {grid.over_adjusted.length > 0 && (
        <p className="mt-3 text-xs text-muted max-w-prose">
          {grid.over_adjusted.join(", ")} needed more than 15% of the sale price moved to
          stand in for this property. Still counted, and worth knowing: a sale that far
          from the subject is describing a different home. Replacing it with a closer one
          would tighten the range more than any other change you can make.
        </p>
      )}

      {included.length === 0 && (
        <p className="mt-3 text-xs text-muted max-w-prose">
          None of these cleared the similarity floor, so the fair-value range is still
          anchored on the asking price alone.
        </p>
      )}
    </section>
  );
}
