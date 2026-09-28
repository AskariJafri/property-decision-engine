"use client";

/**
 * The admin console. The page is a convenience; the authority is the API, which
 * checks the admin role from the database on every request. A non-admin who
 * reaches this page sees an error from the server, not the data.
 */

import { useCallback, useEffect, useState } from "react";

import { formatCad } from "@/components/DataState";
import { RequireAuth } from "@/components/RequireAuth";
import { ApiError, apiFetch, type Me } from "@/lib/api";

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type Settings = Record<string, { [key: string]: Json }>;

const TABS = ["Overview", "Users", "Pricing", "Ads & features", "Promotions", "Costs & assumptions", "Activity"] as const;
type Tab = (typeof TABS)[number];

export default function AdminPage() {
  return (
    <RequireAuth>
      {(me) =>
        me.user.role === "admin" ? (
          <Admin me={me} />
        ) : (
          <p className="text-sm text-alarm" data-testid="admin-forbidden">
            This area is for administrators.
          </p>
        )
      }
    </RequireAuth>
  );
}

function Admin({ me }: { me: Me }) {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-xs text-muted">Signed in as {me.user.email}</p>
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-accent text-ink" : "text-muted"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <Overview />}
      {tab === "Users" && <Users me={me} />}
      {tab === "Pricing" && <SettingsEditor keys={["pricing"]} />}
      {tab === "Ads & features" && <SettingsEditor keys={["ads", "features"]} />}
      {tab === "Promotions" && <SettingsEditor keys={["promotions"]} />}
      {tab === "Costs & assumptions" && <SettingsEditor keys={["costs", "projection"]} />}
      {tab === "Activity" && <Activity />}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Overview = Record<string, any>;

function Stat({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <div className="rounded border border-line p-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 text-lg tabular-nums">{value}</dd>
      {note && <p className="mt-1 text-[11px] text-muted">{note}</p>}
    </div>
  );
}

const money = (cents: number | null | undefined) =>
  cents === null || cents === undefined ? "—" : formatCad(Math.round(cents), Math.abs(cents) < 10000);

function Overview() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiFetch<Overview>("/admin/overview")
      .then(setData)
      .catch((caught: Error) => setError(caught.message));
  }, []);
  if (error) return <p className="text-sm text-alarm">{error}</p>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  const { users, usage, revenue, costs, unit_economics: ue, ads } = data;
  return (
    <div className="space-y-8" data-testid="admin-overview">
      <section>
        <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Unit economics · {ue.period}</h2>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="Revenue" value={money(ue.revenue_cents)} />
          <Stat label="− AI / API cost (est.)" value={money(ue.ai_api_cost_cents)} />
          <Stat label="− Payment fees" value={money(ue.payment_fees_cents)} />
          <Stat label="− Other costs" value={money(ue.other_costs_cents)} note="From Costs & assumptions" />
          <Stat label="= Contribution margin" value={money(ue.contribution_margin_cents)} />
          <Stat label="Revenue per user" value={money(ue.revenue_per_user_cents)} />
          <Stat label="Cost per user" value={money(ue.cost_per_user_cents)} />
          <Stat label="Margin per user" value={money(ue.margin_per_user_cents)} />
          <Stat label="Margin per paying user" value={money(ue.margin_per_paying_user_cents)} />
          <Stat label="Cost per analysis (est.)" value={money(costs.cost_per_analysis_cents)} />
        </dl>
        <p className="mt-2 text-xs text-muted">{costs.note}</p>
      </section>

      <section>
        <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Users</h2>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Total" value={users.total} />
          <Stat label="New (7 days)" value={users.new_7d} />
          <Stat label="Active (7 days)" value={users.active_7d} />
          <Stat label="Free" value={users.free} />
          <Stat label="Paid" value={users.paid} />
          <Stat label="Professional" value={users.professional} />
        </dl>
      </section>

      <section>
        <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Usage</h2>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Analyses today" value={usage.analyses_today} />
          <Stat label="This week" value={usage.analyses_7d} />
          <Stat label="Last 30 days" value={usage.analyses_30d} />
          <Stat label="Free analyses consumed" value={usage.free_analyses_consumed} />
          <Stat label="Watches" value={usage.watches} />
          <Stat label="Comparisons" value={usage.comparisons} />
        </dl>
      </section>

      <section>
        <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Revenue ({revenue.currency})</h2>
        {!revenue.payments_configured && (
          <p className="mb-2 text-xs text-caution">Payments are not configured, so there is no revenue to report.</p>
        )}
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="All time" value={money(revenue.all_time_cents)} />
          <Stat label="Paid reports (30 days)" value={money(revenue.reports_last_30d_cents)} />
          <Stat label="Subscriptions (30 days)" value={money(revenue.subscriptions_last_30d_cents)} />
          <Stat label="Estimated MRR" value={money(revenue.estimated_mrr_cents)} />
          <Stat label="Active subscriptions" value={revenue.active_subscriptions} />
          <Stat
            label="Conversion rate"
            value={revenue.conversion_rate === null ? "—" : `${(revenue.conversion_rate * 100).toFixed(1)}%`}
            note="Paying users ÷ all users"
          />
        </dl>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <div>
          <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">AI / API usage (30 days)</h2>
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="font-normal">Provider</th>
                <th className="font-normal">Calls</th>
                <th className="font-normal">Tokens in/out</th>
                <th className="font-normal">Est. cost</th>
              </tr>
            </thead>
            <tbody>
              {costs.api_by_provider_30d.map((row: Overview) => (
                <tr key={row.provider} className="border-t border-line">
                  <td className="py-1">{row.provider}</td>
                  <td>{row.calls}</td>
                  <td>
                    {row.input_tokens}/{row.output_tokens}
                  </td>
                  <td>{money(row.estimated_cost_cents)}</td>
                </tr>
              ))}
              {costs.api_by_provider_30d.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-2 text-muted">
                    No external API calls recorded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div>
          <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Ads</h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            <Stat label="Ads" value={ads.enabled ? `On · ${ads.provider}` : "Off"} />
            <Stat label="Ad-eligible users" value={ads.ad_eligible_users} />
            <Stat label="Impressions" value="Not available" />
            <Stat label="Ad revenue" value="Not available" />
          </dl>
          <p className="mt-2 text-xs text-muted">{ads.note}</p>
        </div>
      </section>
    </div>
  );
}

