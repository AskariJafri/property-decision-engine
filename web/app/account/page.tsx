"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { formatCad } from "@/components/DataState";
import { UsageMeter } from "@/components/Monetization";
import { RequireAuth } from "@/components/RequireAuth";
import { useSession } from "@/components/Session";
import { ApiError, apiFetch, track, type Me, type Usage } from "@/lib/api";

interface Summary {
  usage: Usage;
  payments_configured: boolean;
  subscriptions: {
    product_key: string;
    status: string;
    amount_cents: number;
    currency: string;
    interval: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    manageable: boolean;
  }[];
  payments: { product_key: string; amount_cents: number; currency: string; status: string; created_at: string }[];
}

export default function AccountPage() {
  return <RequireAuth>{(me) => <Account me={me} />}</RequireAuth>;
}

function Account({ me }: { me: Me }) {
  const { setUsage } = useSession();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<Summary>("/billing/summary")
      .then(setSummary)
      .catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => {
    track("subscription_viewed");
    load();
  }, [load]);

  async function redeem(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    try {
      const body = await apiFetch<{ message: string; usage?: Usage }>("/promo/redeem", { body: { code } });
      setMessage(body.message);
      if (body.usage) setUsage(body.usage);
      setCode("");
      load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "That code could not be used.");
    }
  }

  async function manage() {
    try {
      const { url } = await apiFetch<{ url: string }>("/billing/portal");
      window.location.assign(url);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The billing portal is unavailable.");
    }
  }

  const usage = summary?.usage ?? me.usage;
  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Account</h1>
        <p className="text-sm text-muted">
          {me.user.email} · {usage.tier === "admin" ? "Administrator" : `${usage.tier} plan`}
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="text-sm uppercase tracking-wide text-muted">Usage</h2>
        <UsageMeter usage={usage} />
        <p className="text-sm text-muted">
          Viewing, comparing and running offer scenarios on saved analyses never uses a credit.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm uppercase tracking-wide text-muted">Subscription</h2>
        {summary?.subscriptions.length ? (
          <ul className="space-y-2 text-sm">
            {summary.subscriptions.map((s) => (
              <li key={`${s.product_key}-${s.status}-${s.current_period_end}`} className="rounded border border-line p-3">
                <span className="font-medium">{s.product_key.replace("_", " ")}</span> · {s.status} ·{" "}
                {formatCad(s.amount_cents)} {s.currency}/{s.interval}
                {s.current_period_end &&
                  ` · ${s.cancel_at_period_end ? "ends" : "renews"} ${new Date(s.current_period_end).toLocaleDateString("en-CA")}`}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">
            No subscription. <Link href="/pricing" className="text-accent hover:underline">See plans</Link>
          </p>
        )}
        {summary?.subscriptions.some((s) => s.manageable) && (
          <button type="button" onClick={manage} className="rounded border border-line px-3 py-1.5 text-sm">
            Manage or cancel subscription
          </button>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm uppercase tracking-wide text-muted">Payments</h2>
        {summary?.payments.length ? (
          <ul className="text-sm">
            {summary.payments.map((p) => (
              <li key={p.created_at + p.product_key} className="flex justify-between border-b border-line py-1.5 tabular-nums">
                <span>
                  {new Date(p.created_at).toLocaleDateString("en-CA")} · {p.product_key.replace("_", " ")}
                </span>
                <span>
                  {formatCad(p.amount_cents, true)} {p.currency}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No payments.</p>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm uppercase tracking-wide text-muted">Promo code</h2>
        <form onSubmit={redeem} className="flex gap-2">
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            className="w-48 rounded border border-line px-3 py-1.5 text-sm uppercase"
            aria-label="Promo code"
          />
          <button type="submit" disabled={code.length < 3} className="rounded border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">
            Apply
          </button>
        </form>
        {message && <p className="text-sm text-good">{message}</p>}
      </section>
      {error && <p className="text-sm text-alarm">{error}</p>}
    </div>
  );
}
