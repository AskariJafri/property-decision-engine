/**
 * Sold comparables, supplied by the person entitled to see them.
 *
 * This is the highest-leverage input on the page and the least obvious. With no
 * comparables the fair-value range is ±12% and confidence is capped at 45%; with
 * three or four good ones it narrows to ±6% at 75%. Five minutes of typing is
 * worth more here than anything else the form collects.
 *
 * Where to get them: the comparable-sales email a realtor sends, or looking them
 * up yourself. A person reading a page and typing a number breaches nothing — it
 * is automated collection the portals prohibit (ADR 0002 §2).
 */

"use client";

import { useState } from "react";

export interface ComparableRow {
  address: string;
  price: string;
  date: string;
  squareFeet: string;
  bedrooms: string;
  distance: string;
}

export const EMPTY_ROW: ComparableRow = {
  address: "",
  price: "",
  date: "",
  squareFeet: "",
  bedrooms: "",
  distance: "",
};

/** Rows the user has filled in enough to be usable. */
export function usableRows(rows: ComparableRow[]) {
  return rows.filter((row) => row.address.trim() && row.price.trim() && row.date.trim());
}

export function ComparablesInput({
  rows,
  onChange,
}: {
  rows: ComparableRow[];
  onChange: (rows: ComparableRow[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ready = usableRows(rows).length;

  const update = (index: number, key: keyof ComparableRow, value: string) => {
    const next = [...rows];
    next[index] = { ...next[index], [key]: value };
    onChange(next);
  };

  return (
    <section className="border border-line rounded-lg p-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full text-left text-sm uppercase tracking-wide text-muted"
      >
        {open ? "▾" : "▸"} Comparable sales ({ready} added) — the biggest single
        improvement you can make
      </button>

      {open && (
        <div className="mt-3 space-y-4">
          <p className="text-sm text-muted max-w-prose">
            Without these, the fair-value range is ±12% and confidence caps at 45% — it is
            anchored on the asking price alone, which makes it a sanity band rather than a
            valuation. Three or four recent sales nearby narrow it to ±6%.
          </p>
          <p className="text-xs text-muted max-w-prose">
            Get them from the comparable-sales email your realtor sends, or look them up
            yourself. We do not collect them automatically.
          </p>

          {rows.map((row, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-6 items-end">
              <Cell
                label="Address"
                value={row.address}
                onChange={(v) => update(index, "address", v)}
                className="sm:col-span-2"
              />
              <Cell
                label="Sold for"
                value={row.price}
                onChange={(v) => update(index, "price", v)}
              />
              <Cell
                label="Sold on"
                value={row.date}
                onChange={(v) => update(index, "date", v)}
                placeholder="2026-07-14"
              />
              <Cell
                label="Sq ft"
                value={row.squareFeet}
                onChange={(v) => update(index, "squareFeet", v)}
              />
              <Cell
                label="Beds"
                value={row.bedrooms}
                onChange={(v) => update(index, "bedrooms", v)}
              />
            </div>
          ))}

          <button
            type="button"
            onClick={() => onChange([...rows, { ...EMPTY_ROW }])}
            className="text-sm text-accent border border-accent rounded px-3 py-1"
          >
            Add another
          </button>
        </div>
      )}
    </section>
  );
}

function Cell({
  label,
  value,
  onChange,
  placeholder,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <label className={`flex flex-col gap-1 ${className}`}>
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="border border-line rounded px-2 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
    </label>
  );
}
