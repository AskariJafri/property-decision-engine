"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useSession } from "@/components/Session";
import type { Me } from "@/lib/api";

/**
 * Sends a signed-out visitor to sign in. A convenience only — every API route
 * checks the session itself, so hiding a page here protects nothing on its own.
 */
export function RequireAuth({ children }: { children: (me: Me) => ReactNode }) {
  const { me, loading } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !me) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [loading, me, router, pathname]);

  if (loading || !me) return <p className="text-sm text-muted">Loading…</p>;
  return <>{children(me)}</>;
}

export function LoadingOr({
  error,
  ready,
  children,
}: {
  error: string | null;
  ready: boolean;
  children: ReactNode;
}) {
  if (error) return <p className="text-sm text-alarm">{error}</p>;
  if (!ready) return <p className="text-sm text-muted">Loading…</p>;
  return <>{children}</>;
}
