/**
 * The three data states, built before the happy path (ARCHITECTURE.md §7).
 *
 * Most products treat a missing value as a rendering accident — an em dash, a
 * zero, a blank. Here it is a designed state with a reason, because "we could not
 * check this" is information a buyer needs and a competitor cannot cheaply copy.
 */

import type { ReactNode } from "react";

export function formatCad(cents: number | null | undefined, decimals = false): string {
  if (cents === null || cents === undefined) return "—";
  const dollars = cents / 100;
  return dollars.toLocaleString("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: decimals ? 2 : 0,
    maximumFractionDigits: decimals ? 2 : 0,
  });
}

/** A value we could not determine. Never a zero, never a dash without a reason. */
export function Unavailable({ reason }: { reason: string }) {
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className="text-muted italic">Data unavailable</span>
      <span className="text-xs text-muted max-w-prose">{reason}</span>
    </span>
  );
}

/** A value we computed from an assumption the user should be able to see. */
export function Estimated({
  children,
  assumption,
}: {
  children: ReactNode;
  assumption: string;
}) {
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className="tabular-nums">{children}</span>
      <span className="text-xs text-caution" title={assumption}>
        Estimated · {assumption}
      </span>
    </span>
  );
}

/** A real number we do not want leaned on too hard. */
export function LowConfidence({
  children,
  confidence,
  reason,
}: {
  children: ReactNode;
  confidence: number;
  reason?: string;
}) {
  const weak = confidence < 0.6;
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className={weak ? "tabular-nums text-muted" : "tabular-nums"}>{children}</span>
      <span className="text-xs text-muted">
        {Math.round(confidence * 100)}% confidence{reason ? ` · ${reason}` : ""}
      </span>
    </span>
  );
}

export function Figure({
  label,
  cents,
  decimals,
  hint,
}: {
  label: string;
  cents: number | null | undefined;
  decimals?: boolean;
  hint?: string;
}) {
  return (
    <div className="flex flex-col border-b border-line py-2">
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      {cents === null || cents === undefined ? (
        <Unavailable reason={hint ?? "not computed"} />
      ) : (
        <span className="text-lg tabular-nums">{formatCad(cents, decimals)}</span>
      )}
    </div>
  );
}
