"use client";

/**
 * Back from Stripe. Arriving here proves nothing — the unlock happens only when
 * Stripe's signed webhook reaches the API — so this page waits for the server to
 * confirm rather than announcing success on the strength of a redirect.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useSession } from "@/components/Session";
import { apiFetch, type Me } from "@/lib/api";

export default function Page() {
  return (
    <Suspense>
      <Success />
    </Suspense>
  );
}

function Success() {
  const params = useSearchParams();
  const { setUsage } = useSession();
  const product = params.get("product");
  const analysis = params.get("analysis");
  const [confirmed, setConfirmed] = useState(false);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      try {
        if (product === "deep_dive" && analysis) {
          await apiFetch(`/analyses/${analysis}/deep-dive`);
          setConfirmed(true);
          clearInterval(timer);
        } else {
          const me = await apiFetch<Me>("/me");
          setUsage(me.usage);
          if (me.usage.plan_key === product) {
            setConfirmed(true);
            clearInterval(timer);
          }
        }
      } catch {
        // not yet
      }
      if (attempts >= 15) {
        setGaveUp(true);
        clearInterval(timer);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [product, analysis, setUsage]);

  return (
    <section className="mx-auto max-w-lg rounded-lg border border-line p-6">
      {confirmed ? (
        <>
          <h1 className="text-xl font-semibold">Payment confirmed</h1>
          <p className="mt-2 text-sm text-muted">Thank you. It is unlocked and on your account.</p>
          <Link
            href={product === "deep_dive" && analysis ? `/analyses/${analysis}/deep-dive` : "/dashboard"}
            className="mt-4 inline-block rounded bg-accent px-4 py-2 text-sm text-white"
          >
            {product === "deep_dive" ? "Open the Deep Dive" : "Go to your dashboard"}
          </Link>
        </>
      ) : gaveUp ? (
        <>
          <h1 className="text-xl font-semibold">Still confirming your payment</h1>
          <p className="mt-2 text-sm text-muted">
            Stripe has not confirmed it to us yet. This usually takes seconds; refresh in a
            minute, or check your account page. You will not be charged twice.
          </p>
        </>
      ) : (
        <>
          <h1 className="text-xl font-semibold">Confirming your payment…</h1>
          <p className="mt-2 text-sm text-muted">
            Waiting for Stripe to confirm. Access is granted when the payment is confirmed, not
            when you return to this page.
          </p>
        </>
      )}
    </section>
  );
}
