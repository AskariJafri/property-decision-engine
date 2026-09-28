import type { Metadata, Viewport } from "next";
import "./globals.css";

import { SessionProvider } from "@/components/Session";
import { SiteHeader } from "@/components/SiteHeader";
import { DISCLAIMER } from "@/lib/copy";

export const metadata: Metadata = {
  title: "Property Decision Engine — know what a Canadian home will really cost you",
  description:
    "Paste a Canadian property listing and understand the mortgage, closing costs, monthly carrying cost, affordability and financial risks based on your situation.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning covers this element's own attributes only, one
    // level deep. Browser extensions inject data-* attributes onto <html> and
    // <body> before React hydrates, which React reports as a mismatch we did not
    // cause and cannot prevent. It does not mask mismatches in our own markup.
    <html lang="en-CA" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <SessionProvider>
          <SiteHeader />
          <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">{children}</main>
          <footer className="mx-auto max-w-5xl px-4 py-10 text-xs text-muted sm:px-6">
            <p className="max-w-prose">{DISCLAIMER}</p>
            <p className="mt-2 max-w-prose">
              Closing-cost and land transfer tax rules currently cover Ontario. Mortgage
              rules (stress test, CMHC insurance, down-payment minimums) are federal.
            </p>
          </footer>
        </SessionProvider>
      </body>
    </html>
  );
}
