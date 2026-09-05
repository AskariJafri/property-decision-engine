"use client";

/**
 * One page: your situation, the property, and the answer.
 *
 * Progressive disclosure rather than fifty questions — the form asks for what the
 * engines actually consume and nothing else, and every field that is missing shows
 * up in "what we could not check" rather than being silently defaulted.
 */

import { useState } from "react";

import {
  Factors,
  Money,
  NotChecked,
  BuyScore,
  Explanation,
  ScoreBreakdown,
  Working,
} from "@/components/Analysis";
import {
  ComparablesInput,
  EMPTY_ROW,
  usableRows,
  type ComparableRow,
} from "@/components/ComparablesInput";
import {
  analyze,
  parseListing,
  parseListingDocument,
  type AnalyzeResponse,
  type ParsedListing,
} from "@/lib/api";

const DOLLARS = (value: string) => Math.round(Number(value.replace(/[^0-9.]/g, "")) * 100);

const INITIAL = {
  address: "",
  workAddress: "",
  price: "850000",
  jurisdiction: "ON/Toronto",
  kind: "detached",
  squareFeet: "1450",
  yearBuilt: "1998",
  bedrooms: "3",
  bathrooms: "2.5",
  propertyTax: "",
  condoFee: "",
  income: "190000",
  debts: "450",
  down: "120000",
  savings: "160000",
  emergency: "15000",
  budget: "6000",
  firstTime: true,
  rate: "4.09",
  amortization: "25",
  minBedrooms: "3",
  maxCommute: "45",
  commute: "38",
};

