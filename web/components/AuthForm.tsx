"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { useSession } from "@/components/Session";
import { ApiError, apiFetch } from "@/lib/api";

export function AuthForm({ mode }: { mode: "signup" | "login" }) {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only same-site paths, so a crafted link cannot bounce a user elsewhere.
  const requested = params.get("next") ?? "";
  const next = requested.startsWith("/") && !requested.startsWith("//") ? requested : "/analyze";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch(mode === "signup" ? "/auth/signup" : "/auth/login", {
        body: { email, password },
      });
      await refresh();
      router.push(next);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const signup = mode === "signup";
  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-xl font-semibold">{signup ? "Create your free account" : "Sign in"}</h1>
      {signup && (
        <p className="mt-1 text-sm text-muted">5 free analyses. No credit card required.</p>
      )}
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-muted">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-line px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-muted">Password</span>
          <input
            type="password"
            required
            minLength={signup ? 10 : 1}
            autoComplete={signup ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-line px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          {signup && <span className="text-xs text-muted">At least 10 characters.</span>}
        </label>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-accent px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "One moment…" : signup ? "Create account" : "Sign in"}
        </button>
        {error && <p className="text-sm text-alarm">{error}</p>}
      </form>
      <p className="mt-4 text-sm text-muted">
        {signup ? "Already have an account? " : "New here? "}
        <Link
          href={`${signup ? "/login" : "/signup"}?next=${encodeURIComponent(next)}`}
          className="text-accent hover:underline"
        >
          {signup ? "Sign in" : "Create a free account"}
        </Link>
      </p>
      {signup && (
        <p className="mt-6 text-xs text-muted">
          Your financial details are used only to compute your analysis and are stored
          encrypted. Password reset by email is not available yet; keep your password safe.
        </p>
      )}
    </div>
  );
}
