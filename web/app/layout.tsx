import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Property Decision Engine",
  description:
    "Whether a property makes financial sense for you, with every number sourced.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning covers this element's own attributes only, one
    // level deep. Browser extensions inject data-* attributes onto <html> and
    // <body> before React hydrates, which React reports as a mismatch we did not
    // cause and cannot prevent. It does not mask mismatches in our own markup.
    <html lang="en-CA" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <header className="border-b border-line">
          <div className="mx-auto max-w-5xl px-6 py-4">
            <h1 className="text-sm uppercase tracking-widest text-muted">
              Property Decision Engine
            </h1>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-5xl px-6 py-10 text-xs text-muted max-w-prose">
          This analysis is for informational purposes and is not financial, mortgage, legal,
          tax, insurance, or home-inspection advice.
        </footer>
      </body>
    </html>
  );
}