interface UserRow {
  id: string;
  email: string;
  role: string;
  tier: string;
  plan_key: string | null;
  free_used: number;
  free_total: number;
  analyses: number;
  created_at: string | null;
  last_seen_at: string | null;
}

function Users({ me }: { me: Me }) {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    apiFetch<{ users: UserRow[] }>(`/admin/users?q=${encodeURIComponent(q)}`)
      .then((body) => setRows(body.users))
      .catch((caught: Error) => setError(caught.message));
  }, [q]);
  useEffect(load, [load]);

  async function setRole(id: string, role: string) {
    setError(null);
    try {
      await apiFetch(`/admin/users/${id}`, { method: "PATCH", body: { role } });
      load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not change the role.");
    }
  }

  return (
    <div className="space-y-3">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search by email"
        className="w-full max-w-xs rounded border border-line px-3 py-1.5 text-sm"
      />
      {error && <p className="text-sm text-alarm">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="py-1 font-normal">Email</th>
              <th className="font-normal">Tier</th>
              <th className="font-normal">Free used</th>
              <th className="font-normal">Analyses</th>
              <th className="font-normal">Joined</th>
              <th className="font-normal">Last seen</th>
              <th className="font-normal">Role</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-t border-line tabular-nums">
                <td className="py-1.5">{u.email}</td>
                <td>{u.tier}{u.plan_key ? ` · ${u.plan_key}` : ""}</td>
                <td>
                  {u.free_used}/{u.free_total}
                </td>
                <td>{u.analyses}</td>
                <td>{u.created_at ? new Date(u.created_at).toLocaleDateString("en-CA") : "—"}</td>
                <td>{u.last_seen_at ? new Date(u.last_seen_at).toLocaleDateString("en-CA") : "—"}</td>
                <td>
                  <select
                    value={u.role}
                    disabled={u.id === me.user.id}
                    onChange={(e) => setRole(u.id, e.target.value)}
                    className="rounded border border-line px-1 py-0.5 text-xs"
                  >
                    <option value="user">user</option>
                    <option value="professional">professional</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const TITLES: Record<string, string> = {
  pricing: "Pricing (CAD by default)",
  ads: "Advertising",
  features: "Feature switches",
  promotions: "Promotions",
  costs: "Cost assumptions (for unit economics)",
  projection: "Deep Dive projection assumptions",
};

const PROMO_TEMPLATE: Json = {
  code: "NEWCODE",
  description: "",
  kind: "extra_analyses",
  value: 3,
  applies_to: [],
  active: true,
  expires_on: null,
};

function SettingsEditor({ keys }: { keys: string[] }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [status, setStatus] = useState<Record<string, string>>({});

  useEffect(() => {
    apiFetch<Settings>("/admin/settings").then(setSettings);
  }, []);

  async function save(key: string) {
    if (!settings) return;
    setStatus({ ...status, [key]: "Saving…" });
    try {
      const saved = await apiFetch<{ [k: string]: Json }>(`/admin/settings/${key}`, {
        method: "PUT",
        body: settings[key],
      });
      setSettings({ ...settings, [key]: saved });
      setStatus({ ...status, [key]: "Saved." });
    } catch (caught) {
      setStatus({ ...status, [key]: caught instanceof ApiError ? caught.message : "Could not save." });
    }
  }

  if (!settings) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-8">
      {keys.map((key) => (
        <section key={key} className="rounded-lg border border-line p-4">
          <h2 className="mb-3 font-semibold">{TITLES[key] ?? key}</h2>
          <Editor
            value={settings[key]}
            onChange={(value) => setSettings({ ...settings, [key]: value as { [k: string]: Json } })}
            path={key}
          />
          {key === "promotions" && (
            <button
              type="button"
              className="mt-3 text-sm text-accent"
              onClick={() =>
                setSettings({
                  ...settings,
                  promotions: {
                    promotions: [...((settings.promotions.promotions as Json[]) ?? []), PROMO_TEMPLATE],
                  },
                })
              }
            >
              + Add a promotion
            </button>
          )}
          <div className="mt-4 flex items-center gap-3">
            <button type="button" onClick={() => save(key)} className="rounded bg-accent px-3 py-1.5 text-sm text-white">
              Save
            </button>
            {status[key] && <span className="text-sm text-muted">{status[key]}</span>}
          </div>
        </section>
      ))}
    </div>
  );
}

/** Settings the schema allows to be empty; clearing the box sends null, not "". */
const NULLABLE = new Set(["interval", "expires_on", "analyses_per_month", "features"]);

const humanise = (key: string) =>
  key.replace(/_cents$/, " ($)").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Renders any settings object as a form: booleans, numbers, strings, lists, nested objects. */
function Editor({ value, onChange, path }: { value: Json; onChange: (v: Json) => void; path: string }) {
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v !== "object" || v === null)) {
      return (
        <input
          value={value.join(", ")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            )
          }
          className="w-full rounded border border-line px-2 py-1 text-sm"
          aria-label={path}
        />
      );
    }
    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div key={index} className="rounded border border-line p-3">
            <Editor value={item} onChange={(v) => onChange(value.map((x, i) => (i === index ? v : x)))} path={`${path}.${index}`} />
            {path.endsWith("promotions") && (
              <button type="button" className="mt-2 text-xs text-alarm" onClick={() => onChange(value.filter((_, i) => i !== index))}>
                Remove
              </button>
            )}
          </div>
        ))}
      </div>
    );
  }
  if (value !== null && typeof value === "object") {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(value).map(([key, child]) => {
          const nested = child !== null && typeof child === "object" && !Array.isArray(child);
          const nestedList = Array.isArray(child) && child.some((c) => typeof c === "object" && c !== null);
          return (
            <label key={key} className={`flex flex-col gap-1 ${nested || nestedList ? "sm:col-span-2" : ""}`}>
              <span className="text-xs text-muted">{humanise(key)}</span>
              <Field name={key} value={child} onChange={(v) => onChange({ ...value, [key]: v })} path={`${path}.${key}`} />
            </label>
          );
        })}
      </div>
    );
  }
  return null;
}

