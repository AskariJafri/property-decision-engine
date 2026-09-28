"use client";

/**
 * Property Watch. Honest about its source: updates come from the buyer, because
 * no listing feed this product may lawfully use is connected. When a price
 * changes, the analysis is re-run and the difference shown.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { formatCad } from "@/components/DataState";
import { UpgradeCard } from "@/components/Monetization";
import { RequireAuth } from "@/components/RequireAuth";
import { ApiError, apiFetch } from "@/lib/api";

interface WatchEvent {
  id: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  note: string | null;
  analysis_id: string | null;
  created_at: string;
}

interface Watch {
  id: string;
  title: string;
  listing_status: string;
  last_price_cents: number;
  days_on_market: number | null;
  current_analysis_id: string;
  events: WatchEvent[];
}

interface Impact {
  key: string;
  label: string;
  before: number | null;
  after: number | null;
  change: number | null;
}

const STATUSES = ["for_sale", "conditional", "sold", "terminated", "expired", "relisted", "unknown"];
const label = (s: string) => s.replace("_", " ");

export default function WatchPage() {
  return (
    <RequireAuth>
      {() => (
        <Suspense>
          <Watches />
        </Suspense>
      )}
    </RequireAuth>
  );
}

function Watches() {
  const params = useSearchParams();
  const [watches, setWatches] = useState<Watch[] | null>(null);
  const [limit, setLimit] = useState<number | null>(0);
  const [automatic, setAutomatic] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [impact, setImpact] = useState<{ watchId: string; rows: Impact[] } | null>(null);

  const load = useCallback(() => {
    apiFetch<{ watches: Watch[]; watch_limit: number | null; automatic_monitoring: boolean }>("/watches")
      .then((body) => {
        setWatches(body.watches);
        setLimit(body.watch_limit);
        setAutomatic(body.automatic_monitoring);
      })
      .catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => {
    const analysis = params.get("analysis");
    if (!analysis) return load();
    apiFetch("/watches", { body: { analysis_id: analysis } })
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 402) setLocked(true);
        else setError(caught instanceof Error ? caught.message : "Could not add the watch.");
      })
      .finally(load);
  }, [params, load]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Property Watch</h1>
        <p className="max-w-prose text-sm text-muted">
          {automatic
            ? "Watched properties are checked automatically for price and status changes."
            : "Automatic listing monitoring is not available: the listing portals do not permit automated collection, and no licensed feed is connected. When you see a price or status change, record it here and your analysis is recalculated at the new price."}
        </p>
      </div>

      {locked && (
        <UpgradeCard
          title="Property Watch is part of a plan"
          body="Save properties, record price and status changes, and see how each change moves your monthly cost, closing costs and cash required — with the Property Watch or Professional plan."
        />
      )}
      {error && <p className="text-sm text-alarm">{error}</p>}

      {watches && watches.length === 0 && !locked && (
        <p className="text-sm text-muted">
          {limit === 0
            ? "Your plan does not include watches."
            : "Nothing watched yet. Open an analysis and choose “Watch this property”."}{" "}
          <Link href="/dashboard" className="text-accent hover:underline">
            Your analyses
          </Link>
        </p>
      )}

      <ul className="space-y-4">
        {watches?.map((watch) => (
          <li key={watch.id} className="rounded-lg border border-line p-4" data-testid="watch">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <Link href={`/analyses/${watch.current_analysis_id}`} className="font-medium hover:underline">
                  {watch.title}
                </Link>
                <p className="text-xs text-muted tabular-nums">
                  {formatCad(watch.last_price_cents)} · {label(watch.listing_status)}
                  {watch.days_on_market !== null && ` · ${watch.days_on_market} days on market`}
                </p>
              </div>
              <button
                type="button"
                className="text-xs text-muted hover:text-alarm"
                onClick={() => apiFetch(`/watches/${watch.id}`, { method: "DELETE" }).then(load)}
              >
                Stop watching
              </button>
            </div>

            <UpdateForm
              watch={watch}
              onDone={(rows) => {
                if (rows) setImpact({ watchId: watch.id, rows });
                load();
              }}
            />

            {impact?.watchId === watch.id && (
              <div className="mt-4 rounded border border-accent/30 bg-accent/5 p-3" data-testid="watch-impact">
                <h3 className="text-sm font-semibold">How this change affects your previous analysis</h3>
                <table className="mt-2 w-full text-sm tabular-nums">
                  <tbody>
                    {impact.rows.map((row) => (
                      <tr key={row.key} className="border-t border-line">
                        <td className="py-1 pr-3 text-muted">{row.label}</td>
                        <td className="py-1 pr-3">
                          {row.key === "buy_score" ? row.before ?? "—" : formatCad(row.before)}
                        </td>
                        <td className="py-1 pr-3">→</td>
                        <td className="py-1 pr-3">
                          {row.key === "buy_score" ? row.after ?? "—" : formatCad(row.after)}
                        </td>
                        <td className="py-1 text-xs">
                          {row.change === null || row.change === 0
                            ? ""
                            : row.key === "buy_score"
                              ? `${row.change > 0 ? "+" : ""}${row.change}`
                              : `${row.change > 0 ? "+" : "−"}${formatCad(Math.abs(row.change))}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {watch.events.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-muted">
                {watch.events.map((e) => (
                  <li key={e.id}>
                    <span className="font-medium text-ink">Property update</span> ·{" "}
                    {new Date(e.created_at).toLocaleDateString("en-CA")} ·{" "}
                    {e.field === "price"
                      ? `${formatCad(Number(e.old_value))} → ${formatCad(Number(e.new_value))}`
                      : `${label(e.field)}: ${e.old_value ?? "—"} → ${e.new_value ?? "—"}`}
                    {e.note ? ` · ${e.note}` : ""}
                    {e.analysis_id && (
                      <>
                        {" · "}
                        <Link href={`/analyses/${e.analysis_id}`} className="text-accent hover:underline">
                          recalculated analysis
                        </Link>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function UpdateForm({ watch, onDone }: { watch: Watch; onDone: (impact: Impact[] | null) => void }) {
  const [price, setPrice] = useState("");
  const [status, setStatus] = useState(watch.listing_status);
  const [days, setDays] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await apiFetch<{ impact: Impact[] | null }>(`/watches/${watch.id}/updates`, {
        body: {
          price_cents: price ? Math.round(Number(price.replace(/[^0-9.]/g, "")) * 100) : null,
          listing_status: status !== watch.listing_status ? status : null,
          days_on_market: days ? Number(days) : null,
        },
      });
      setPrice("");
      setDays("");
      onDone(body.impact);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not record that.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">New price</span>
        <input
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          inputMode="decimal"
          placeholder={String(watch.last_price_cents / 100)}
          className="w-36 rounded border border-line px-2 py-1.5 text-sm tabular-nums"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Status</span>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border border-line px-2 py-1.5 text-sm">
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Days on market</span>
        <input value={days} onChange={(e) => setDays(e.target.value)} inputMode="numeric" className="w-24 rounded border border-line px-2 py-1.5 text-sm" />
      </label>
      <button type="submit" disabled={busy} className="rounded border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-50">
        {busy ? "Recalculating…" : "Record update"}
      </button>
      {error && <p className="w-full text-sm text-alarm">{error}</p>}
    </form>
  );
}
