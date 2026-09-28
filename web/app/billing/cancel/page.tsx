import Link from "next/link";

export default function Page() {
  return (
    <section className="mx-auto max-w-lg rounded-lg border border-line p-6">
      <h1 className="text-xl font-semibold">Checkout cancelled</h1>
      <p className="mt-2 text-sm text-muted">Nothing was charged. Your analyses are still here.</p>
      <div className="mt-4 flex gap-3">
        <Link href="/dashboard" className="rounded bg-accent px-4 py-2 text-sm text-white">
          Your analyses
        </Link>
        <Link href="/pricing" className="rounded border border-line px-4 py-2 text-sm">
          Pricing
        </Link>
      </div>
    </section>
  );
}
