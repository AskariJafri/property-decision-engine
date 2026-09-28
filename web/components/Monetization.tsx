"use client";

/**
 * The paid parts of the product, presented as what they are.
 *
 * Quiet cards rather than pop-ups: an upgrade offer sits after the useful result,
 * says exactly what it adds and what it costs, and never blocks the page.
 */

import Link from "next/link";
import { useState } from "react";

import { formatCad } from "@/components/DataState";
import { useSession } from "@/components/Session";
import { ApiError, startCheckout, track, type Product, type Usage } from "@/lib/api";

export function priceLabel(product: Product): string {
  const amount = formatCad(product.price_cents, product.price_cents % 100 !== 0);
  return product.interval ? `${amount} CAD / ${product.interval}` : `${amount} CAD one-time`;
}

/** "4 of 5 free analyses remaining" — straight from the server's count. */
export function UsageMeter({ usage, compact = false }: { usage: Usage; compact?: boolean }) {
  let text: string;
  if (usage.unlimited) text = "Unlimited analyses";
  else if (usage.plan_key && usage.plan_monthly_cap !== null)
    text = `${usage.plan_remaining ?? 0} of ${usage.plan_monthly_cap} analyses left this month`;
  else if (usage.plan_key) text = "Plan active";
  else
    text = `${usage.free_remaining} of ${usage.free_total} free ${
      usage.free_total === 1 ? "analysis" : "analyses"
    } remaining`;

  const low = !usage.unlimited && !usage.plan_key && usage.free_remaining <= 1;
  return (
    <span
      data-testid="usage-meter"
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs tabular-nums ${
        low ? "border-caution/50 text-caution" : "border-line text-muted"
      }`}
    >
      {!compact && !usage.unlimited && !usage.plan_key && (
        <span className="flex gap-0.5" aria-hidden>
          {Array.from({ length: Math.min(usage.free_total, 10) }, (_, i) => (
            <span
              key={i}
              className={`h-1.5 w-1.5 rounded-full ${i < usage.free_remaining ? "bg-accent" : "bg-line"}`}
            />
          ))}
        </span>
      )}
      {text}
    </span>
  );
}

function useCheckout() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function buy(productKey: string, analysisId?: string) {
    setBusy(productKey);
    setError(null);
    try {
      await startCheckout(productKey, analysisId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Checkout could not start.");
      setBusy(null);
    }
  }
  return { busy, error, buy };
}

/** The Deep Dive offer, placed after a finished free analysis. */
export function DeepDiveCta({ analysisId, unlocked }: { analysisId: string; unlocked: boolean }) {
  const { config } = useSession();
  const { busy, error, buy } = useCheckout();
  const product = config?.products.find((p) => p.key === "deep_dive");
  if (config && !config.features.deep_dive) return null;

  return (
    <section className="rounded-lg border border-accent/30 bg-accent/5 p-5">
      <h2 className="text-base font-semibold text-ink">Want the complete 10-year analysis?</h2>
      <p className="mt-1 max-w-prose text-sm text-muted">
        The Deep Dive projects five and ten years of ownership — interest, equity, carrying
        costs and resale under several appreciation scenarios, including none — with rate and
        down-payment sensitivity, a closing-cost breakdown and a PDF you can keep. Every
        assumption is labelled.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {unlocked ? (
          <Link
            href={`/analyses/${analysisId}/deep-dive`}
            className="rounded bg-accent px-4 py-2 text-sm text-white"
          >
            Open the Deep Dive
          </Link>
        ) : (
          <>
            <Link
              href={`/analyses/${analysisId}/deep-dive`}
              onClick={() => track("deep_dive_viewed")}
              className="rounded bg-accent px-4 py-2 text-sm text-white"
            >
              Unlock Deep Dive{product ? ` — ${priceLabel(product)}` : ""}
            </Link>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => {
                track("upgrade_clicked", { from: "deep_dive_cta" });
                buy("deep_dive", analysisId);
              }}
              className="text-sm text-accent underline-offset-2 hover:underline disabled:opacity-50"
            >
              {busy ? "Opening checkout…" : "Go straight to checkout"}
            </button>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-caution">{error}</p>}
    </section>
  );
}

/** Shown in place of the form once the free analyses are used. Never a modal. */
export function LimitReached({ usage, analysisId }: { usage: Usage; analysisId?: string }) {
  const { config } = useSession();
  const { busy, error, buy } = useCheckout();
  const products = config?.products ?? [];
  const onPlan = usage.plan_key !== null;

  return (
    <section data-testid="limit-reached" className="rounded-lg border border-line p-6">
      <h2 className="text-lg font-semibold">
        {onPlan
          ? "You've used this month's analyses on your plan."
          : `You've used your ${usage.free_total} free property analyses.`}
      </h2>
      <p className="mt-1 text-muted">Continue analyzing properties with Property Decision Engine.</p>
      <p className="mt-3 max-w-prose text-sm text-muted">
        Everything you have already analysed stays yours — open it, compare it, and run offer
        scenarios on it from your dashboard at no cost.
      </p>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {products.map((product) => (
          <div key={product.key} className="flex flex-col rounded border border-line p-4">
            <span className="text-sm font-semibold">{product.name}</span>
            <span className="mt-1 text-sm tabular-nums">{priceLabel(product)}</span>
            <p className="mt-2 flex-1 text-xs text-muted">{product.description}</p>
            {product.key === "deep_dive" ? (
              analysisId ? (
                <button
                  type="button"
                  onClick={() => buy("deep_dive", analysisId)}
                  disabled={busy !== null}
                  className="mt-3 rounded border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-50"
                >
                  Deep Dive this property
                </button>
              ) : (
                <Link
                  href="/dashboard"
                  className="mt-3 rounded border border-accent px-3 py-1.5 text-center text-sm text-accent"
                >
                  Choose a property
                </Link>
              )
            ) : (
              <button
                type="button"
                onClick={() => {
                  track("upgrade_clicked", { from: "limit_reached", product: product.key });
                  buy(product.key);
                }}
                disabled={busy !== null}
                className="mt-3 rounded bg-accent px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                {busy === product.key ? "Opening checkout…" : `Choose ${product.name}`}
              </button>
            )}
          </div>
        ))}
        <div className="flex flex-col rounded border border-dashed border-line p-4">
          <span className="text-sm font-semibold">Upgrade</span>
          <p className="mt-2 flex-1 text-xs text-muted">
            Compare every plan side by side, including what each one includes.
          </p>
          <Link
            href="/pricing"
            onClick={() => track("upgrade_clicked", { from: "limit_reached_pricing" })}
            className="mt-3 rounded border border-line px-3 py-1.5 text-center text-sm"
          >
            See pricing
          </Link>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-caution">{error}</p>}
    </section>
  );
}

/** A plain upgrade prompt for a feature a plan unlocks. */
export function UpgradeCard({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-lg border border-line p-5">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-1 max-w-prose text-sm text-muted">{body}</p>
      <Link
        href="/pricing"
        onClick={() => track("upgrade_clicked", { from: "upgrade_card" })}
        className="mt-3 inline-block rounded bg-accent px-4 py-2 text-sm text-white"
      >
        See plans
      </Link>
    </section>
  );
}

export { useCheckout };
