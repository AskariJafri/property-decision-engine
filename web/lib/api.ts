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
  risks: RiskOut[];
  traces: TraceOut[];
  assumptions: { key: string; value: unknown; rationale: string }[];
  unavailable: { component?: string; reason: string }[];
  disclaimer: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function analyze(body: unknown): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/api/v1/properties/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Analysis failed");
  }
  return (await response.json()) as AnalyzeResponse;
}

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
export async function parseListing(text: string): Promise<ParsedListing> {
  const response = await fetch(`${API_BASE}/api/v1/listings/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error("Could not read that listing text.");
  return (await response.json()) as ParsedListing;
}

/**
 * Read a listing from a document the user saved.
 *
 * The intended flow: open the listing in your own browser, print it to PDF, drop
 * the file here. No automated retrieval, and a browser's PDF has a real text
 * layer so the values come out exactly rather than being inferred from pixels.
 */
export async function parseListingDocument(file: File): Promise<ParsedListing> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/v1/listings/parse-document`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: "Could not read that file." }));
    throw new Error(
      typeof problem.detail === "string" ? problem.detail : "Could not read that file.",
    );
  }
  return (await response.json()) as ParsedListing;
}
