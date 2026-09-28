"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AdSlot } from "@/components/AdSlot";
import { formatCad } from "@/components/DataState";
import { UpgradeCard, UsageMeter } from "@/components/Monetization";
import { LoadingOr, RequireAuth } from "@/components/RequireAuth";
import { apiFetch, type AnalysisSummary, type Me, type Usage } from "@/lib/api";

export default function DashboardPage() {
  return <RequireAuth>{(me) => <Dashboard me={me} />}</RequireAuth>;
}

function Dashboard({ me }: { me: Me }) {
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[] | null>(null);
  const [usage, setUsage] = useState<Usage>(me.usage);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ analyses: AnalysisSummary[]; usage: Usage }>("/analyses")
      .then((body) => {
        setAnalyses(body.analyses);
        setUsage(body.usage);
      })
      .catch((caught: Error) => setError(caught.message));
  }, []);

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id)
        ? current.filter((x) => x !== id)
        : current.length < usage.compare_max
          ? [...current, id]
          : current,
    );

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Your analyses</h1>
        <div className="flex flex-wrap items-center gap-3">
          <UsageMeter usage={usage} />
          <Link href="/analyze" className="rounded bg-accent px-4 py-2 text-sm text-white">
            Analyze a property
          </Link>
        </div>
      </div>

      <LoadingOr error={error} ready={analyses !== null}>
        {analyses && analyses.length === 0 ? (
          <section className="rounded-lg border border-line p-6 text-sm text-muted">
            Nothing analysed yet.{" "}
            <Link href="/analyze" className="text-accent hover:underline">
              Analyze your first property
            </Link>
            .
          </section>
        ) : (
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted">
                Select 2–{usage.compare_max} to compare side by side. Opening, comparing and
                running offers on saved analyses never uses a credit.
              </p>
              <button
                type="button"
                disabled={selected.length < 2}
                onClick={() => router.push(`/compare?ids=${selected.join(",")}`)}
                className="rounded border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40"
              >
                Compare {selected.length > 0 ? `(${selected.length})` : ""}
              </button>
            </div>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {analyses?.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3 p-3 sm:flex-nowrap">
                  <input
                    type="checkbox"
                    aria-label={`Select ${a.title ?? "analysis"} for comparison`}
                    checked={selected.includes(a.id)}
                    onChange={() => toggle(a.id)}
                  />
                  <div className="min-w-0 flex-1">
                    <Link href={`/analyses/${a.id}`} className="font-medium hover:underline">
                      {a.title ?? "Property"}
                    </Link>
                    <p className="text-xs text-muted">
                      {new Date(a.created_at).toLocaleDateString("en-CA")}
                      {a.derived_from_id ? " · recalculated after a price change" : ""}
                      {a.watched ? " · watched" : ""}
                    </p>
                  </div>
                  <dl className="grid grid-cols-3 gap-4 text-right text-xs tabular-nums">
                    <div>
                      <dt className="text-muted">Price</dt>
                      <dd>{formatCad(a.purchase_price_cents)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted">Monthly</dt>
                      <dd>{formatCad(a.monthly_ownership_cost_cents)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted">Score</dt>
                      <dd>{a.buy_score ?? "—"}</dd>
                    </div>
                  </dl>
                  <Link
                    href={`/analyses/${a.id}/deep-dive`}
                    className="text-xs text-accent hover:underline"
                  >
                    {a.deep_dive_unlocked ? "Deep Dive" : "Unlock Deep Dive"}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </LoadingOr>

      {!usage.unlimited && !usage.plan_key && usage.free_remaining <= 2 && (
        <UpgradeCard
          title="Keep going after your free analyses"
          body="Property Watch and Professional plans include a monthly allowance of analyses, saved watches with price-change recalculation, and (Professional) every Deep Dive."
        />
      )}
      <AdSlot slot="AD_SLOT_DASHBOARD" />
    </div>
  );
}