function Field({ name, value, onChange, path }: { name: string; value: Json; onChange: (v: Json) => void; path: string }) {
  if (typeof value === "boolean") {
    return (
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4" aria-label={path} />
    );
  }
  if (typeof value === "number" && name.endsWith("_cents")) {
    return (
      <input
        inputMode="decimal"
        defaultValue={(value / 100).toFixed(2)}
        onBlur={(e) => onChange(Math.round(Number(e.target.value) * 100))}
        className="rounded border border-line px-2 py-1 text-sm tabular-nums"
        aria-label={path}
      />
    );
  }
  if (typeof value === "number") {
    return (
      <input
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
        className="rounded border border-line px-2 py-1 text-sm tabular-nums"
        aria-label={path}
      />
    );
  }
  if (value === null || typeof value === "string") {
    return (
      <input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" && (value === null || NULLABLE.has(name)) ? null : e.target.value)}
        className="rounded border border-line px-2 py-1 text-sm"
        aria-label={path}
      />
    );
  }
  return <Editor value={value} onChange={onChange} path={path} />;
}

function Activity() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<Record<string, any> | null>(null);
  useEffect(() => {
    Promise.all([
      apiFetch<{ events: { name: string; count: number }[] }>("/admin/funnel"),
      apiFetch<{ errors: { at: string; method: string; path: string; error_class: string; message: string }[] }>("/admin/errors"),
      apiFetch<{ calls: { at: string; provider: string; operation: string; ok: boolean; latency_ms: number | null }[] }>("/admin/api-usage"),
      apiFetch<{ entries: { at: string; action: string; entity: string }[] }>("/admin/audit"),
    ]).then(([funnel, errors, calls, audit]) => setData({ funnel, errors, calls, audit }));
  }, []);
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="grid gap-8 md:grid-cols-2">
      <section>
        <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">Funnel (30 days)</h2>
        <ul className="text-sm tabular-nums">
          {data.funnel.events.map((e: { name: string; count: number }) => (
            <li key={e.name} className="flex justify-between border-b border-line py-1">
              <span>{e.name.replace(/_/g, " ")}</span>
              <span>{e.count}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2 className="mb-2 text-sm uppercase tracking-wide text-muted">System errors</h2>
        <ul className="space-y-1 text-xs">
          {data.errors.errors.map((e: { at: string; method: string; path: string; error_class: string; message: string }, i: number) => (
            <li key={i} className="border-b border-line py-1">
              {new Date(e.at).toLocaleString("en-CA")} · {e.method} {e.path} · <strong>{e.error_class}</strong> {e.message}
            </li>
          ))}
          {data.errors.errors.length === 0 && <li className="text-muted">No errors recorded.</li>}
        </ul>
        <h2 className="mb-2 mt-6 text-sm uppercase tracking-wide text-muted">Recent API calls</h2>
        <ul className="space-y-1 text-xs">
          {data.calls.calls.slice(0, 20).map((c: { at: string; provider: string; operation: string; ok: boolean; latency_ms: number | null }, i: number) => (
            <li key={i}>
              {new Date(c.at).toLocaleString("en-CA")} · {c.provider}/{c.operation} · {c.ok ? "ok" : "failed"}
              {c.latency_ms !== null ? ` · ${c.latency_ms} ms` : ""}
            </li>
          ))}
          {data.calls.calls.length === 0 && <li className="text-muted">None.</li>}
        </ul>
        <h2 className="mb-2 mt-6 text-sm uppercase tracking-wide text-muted">Admin audit log</h2>
        <ul className="space-y-1 text-xs">
          {data.audit.entries.map((e: { at: string; action: string; entity: string }, i: number) => (
            <li key={i}>
              {new Date(e.at).toLocaleString("en-CA")} · {e.action}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
