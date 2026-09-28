/** Types mirroring the analyze payload in docs/API.md, and the fetch that gets it. */

export interface ScoreOut {
  component: string;
  available: boolean;
  subscore: number | null;
  base_weight: number;
  effective_weight: number;
  contribution: number;
  confidence: number;
  unavailable_reason: string | null;
}

export interface FactorOut {
  component: string;
  direction: string;
  magnitude: number;
  sentence: string;
}

export interface RiskOut {
  category: string;
  status: "confirmed" | "potential" | "unknown";
  severity: "low" | "medium" | "high";
  evidence: string;
  explanation: string;
  recommended_action: string;
  distance_m: number | null;
}

export interface TraceOut {
  name: string;
  formula: string;
  inputs: Record<string, unknown>;
  output: unknown;
  unit: string | null;
  rule_keys: string[];
}

/**
 * Prose over a finished analysis, and the only AI-authored text in the payload.
 *
 * It contributes no numbers. Everything it mentions was computed first and handed
 * to the model, and the backend's numeric guard discards the whole explanation if
 * a figure appears that was never supplied — so this either arrives verified or
 * does not arrive at all.
 */
export interface ExplanationOut {
  summary: string;
  pros: string[];
  cons: string[];
  questions: string[];
  what_would_change_this: string[];
  model_id: string;
  numeric_guard_passed: boolean;
  source: string;
}

/** One line of the adjustment grid. */
export interface Adjustment {
  attribute: string;
  subject_value: string;
  comparable_value: string;
  /** Signed: positive means the comparable was inferior and was adjusted up. */
  amount_cents: number;
  basis: string;
}

export interface UnadjustedAttribute {
  attribute: string;
  reason: string;
}

export interface AdjustedComparable {
  address: string;
  sale_price_cents: number;
  sale_date: string;
  similarity: number;
  included: boolean;
  reason: string;
  adjustments: Adjustment[];
  unadjusted: UnadjustedAttribute[];
  adjusted_price_cents: number;
  net_adjustment_cents: number;
  gross_adjustment_cents: number;
  gross_adjustment_ratio: number;
}

export interface ComparableGrid {
  rows: AdjustedComparable[];
  price_per_square_foot_cents: number | null;
  over_adjusted: string[];
}

export interface AnalyzeResponse {
  scoring_model_version: string;
  rule_set: string;
  /** Null when the model withholds it — see score_withheld_reason. */
  buy_score: number | null;
  score_withheld_reason: string | null;
  confidence: number;
  inputs_hash: string;
  scores: ScoreOut[];
  factors: { positive: FactorOut[]; negative: FactorOut[] };
  money: {
    purchase_price_cents: number;
    down_payment_cents: number;
    mortgage_principal_cents: number;
    insurance_premium_cents: number;
    monthly_ownership_cost_cents: number;
    closing_costs_cents: number;
    cash_required_cents: number;
    cash_shortfall_cents: number;
  };
  closing_cost_lines: {
    key: string;
    label: string;
    amount_cents: number;
    is_estimate: boolean;
    rule_keys: string[];
  }[];
  qualification: {
    may_qualify: boolean;
    stressed_rate: number;
    gds: number;
    tds: number;
    gds_limit: number;
    tds_limit: number;
    insured_eligible: boolean;
    max_purchase_price_cents: number | null;
    blocking_reasons: string[];
    disclaimer: string;
  };
  fair_value: {
    low_cents: number;
    high_cents: number;
    basis: string;
    confidence: number;
    note: string;
  };
  comparable_grid: ComparableGrid;
  risks: RiskOut[];
  traces: TraceOut[];
  assumptions: { key: string; value: unknown; rationale: string }[];
  unavailable: { component?: string; reason: string }[];
  /** Exactly one of these is populated. */
  explanation: ExplanationOut | null;
  explanation_unavailable_reason: string | null;
  disclaimer: string;
  /** The free analysis's plain-language layer. */
  monthly_breakdown: MonthlyLine[];
  money_labels: Record<string, DataBasis>;
  missing_info: MissingItem[];
  personal: PersonalFit | null;
  rate_scenarios: RateScenario[];
  /** Set by the metered API. */
  analysis_id: string | null;
  created_at: string | null;
  duplicate: boolean;
  usage: Usage | null;
}

/**
 * How a figure came to exist. Shown beside the figure, never hidden in a footnote:
 * known (published rules and your inputs, calculated), user-provided, estimated,
 * an assumption, or unavailable.
 */
export type DataBasis = "known" | "user_provided" | "estimated" | "assumption" | "unavailable";

export interface MonthlyLine {
  key: string;
  label: string;
  amount_cents: number | null;
  basis: DataBasis;
  note: string;
}

export interface MissingItem {
  key: string;
  title: string;
  why_it_matters: string;
  what_to_ask_for: string;
  severity: "high" | "medium" | "low";
  category: string;
}

export interface PersonalFit {
  lines: MonthlyLine[];
  housing_share_of_gross: number;
  emergency_months: number | null;
  note: string;
}

