"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { UsageMeter } from "@/components/Monetization";
import { useSession } from "@/components/Session";

const SIGNED_IN = [
  { href: "/analyze", label: "Analyze" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/compare", label: "Compare" },
  { href: "/watch", label: "Watch" },
  { href: "/pricing", label: "Pricing" },
];

export function SiteHeader() {
  const { me, loading, logout } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const links = me
    ? [
        ...SIGNED_IN,
        { href: "/account", label: "Account" },
        ...(me.user.role === "admin" ? [{ href: "/admin", label: "Admin" }] : []),
      ]
    : [{ href: "/pricing", label: "Pricing" }];

  const linkClass = (href: string) =>
    `text-sm ${pathname === href || pathname.startsWith(`${href}/`) ? "text-ink" : "text-muted hover:text-ink"}`;

  return (
    <header className="border-b border-line print:hidden">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="text-sm uppercase tracking-widest text-muted hover:text-ink">
          Property Decision Engine
        </Link>

        <button
          type="button"
          className="rounded border border-line px-2 py-1 text-sm md:hidden"
          aria-expanded={open}
          aria-controls="site-nav"
          onClick={() => setOpen(!open)}
        >
          Menu
        </button>

        <nav
          id="site-nav"
          className={`${open ? "flex" : "hidden"} absolute left-0 right-0 top-12 z-20 flex-col gap-3 border-b border-line bg-white px-4 py-4 md:static md:flex md:flex-row md:items-center md:gap-5 md:border-0 md:p-0`}
        >
          {links.map((link) => (
            <Link key={link.href} href={link.href} className={linkClass(link.href)} onClick={() => setOpen(false)}>
              {link.label}
            </Link>
          ))}
          {!loading && me && <UsageMeter usage={me.usage} compact />}
          {!loading &&
            (me ? (
              <button
                type="button"
                className="text-left text-sm text-muted hover:text-ink"
                onClick={async () => {
                  await logout();
                  setOpen(false);
                  router.push("/");
                }}
              >
                Sign out
              </button>
            ) : (
              <>
                <Link href="/login" className={linkClass("/login")} onClick={() => setOpen(false)}>
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  className="rounded bg-accent px-3 py-1.5 text-sm text-white"
                  onClick={() => setOpen(false)}
                >
                  Start free
                </Link>
              </>
            ))}
        </nav>
      </div>
    </header>
  );
}
