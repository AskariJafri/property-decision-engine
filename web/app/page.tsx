/**
 * The landing page. What the product does, for whom, and what it costs — in that
 * order, with no claim it cannot back: it estimates and explains, it does not
 * promise savings or pick good investments.
 */

import Link from "next/link";

import { LandingBeacon } from "@/components/LandingBeacon";

const STEPS = [
  {
    title: "Paste a listing",
    body: "Copy the listing text or save it as a PDF. We read the price, taxes, fees and size, and show you where each value came from.",
  },
  {
    title: "Tell us about your finances",
    body: "Income, debts, down payment and savings. Used only to compute your numbers, stored encrypted, never shared.",
  },
  {
    title: "Analyze the property",
    body: "Mortgage, CMHC insurance, land transfer tax, closing costs, monthly carrying cost and the lender stress test — each with its working.",
  },
  {
    title: "Compare scenarios",
    body: "Different offer prices, higher rates, other properties side by side. See the trade-offs rather than a verdict.",
  },
  {
    title: "Make a more informed decision",
    body: "Walk into the offer knowing the costs, the risks, and the questions still worth asking.",
  },
];

const COVERS = [
  "Mortgage payment with Canadian semi-annual compounding",
  "CMHC insurance and minimum down payment",
  "Ontario and Toronto land transfer tax, first-time buyer rebates",
  "Closing costs and total cash required",
  "Property tax, condo fees, insurance and maintenance — labelled",
  "Stress-test (GDS/TDS) estimate against your income and debts",
  "Interest-rate sensitivity and offer scenarios",
  "What is missing from the listing, and what to ask for",
];

export default function Landing() {
  return (
    <div className="space-y-16">
      <LandingBeacon />
      <section className="pt-6">
        <p className="text-xs uppercase tracking-widest text-accent">For Canadian homebuyers</p>
        <h1 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight text-ink sm:text-4xl">
          Before you make an offer, know what this home will really cost you.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">
          Paste a Canadian property listing and understand the mortgage, closing costs, monthly
          carrying cost, affordability, scenarios and financial risks based on your situation.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <Link
            href="/analyze"
            className="rounded bg-accent px-5 py-3 text-base font-medium text-white"
          >
            Analyze a Property — Free
          </Link>
          <span className="text-sm text-muted">5 free analyses. No credit card required.</span>
        </div>
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-muted">How it works</h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map((step, index) => (
            <li key={step.title} className="rounded-lg border border-line p-4">
              <span className="text-xs tabular-nums text-accent">{index + 1}</span>
              <h3 className="mt-1 font-medium">{step.title}</h3>
              <p className="mt-2 text-sm text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-8 md:grid-cols-2">
        <div>
          <h2 className="text-sm uppercase tracking-wide text-muted">What the analysis covers</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {COVERS.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="text-good" aria-hidden>
                  ✓
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-line p-5">
          <h2 className="text-sm uppercase tracking-wide text-muted">Every number shows its source</h2>
          <p className="mt-3 text-sm">
            Each figure is marked as <strong>calculated</strong> from published rules,{" "}
            <strong>provided by you</strong>, <strong>estimated</strong>, or a{" "}
            <strong>planning assumption</strong> you can replace. When something cannot be
            known — a condo fee the listing omits, the age of the roof — it is named as missing
            rather than guessed.
          </p>
          <p className="mt-3 text-sm text-muted">
            The arithmetic is deterministic and inspectable. Where AI is used, it only explains
            numbers that were already computed, and it is labelled.
          </p>
        </div>
      </section>

      <section className="rounded-lg border border-line p-6">
        <h2 className="text-xl font-semibold">Built for Canadian homebuyers.</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Canadian mortgage rules — the stress test, CMHC insurance bands, the tiered minimum
          down payment and semi-annual compounding — are built in. Closing-cost and land
          transfer tax rules currently cover Ontario, including Toronto&apos;s municipal tax; other
          provinces are on the way and are not estimated in the meantime.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link href="/analyze" className="rounded bg-accent px-4 py-2 text-sm text-white">
            Analyze a Property — Free
          </Link>
          <Link href="/pricing" className="rounded border border-line px-4 py-2 text-sm">
            See pricing
          </Link>
        </div>
      </section>
    </div>
  );
}
