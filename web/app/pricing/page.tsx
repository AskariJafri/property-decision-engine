"use client";

import Link from "next/link";
import { useEffect } from "react";

import { priceLabel, useCheckout } from "@/components/Monetization";
import { useSession } from "@/components/Session";
import { track, type Product } from "@/lib/api";

function features(product: Product): string[] {
  if (product.kind === "one_time") {
    return [
      "One property, analysed in full",
      "5- and 10-year projections with resale scenarios",
      "Rate and down-payment sensitivity",
      "Every assumption labelled, and a PDF",
    ];
  }
  const f = product.features;
  if (!f) return [];
  return [
    f.analyses_per_month === null
      ? "Unlimited analyses (fair use)"
      : `${f.analyses_per_month} analyses a month`,
    f.watch_limit ? `Watch up to ${f.watch_limit} properties` : "No watches",
    f.deep_dive_included ? "Every Deep Dive included" : "Deep Dives available to buy",
    `Compare up to ${f.compare_max} properties`,
    "No advertising",
  ];
}

export default function PricingPage() {
  const { me, config } = useSession();
  const { busy, error, buy } = useCheckout();

  useEffect(() => track("pricing_viewed"), []);

  const products = config?.products ?? [];
  const current = me?.usage.plan_key;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Pricing</h1>
        <p className="mt-1 max-w-prose text-muted">
          Start with {config?.free_analyses ?? 5} free analyses — no credit card. Pay only if you
          want more depth or keep analysing. All prices in {config?.currency ?? "CAD"}.
        </p>
      </div>

      {config && !config.payments_configured && (
        <p className="rounded border border-caution/40 bg-caution/5 p-3 text-sm text-caution">
          Payments are not set up yet on this deployment, so paid plans cannot be purchased right
          now. Nothing will be charged.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col rounded-lg border border-line p-5">
          <h2 className="font-semibold">Free</h2>
          <p className="mt-1 text-xl tabular-nums">$0</p>
          <ul className="mt-3 flex-1 space-y-1 text-sm text-muted">
            <li>{config?.free_analyses ?? 5} complete property analyses</li>
            <li>Mortgage, closing costs, monthly cost</li>
            <li>Affordability and rate scenarios</li>
            <li>Risk flags and what to investigate</li>
            <li>Offer scenarios and comparison</li>
          </ul>
          <Link href={me ? "/analyze" : "/signup"} className="mt-4 rounded border border-line px-3 py-2 text-center text-sm">
            {me ? "Analyze a property" : "Start free"}
          </Link>
        </div>

        {products.map((product) => (
          <div
            key={product.key}
            className={`flex flex-col rounded-lg border p-5 ${product.key === "professional" ? "border-accent/50" : "border-line"}`}
          >
            <h2 className="font-semibold">{product.name}</h2>
            <p className="mt-1 text-xl tabular-nums">{priceLabel(product)}</p>
            <p className="mt-2 text-sm text-muted">{product.description}</p>
            <ul className="mt-3 flex-1 space-y-1 text-sm">
              {features(product).map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-good" aria-hidden>
                    ✓
                  </span>
                  {item}
                </li>
              ))}
            </ul>
            {product.kind === "one_time" ? (
              <Link href={me ? "/dashboard" : "/signup"} className="mt-4 rounded border border-accent px-3 py-2 text-center text-sm text-accent">
                Choose a property to unlock
              </Link>
            ) : current === product.key ? (
              <span className="mt-4 rounded border border-line px-3 py-2 text-center text-sm text-muted">
                Your current plan
              </span>
            ) : me ? (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => {
                  track("upgrade_clicked", { from: "pricing", product: product.key });
                  buy(product.key);
                }}
                className="mt-4 rounded bg-accent px-3 py-2 text-sm text-white disabled:opacity-50"
              >
                {busy === product.key ? "Opening checkout…" : `Choose ${product.name}`}
              </button>
            ) : (
              <Link href="/signup?next=/pricing" className="mt-4 rounded bg-accent px-3 py-2 text-center text-sm text-white">
                Create an account
              </Link>
            )}
          </div>
        ))}
      </div>
      {error && <p className="text-sm text-caution">{error}</p>}
      <p className="max-w-prose text-xs text-muted">
        Subscriptions renew monthly and can be cancelled any time from your account; you keep
        access until the end of the period. Payments are processed by Stripe — card details
        never reach our servers.
      </p>
    </div>
  );
}
