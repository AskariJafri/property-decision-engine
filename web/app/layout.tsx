import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Property Decision Engine",
  description:
    "Whether a property makes financial sense for you, with every number sourced.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-CA">
      <body>
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
