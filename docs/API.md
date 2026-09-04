# API Design

**Status:** Phase B contract. Routes are implemented in Phase F; this is what they will honour.
**Base:** `/api/v1`. OpenAPI served at `/api/v1/openapi.json`, docs at `/api/v1/docs`.

---

## Cross-cutting rules

**Money.** Every monetary field is an integer of cents and its name ends in `_cents`. There are
no dollar floats anywhere in the API surface.

**Every derived value carries its provenance.** The standard envelope:

```json
{
  "value": 612300,
  "unit": "cents",
  "source_class": "calculated",
  "confidence": 0.92,
  "as_of": "2026-09-04T12:00:00Z",
  "sources": ["src_boc_valet", "rule_on_ltt_2017"]
}
```

**Unavailable is a value, not an error.** A field we could not determine returns:

```json
{ "value": null, "source_class": "unavailable", "reason": "No TRCA coverage at this location" }
```

Clients render that as "Data unavailable" with the reason. A `null` without a `reason` is a bug
and fails schema validation on our side before it reaches the client.

**Errors** are RFC 9457 problem details (`application/problem+json`) with `type`, `title`,
`status`, `detail`, `instance`, and a `trace_id`.

**Auth.** Session cookie, httpOnly + Secure + SameSite=Lax; CSRF token required on mutating
requests. Rate limits: 60 req/min general, **10/hour on `analyze`**, **20/day on `listings/parse`**
(both are the expensive paths).

**Idempotency.** `POST /properties/{id}/analyze` accepts `Idempotency-Key`; a repeat with the
same key returns the same analysis rather than burning a second run.

---

## Onboarding and profile

```
POST   /api/v1/auth/register            {email, password}
POST   /api/v1/auth/login               → session cookie
POST   /api/v1/auth/logout
GET    /api/v1/users/me
PATCH  /api/v1/users/me

GET    /api/v1/users/me/financial-profile
PUT    /api/v1/users/me/financial-profile
GET    /api/v1/users/me/preferences
PUT    /api/v1/users/me/preferences
DELETE /api/v1/users/me                 → schedules hard deletion, returns the grace window
```

`PUT financial-profile` supersedes rather than overwrites: the previous row is closed with
`valid_to` so existing analyses stay replayable. The response never echoes the encrypted values
back in full — it returns what was stored, per field, as `{stored: true, updated_at}`.

**Progressive disclosure is a client concern**, but the server supports it: every field on the
financial profile and preferences is individually nullable, and `GET .../completeness` returns
which analyses are possible with what is currently known.

```
GET    /api/v1/users/me/completeness
→ { "can_analyze": true,
    "blocking": [],
    "degraded": [{"component":"investment","reason":"no rental assumptions provided"}] }
```

---

## Property

```
POST   /api/v1/properties                 create from a normalized payload
GET    /api/v1/properties/{id}
PATCH  /api/v1/properties/{id}
GET    /api/v1/properties/{id}/attributes  per-field values with provenance and conflicts
POST   /api/v1/properties/{id}/attributes  user correction; supersedes, never overwrites
```

`GET /attributes` returns the resolution, not just the winner:

```json
{ "sqft": { "value": 1450, "source_class": "user_asserted", "confidence": 0.65,
            "alternatives": [{"value": 1380, "source_class": "verified",
                              "source": "src_toronto_property_boundaries"}],
            "conflict": true } }
```

A conflict is surfaced, never resolved silently.

### Listing ingestion

```
POST   /api/v1/listings/parse             multipart: pdf | image | text
→ 202 { "job_id": "...", "status": "processing" }
GET    /api/v1/listings/parse/{job_id}
→ { "status":"complete", "extracted": {...}, "confidence_per_field": {...},
    "requires_confirmation": true }
POST   /api/v1/listings/parse/{job_id}/confirm   {corrections: {...}} → creates the property
```

**Nothing extracted is stored as a property attribute until the user confirms it.** A
`source_url` may be recorded if the user supplies one, and is never fetched (ADR 0002 §2).

---

## Analysis