export default function Home() {
  const [form, setForm] = useState(INITIAL);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [listing, setListing] = useState("");
  const [parsed, setParsed] = useState<ParsedListing | null>(null);
  const [comps, setComps] = useState<ComparableRow[]>([{ ...EMPTY_ROW }]);

  // Reading a listing fills the form; it never analyses anything on its own. The
  // user sees every value next to the text it came from and confirms by pressing
  // Analyse — nothing is trusted before that (ADR 0002 §2).
  function applyParsed(result: ParsedListing) {
    setParsed(result);
    const f = result.fields;
      setForm((current) => ({
        ...current,
        price: f.listing_price !== undefined ? String(f.listing_price) : current.price,
        bedrooms: f.bedrooms !== undefined ? String(f.bedrooms) : current.bedrooms,
        squareFeet: f.square_feet !== undefined ? String(f.square_feet) : current.squareFeet,
        yearBuilt: f.year_built !== undefined ? String(f.year_built) : current.yearBuilt,
        address: f.address !== undefined ? String(f.address) : current.address,
        bathrooms: f.bathrooms !== undefined ? String(f.bathrooms) : current.bathrooms,
        propertyTax:
          f.annual_property_tax !== undefined
            ? String(f.annual_property_tax)
            : current.propertyTax,
        condoFee:
          f.monthly_condo_fee !== undefined ? String(f.monthly_condo_fee) : current.condoFee,
        // A stated condo fee means it is a condo, whatever the dropdown says.
        kind: f.monthly_condo_fee !== undefined ? "condo_apartment" : current.kind,
    }));
  }

  async function onRead() {
    setBusy(true);
    setError(null);
    try {
      applyParsed(await parseListing(listing));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not read that.");
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      applyParsed(await parseListingDocument(file));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not read that file.");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  const set = (key: keyof typeof INITIAL) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: event.target.value });

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(
        await analyze({
          property: {
            purchase_price_cents: DOLLARS(form.price),
            address: form.address || null,
            jurisdiction: form.jurisdiction,
            property_kind: form.kind,
            square_feet: Number(form.squareFeet) || null,
            year_built: Number(form.yearBuilt) || null,
            bedrooms: Number(form.bedrooms) || null,
            bathrooms: form.bathrooms ? String(Number(form.bathrooms)) : null,
            // A stated figure always beats our estimate from the municipal rate.
            annual_property_tax_cents: form.propertyTax ? DOLLARS(form.propertyTax) : null,
            monthly_condo_fee_cents: form.condoFee ? DOLLARS(form.condoFee) : null,
            has_parking: true,
          },
          buyer: {
            gross_annual_income_cents: DOLLARS(form.income),
            household_income_cents: DOLLARS(form.income),
            monthly_debt_payments_cents: DOLLARS(form.debts),
            down_payment_cents: DOLLARS(form.down),
            available_savings_cents: DOLLARS(form.savings),
            emergency_fund_cents: DOLLARS(form.emergency),
            desired_max_monthly_cents: DOLLARS(form.budget),
            first_time_buyer: form.firstTime,
            residency_status: "citizen_or_pr",
          },
          terms: {
            contract_rate: String(Number(form.rate) / 100),
            amortization_years: Number(form.amortization),
          },
          preferences: {
            min_bedrooms: Number(form.minBedrooms) || null,
            requires_parking: true,
            max_commute_minutes: Number(form.maxCommute) || null,
            commute_minutes: Number(form.commute) || null,
            work_address: form.workAddress || null,
            commute_mode: "car",
            goal: "primary_residence",
            time_horizon: "5_to_10",
            risk_posture: "balanced",
          },
          comparables: usableRows(comps).map((row) => ({
            address: row.address,
            sale_price_cents: DOLLARS(row.price),
            sale_date: row.date,
            square_feet: Number(row.squareFeet) || null,
            bedrooms: Number(row.bedrooms) || null,
            distance_m: Number(row.distance) || null,
          })),
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <section className="border border-line rounded-lg p-4 space-y-3">
        <h2 className="text-sm uppercase tracking-wide text-muted">
          Paste a listing (optional)
        </h2>
        <p className="text-sm text-muted max-w-prose">
          Copy the listing text and paste it here — we read what it states and fill the form
          below. We do not fetch listing URLs: the portals prohibit it, so you paste what you
          are already looking at.
        </p>
        <textarea
          value={listing}
          onChange={(event) => setListing(event.target.value)}
          rows={5}
          placeholder="Offered at $849,000. 3 bedrooms, 2.5 bathrooms, 1,450 sq ft. Built in 1998..."
          className="w-full border border-line rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onRead}
            disabled={busy || !listing.trim()}
            className="border border-accent text-accent px-4 py-1.5 rounded text-sm disabled:opacity-40"
          >
            Read this listing
          </button>

          <span className="text-xs text-muted">or</span>

          {/* Print the listing to PDF from your own browser and drop it here.
              Two clicks, no copying, and nothing fetched on your behalf. */}
          <label className="border border-accent text-accent px-4 py-1.5 rounded text-sm cursor-pointer">
            Upload a saved PDF
            <input type="file" accept=".pdf,.txt,.md" onChange={onUpload} className="hidden" />
          </label>
          <span className="text-xs text-muted">Ctrl+P on the listing → Save as PDF</span>
        </div>

        {parsed && (
          <div className="text-sm space-y-2">
            <p className="text-muted">{parsed.note}</p>
            {Object.keys(parsed.fields).length > 0 && (
              <ul className="space-y-1">
                {Object.entries(parsed.fields).map(([field, value]) => (
                  <li key={field} className="text-xs">
                    <span className="font-mono">{field}</span> = {String(value)}
                    {parsed.evidence[field] && (
                      <span className="text-muted"> — read from “{parsed.evidence[field]}”</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {Object.entries(parsed.rejected).map(([field, reason]) => (
              <p key={field} className="text-xs text-caution">
                <span className="font-mono">{field}</span> ignored: {reason}
              </p>
            ))}
            <p className="text-xs text-muted">
              Read by {parsed.read_by}. Check each value against its source before analysing.
            </p>
          </div>
        )}
      </section>

      <form onSubmit={onSubmit} className="space-y-6">
        <p className="max-w-prose text-muted">
          Give us the property and your situation. Every number below is computed, sourced and
          shown with its working — and anything we cannot determine is named rather than guessed.
        </p>

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="text-sm uppercase tracking-wide text-muted mb-2">The property</legend>
          {/* Municipality is not cosmetic: Toronto charges a second land transfer
              tax worth about $9,000 on this file, and each city sets its own
              property tax rate. Defaulting it silently would be a wrong number
              dressed as a precise one. */}
          <label className="flex flex-col gap-1">
            <span className="text-xs uppercase tracking-wide text-muted">Municipality</span>
            <select
              value={form.jurisdiction}
              onChange={(event) => setForm({ ...form, jurisdiction: event.target.value })}
              className="border border-line rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              <option value="ON/Toronto">Toronto</option>
              <option value="ON/Mississauga">Mississauga</option>
              <option value="ON/Ottawa">Ottawa</option>
              <option value="ON/Other">Elsewhere in Ontario</option>
            </select>
            <span className="text-xs text-muted">
              {form.jurisdiction === "ON/Toronto"
                ? "Toronto charges a second land transfer tax."
                : form.jurisdiction === "ON/Other"
                  ? "We have no tax rate for that municipality, so property tax will be reported as unavailable."
                  : "Provincial land transfer tax only."}
            </span>
          </label>
          <Field
            label="Property address"
            value={form.address}
            onChange={set("address")}
            className="sm:col-span-2"
          />
          <Field
            label="Your work address (for commute)"
            value={form.workAddress}
            onChange={set("workAddress")}
            className="sm:col-span-2"
          />
          <Field label="Asking price" value={form.price} onChange={set("price")} />
          <Field label="Square feet" value={form.squareFeet} onChange={set("squareFeet")} />
          <Field label="Year built" value={form.yearBuilt} onChange={set("yearBuilt")} />
          <Field label="Bedrooms" value={form.bedrooms} onChange={set("bedrooms")} />
          <Field label="Bathrooms" value={form.bathrooms} onChange={set("bathrooms")} />
          <label className="flex flex-col gap-1">
            <span className="text-xs uppercase tracking-wide text-muted">Property type</span>
            <select
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value })}
              className="border border-line rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              <option value="detached">Detached</option>
              <option value="semi">Semi-detached</option>
              <option value="townhouse">Townhouse</option>
              <option value="condo_apartment">Condo apartment</option>
              <option value="condo_town">Condo townhouse</option>
              <option value="duplex">Duplex</option>
            </select>
          </label>
          <Field
            label="Annual property tax"
            value={form.propertyTax}
            onChange={set("propertyTax")}
          />
          <Field label="Monthly condo fee" value={form.condoFee} onChange={set("condoFee")} />
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="text-sm uppercase tracking-wide text-muted mb-2">
            Your situation
          </legend>
          <Field label="Household income" value={form.income} onChange={set("income")} />
          <Field label="Down payment" value={form.down} onChange={set("down")} />
          <Field label="Savings available" value={form.savings} onChange={set("savings")} />
          <Field label="Monthly debts" value={form.debts} onChange={set("debts")} />
          <Field label="Emergency fund" value={form.emergency} onChange={set("emergency")} />
          <Field label="Max monthly budget" value={form.budget} onChange={set("budget")} />
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="text-sm uppercase tracking-wide text-muted mb-2">The mortgage</legend>
          <Field label="Rate (%)" value={form.rate} onChange={set("rate")} />
          <Field label="Amortization (years)" value={form.amortization} onChange={set("amortization")} />
          <label className="flex items-end gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.firstTime}
              onChange={(event) => setForm({ ...form, firstTime: event.target.checked })}
            />
            First-time buyer
          </label>
        </fieldset>

        <ComparablesInput rows={comps} onChange={setComps} />

        <button
          type="submit"
          disabled={busy}
          className="bg-accent text-white px-5 py-2 rounded disabled:opacity-50"
        >
          {busy ? "Analysing…" : "Analyse this property"}
        </button>

        {error && <p className="text-alarm text-sm">{error}</p>}
      </form>

      {result && (
        <div className="space-y-8">
          <BuyScore result={result} />
          <Money result={result} />
          <Factors result={result} />
          <Explanation result={result} />
          <ScoreBreakdown scores={result.scores} />
          <NotChecked result={result} />
          <Working result={result} />
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  className?: string;
}) {
  return (
    <label className={`flex flex-col gap-1 ${className}`}>
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <input
        value={value}
        onChange={onChange}
        inputMode="decimal"
        className="border border-line rounded px-3 py-2 tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
    </label>
  );
}
