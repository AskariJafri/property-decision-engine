# ADR 0001 — Initial architecture

- **Date:** 2026-09-03
- **Status:** Accepted, **partially superseded by [ADR 0002](0002-zero-cost-data-strategy.md)**
  (2026-09-04), which removes every paid provider. Decisions 1, 2, 4, 5, 6, 7 and 8 stand
  unchanged. Decision 3's *mechanism* stands; its Google-specific retention example no longer
  applies, because the self-hosted OSM stack permits permanent storage.
- **Context:** Phase 0 research, `/docs/research/RESEARCH_REPORT.md`

---

## Decision 1 — The MVP ships without MLS data, by design

**Context.** Ontario sold prices are gated behind board membership or Teranet. CREA's DDF, the
one nominally open route, is display-only under its own Rules (§5(d), §5(i)) and cannot lawfully
feed a valuation.

**Decision.** Build the MVP with no MLS dependency. Property attributes come from the user and
(later) MPAC. Fair value is a wide, low-confidence range derived from market benchmarks, and the
absence of sold comparables is stated in the UI.

**Consequences.** The Value Score is the weakest subscore at launch, and we say so. In exchange,
nothing in the product depends on an agreement we do not have, and the comparable engine can be
switched on later behind an unchanged interface. Rejected: acquiring listing data by scraping —
prohibited by every relevant terms of service and incompatible with the product's central claim.

---

## Decision 2 — Provenance is a schema-level concept, not a convention

**Decision.** Every externally sourced or derived fact is written through a provenance layer
recording value, source, provider, retrieved_at, effective_at, confidence, licence class and
`expires_at`. `property_attributes` holds one row per field per source rather than one row per
property.

**Consequences.** Writes are more expensive and queries need a resolution step ("best value for
this field"). We accept both. Retrofitting provenance after launch would mean rewriting every
table that matters, and the UI's provenance labelling — the differentiator — is only as honest
as the storage beneath it.

---

## Decision 3 — Licence policy is enforced in code

**Decision.** Each provider adapter declares a `ProviderPolicy` (licence class,
`may_store_values`, `max_retention_days`, `attribution_required`). The provenance repository
refuses writes that contradict it. A TTL sweeper deletes retention-limited facts.

**Consequences.** Google-sourced coordinates cannot be durably stored (30-day limit); place IDs
can. `locations` therefore holds a place ID plus *our derived metrics*, never cached Google
content. Compliance survives staff turnover, because the rule is a code path rather than a
paragraph someone must remember.

---

## Decision 4 — Rules are versioned data with effective dates

**Decision.** Mortgage, tax and program rules live in a registry keyed by jurisdiction, rule
name, value, effective range, source URL and version. Resolution is always `as_of` a date.
Nothing labelled `[UNVERIFIED]` in the research report may be activated.

**Consequences.** Toronto's 2026-04-01 luxury MLTT bands are a data change, not a code change,
and an analysis replayed from March 2026 still reproduces exactly. Rejected: constants in the
financial engine — the exact failure mode that makes every competitor's calculator quietly wrong
after a budget.

---

## Decision 5 — Engines are pure; the LLM is downstream of all of them

**Decision.** `engines/` are pure functions over value objects: no session, no provider, no model
call. The AI layer runs last, receives structured facts plus an explicit list of unavailable
fields, and returns validated JSON. Validation rejects any numeric token not present in the
input bundle.

**Consequences.** Financial and scoring logic is testable without a database or a network, and a
hallucinated figure fails closed instead of reaching a user who is about to spend $850,000.
Enforced by an import lint: `engines` may not import `services`, `repositories`, `providers` or
`ai`.

---

## Decision 6 — Reproducibility over freshness

**Decision.** An analysis is an immutable record stamped with `rule_set_version` and
`scoring_model_version`. Analyses are never recomputed on read; a re-run creates a new record
and the user is shown what changed.

**Consequences.** More rows, and "your score changed" becomes a designed experience rather than
an accident. The alternative — a score that quietly differs each time it is opened — would
destroy the trust the product is built on.

---

## Decision 7 — Missing data degrades weight and confidence, never the score

**Decision.** An unavailable subscore is dropped and its weight redistributed; if more than 35%
of weight would be redistributed, no Buy Score is emitted at all. `UNKNOWN` risk reduces
confidence, not the Risk Score.

**Consequences.** The product will sometimes decline to produce its headline number. That is the
intended behaviour, and it is the clearest possible expression of the brief's rule that unknown
must never become risk — or, in the other direction, that a silent zero must never become a
verdict.

---

## Decision 8 — Stack

FastAPI + SQLAlchemy + Alembic + Pydantic + PostgreSQL; Next.js + TypeScript + Tailwind +
shadcn/ui. Chosen for the owner's stated preference, the strength of Pydantic for the
extraction-validation boundary, and Postgres's suitability for provenance and geospatial work
(PostGIS available when the risk engine needs it).

**Money is stored in integer cents.** Floats are prohibited in any financial path.

---

## Open items requiring owner input before Phase B

1. Pilot municipality (decides the first flood/zoning/development integrations)
2. Budget for MPAC and Local Logic, or a strictly free-tier MVP
3. Business model, which determines the FSRA analysis and the independence claim
4. Whether a brokerage relationship for VOW sold data is on the table long term
5. Who performs the legal review of mortgage-adjacent language