```
POST   /api/v1/properties/{id}/analyze
GET    /api/v1/properties/{id}/analysis           latest
GET    /api/v1/analyses/{analysis_id}             a specific immutable run
GET    /api/v1/analyses/{analysis_id}/traces      calculation working, per figure
GET    /api/v1/analyses/{analysis_id}/risks
GET    /api/v1/analyses/{analysis_id}/comparables
GET    /api/v1/analyses/{analysis_id}/explanation AI narrative (cached)
```

Response shape (abridged):

```json
{
  "analysis_id": "...",
  "buy_score": 84,
  "score_withheld_reason": null,
  "confidence": 0.78,
  "scoring_model_version": "0.1.0",
  "rule_set": "2026.09.1",
  "scores": [
    {"component":"affordability","subscore":91,"base_weight":0.25,
     "effective_weight":0.29,"contribution":26.4,"confidence":0.95,"available":true}
  ],
  "money": {
    "purchase_price_cents": 85000000,
    "down_payment_cents": 12000000,
    "mortgage_principal_cents": 73000000,
    "monthly_ownership_cost_cents": 412000,
    "closing_costs_cents": 2840000,
    "cash_required_cents": 14840000
  },
  "fair_value": {"low_cents": 82000000, "high_cents": 84500000, "confidence": 0.45,
                 "basis": "market_benchmark_only",
                 "note": "No comparable sales supplied — add some to narrow this"},
  "qualification_estimate": {
    "may_qualify": true, "stressed_rate": 0.0609, "gds": 0.312, "tds": 0.371,
    "insured_eligible": false,
    "disclaimer": "Estimate from published rules. Only a lender can confirm."
  },
  "factors": {"positive": [...], "negative": [...]},
  "unavailable": [{"field":"flood_risk","reason":"outside TRCA mapped coverage"}]
}
```

`buy_score` is **nullable**. When more than 35% of scoring weight is unavailable the field is
`null` and `score_withheld_reason` explains why, with subscores still populated
(`SCORING_MODEL.md` §7).

`qualification_estimate.disclaimer` is part of the payload, not a UI decoration — the compliance
position in `COMPLIANCE.md` §1 requires the caveat to travel with the number.

---

## Comparables (user-supplied)

```
POST   /api/v1/properties/{id}/comparables       one comp, or a batch
POST   /api/v1/comparables/parse                 paste a realtor's email → structured comps
DELETE /api/v1/comparables/{comp_id}
GET    /api/v1/analyses/{id}/comparables         with similarity and inclusion reasoning
```

Each returned comp carries `similarity`, `distance_m`, `included`, and a plain-language
`inclusion_reason` or `exclusion_reason`. Comps are scoped to the supplying user; there is no
endpoint that returns another user's comps, by construction.

---

## Scenarios

```
POST   /api/v1/analyses/{id}/scenarios
{ "changes": { "rate_delta_bps": 100 } }
```

Supported change keys: `rate_delta_bps`, `down_payment_delta_cents`, `price_delta_pct`,
`income_delta_pct`, `condo_fee_delta_pct`, `property_tax_delta_pct`, `rent_basement_cents`,
`hold_years`, `amortization_years`.

Returns changed assumptions, recomputed payment, total monthly cost, equity at horizon, cash
flow, projected value under stated appreciation *scenarios* (never a forecast), and sensitivity.
Deterministic: the same scenario against the same analysis returns byte-identical numbers.

---

## Comparison

```
POST   /api/v1/comparisons        {analysis_ids: [...]}
GET    /api/v1/comparisons/{id}
```

Returns per-axis comparison plus labelled verdicts (`best_overall`, `best_value`,
`most_affordable`, `best_investment`), each with the reason it won that label.

---

## Location and reference

```
POST   /api/v1/location/enrich     {property_id}  → recompute location metrics
GET    /api/v1/reference/rules?jurisdiction=ON/Toronto&as_of=2026-09-04
GET    /api/v1/reference/sources   the licence register, rendered for the UI's attribution block
GET    /api/v1/health
```

`GET /reference/rules` exists because the product's promise is auditability: a user can read the
exact bracket table that produced their land transfer tax, with its source URL and effective
date.

---

## Versioning

URI-versioned (`/api/v1`). Additive changes ship in place. A change to scoring semantics bumps
`scoring_model_version` in the payload rather than the URI — old analyses keep their old version
and are never silently reinterpreted.