export interface RateScenario {
  rate: number;
  monthly_payment_cents: number;
  monthly_ownership_cost_cents: number;
  change_cents: number;
}

/** Computed by the server. The browser renders it and never decides anything from it. */
export interface Usage {
  tier: "free" | "paid" | "professional" | "admin";
  unlimited: boolean;
  plan_key: string | null;
  free_total: number;
  free_used: number;
  free_remaining: number;
  plan_monthly_cap: number | null;
  plan_used_this_month: number;
  plan_remaining: number | null;
  can_analyze: boolean;
  deep_dive_included: boolean;
  watch_limit: number | null;
  compare_max: number;
  show_ads: boolean;
}

export interface Me {
  user: { id: string; email: string; role: "user" | "professional" | "admin"; created_at: string };
  usage: Usage;
}

export interface Product {
  key: string;
  name: string;
  kind: "one_time" | "subscription";
  price_cents: number;
  interval: "month" | "year" | null;
  description: string;
  features: {
    analyses_per_month: number | null;
    deep_dive_included: boolean;
    watch_limit: number;
    compare_max: number;
  } | null;
  active: boolean;
}

export interface PublicConfig {
  currency: string;
  free_analyses: number;
  products: Product[];
  features: Record<string, boolean>;
  ads: {
    enabled: boolean;
    provider: "none" | "adsense";
    adsense_client: string;
    slots: Record<string, boolean>;
  };
  payments_configured: boolean;
}

export interface AnalysisSummary {
  id: string;
  title: string | null;
  created_at: string;
  buy_score: number | null;
  purchase_price_cents: number | null;
  monthly_ownership_cost_cents: number | null;
  cash_required_cents: number | null;
  closing_costs_cents: number | null;
  credit_source: string | null;
  derived_from_id: string | null;
  deep_dive_unlocked: boolean;
  watched: boolean;
}

export interface SavedAnalysis extends AnalyzeResponse {
  title: string | null;
  deep_dive_unlocked: boolean;
  request: AnalyzeRequestBody;
}

// The request as the form builds it; kept loose because the server validates it.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AnalyzeRequestBody = Record<string, any>;

/** The server's refusal, with its structured detail when it sent one. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: unknown }).message)
          : `Request failed (${status})`,
    );
  }

  get code(): string | undefined {
    const d = this.detail;
    return d && typeof d === "object" && "code" in d ? String((d as { code: unknown }).code) : undefined;
  }
}

/**
 * Same-origin, always.
 *
 * The browser only ever talks to this app; `next.config.mjs` proxies `/api/*` to
 * the API. That is what lets the session live in a first-party, httpOnly cookie —
 * a cross-site API would need third-party cookies, which browsers now block.
 */
function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)pde_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = options.method ?? (options.body !== undefined || options.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = problem?.detail;
    if (Array.isArray(detail)) {
      // Pydantic validation errors: show the first one in words.
      const first = detail[0];
      throw new ApiError(response.status, first?.msg ? `Check your inputs: ${first.msg}` : detail);
    }
    throw new ApiError(response.status, detail ?? "Request failed");
  }
  return (await response.json()) as T;
}

export const analyze = (body: AnalyzeRequestBody) =>
  apiFetch<AnalyzeResponse>("/properties/analyze", { body });

export const COMPONENT_LABELS: Record<string, string> = {
  affordability: "Affordability",
  value: "Value",
  personal_fit: "Personal fit",
  location: "Location",
  property_quality: "Property quality",
  investment: "Investment",
  risk: "Risk",
  market: "Market conditions",
};

export interface ParsedListing {
  fields: Record<string, number | string>;
  fields_as_cents: Record<string, number>;
  evidence: Record<string, string>;
  rejected: Record<string, string>;
  read_by: string;
  requires_confirmation: boolean;
  note: string;
}

/**
 * Read a listing the user pasted.
 *
 * There is no URL parameter on purpose: the portals prohibit automated
 * collection, so the user pastes what they are already looking at (ADR 0002 §2).
 */
export const parseListing = (text: string) =>
  apiFetch<ParsedListing>("/listings/parse", { body: { text } });

/**
 * Read a listing from a document the user saved.
 *
 * The intended flow: open the listing in your own browser, print it to PDF, drop
 * the file here. No automated retrieval, and a browser's PDF has a real text
 * layer so the values come out exactly rather than being inferred from pixels.
 */
export function parseListingDocument(file: File): Promise<ParsedListing> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<ParsedListing>("/listings/parse-document", { form });
}

/** Funnel analytics: an event name, never a figure. Failures are ignored. */
export function track(name: string, properties?: Record<string, string | number | boolean>) {
  apiFetch("/events", { body: { name, properties } }).catch(() => undefined);
}

export async function startCheckout(productKey: string, analysisId?: string, promoCode?: string) {
  const { url } = await apiFetch<{ url: string }>("/billing/checkout", {
    body: { product_key: productKey, analysis_id: analysisId ?? null, promo_code: promoCode || null },
  });
  window.location.assign(url);
}
