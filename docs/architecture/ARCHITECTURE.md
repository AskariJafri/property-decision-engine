# Architecture

**Status:** Phase 0 proposal. Nothing here is built yet. Decisions with lasting consequence are
recorded in `/docs/decisions/0001-initial-architecture.md`.

---

## 1. Shape of the system

```
                 ┌─────────────────────────────────────────────┐
   Next.js UI ──▶│  FastAPI  (thin routes, no business logic)  │
                 └───────────────┬─────────────────────────────┘
                                 │ services (orchestration, transactions)
                 ┌───────────────▼─────────────────────────────┐
                 │                 ENGINES                     │
                 │  financial │ scoring │ valuation │ location  │
                 │  scenarios │ risk    │ comparables          │
                 │  — pure, deterministic, no I/O, no LLM —    │
                 └───────────────┬─────────────────────────────┘
                 ┌───────────────▼──────────┐   ┌──────────────┐
                 │  repositories (SQLAlchemy)│   │  providers   │
                 │  PostgreSQL               │◀──│  (adapters)  │
                 └───────────────────────────┘   └──────┬───────┘
                                 ▲                      │
                 ┌───────────────┴──────────┐    external APIs:
                 │   AI layer (explain only)│    MPAC, BoC, StatCan,
                 └──────────────────────────┘    CMHC, municipal, maps
```

The load-bearing rule: **engines are pure functions over value objects.** They take a fully
resolved input bundle and return a result plus its own explanation. They never open a session,
never call a provider, never call a model. That is what makes the whole system testable without
a database and reproducible across versions.

---

## 2. Backend layout

```
backend/
  app/
    api/v1/            routes only: validate, call a service, serialize
    core/              config, security, logging (with redaction), errors
    models/            SQLAlchemy ORM
    schemas/           Pydantic request/response + engine value objects
    repositories/      all SQL lives here
    services/          orchestration: fetch, enrich, run engines, persist
    engines/
      financial/       mortgage, closing costs, ownership cost, affordability
        rules/         VERSIONED, DATED rule tables (see §4)
      scoring/         subscores, weights, aggregation, confidence
      valuation/       fair value (v1: comparable/benchmark blend)
      comparables/     candidate selection + similarity scoring
      location/        metric assembly from provider results
      risk/            risk-flag rules
      scenarios/       deterministic what-if
    providers/         one adapter per external source, behind a Protocol
    ingestion/         listing URL / PDF / image / manual normalization
    ai/                prompt assembly, structured output, validation
    provenance/        fact recording, licence policy enforcement, TTL sweep
    workers/           async enrichment jobs
  tests/
    unit/ integration/ fixtures/
  alembic/
```

**Why engines sit beside services rather than under them:** a service may call several engines
and several providers; an engine must never reach back. Enforced in review and by an import
lint (engines may not import from `services`, `repositories`, `providers` or `ai`).

---

## 3. The analysis pipeline

One analysis is a pipeline of clearly separated stages, each producing recorded facts:

1. **Resolve property** — normalize address, geocode, attach or create the property record.
2. **Enrich** — providers fill attributes, tax, location metrics, risk sources. Every value
   written through the provenance layer. Failures degrade to `unavailable`, never to a guess.
3. **Compute money** — the financial engine: mortgage, insurance premium, closing costs,
   monthly ownership cost, qualification estimate, stress cases.
4. **Value** — comparables (when licensed data exists) then a fair-value *range* with confidence.
5. **Score** — subscores, user-adjusted weights, missing-data penalties, one Buy Score.
6. **Risk** — deterministic flags with `CONFIRMED` / `POTENTIAL` / `UNKNOWN` status.
7. **Explain** — the AI layer receives the finished, structured fact bundle and writes prose.
8. **Persist** — an immutable `property_analyses` row: inputs, outputs, weights, versions.

Stages 3–6 are pure. Stage 7 cannot alter stages 3–6. Stage 8 makes the whole thing replayable.

**Reproducibility contract:** `(analysis_inputs, rule_set_version, scoring_model_version)`
determines the score exactly. An analysis is never recomputed on read; a new run creates a new
row so a user can see what changed and why.

---

## 4. The rule registry

Rules are data, not code. Every rule row carries:

```
jurisdiction   e.g. "CA", "ON", "ON/Toronto"
rule_name      e.g. "ltt.brackets", "mqr.floor", "insured.max_price"
value          JSON payload (brackets, rates, thresholds)
effective_from date, effective_to date | null
source_url     the issuing authority
version        monotonic per rule_name
```

Resolution is always `as_of` a date — normally the analysis date, so an analysis run in June
2026 for a Toronto property above $3M picks up the April 2026 luxury MLTT bands, and an analysis
replayed from March 2026 does not. Seed contents come from
`/docs/research/RESEARCH_REPORT.md` §3, carrying their `[PRIMARY]`/`[SECONDARY]`/`[UNVERIFIED]`
labels into a `confidence` column; **nothing labelled `[UNVERIFIED]` may be marked active.**

---

## 5. Provider abstractions

Every external source sits behind a `Protocol` in `providers/`, with a mock implementation used
by default in tests and local development:

```
GeocodingProvider          PropertyDataProvider      AssessmentProvider
PlacesProvider             ComparableProvider        MortgageRateProvider
MarketDataProvider         RiskDataProvider          RentalDataProvider
SchoolDataProvider         TransitDataProvider       ListingExtractionProvider
```

Each adapter declares, in code, the licence facts the provenance layer enforces:

```python
class ProviderPolicy:
    provider: str
    licence_class: Literal["open", "licensed", "restricted", "prohibited"]
    may_store_values: bool          # false for Google content other than place IDs
    max_retention_days: int | None  # 30 for Google-derived coordinates
    attribution_required: str | None
```

A provider whose policy says `may_store_values=False` physically cannot get a durable
`data_provenance` row for that field; the repository refuses the write. Licensing is enforced by
the code path, not by a developer remembering a page in a document.

In the zero-cost stack (ADR 0002) most adapters point at **our own services** — Nominatim, OSRM
and Overpass running on an Ontario OSM extract — so their policies are `open` with permanent
storage and no rate limit. The mechanism stays regardless: it is what stops a future paid or
restricted provider from being wired in casually, and it is what keeps `prohibited` sources
un-integrable by construction rather than by discipline.

---

## 6. Data model (proposal)

UUID primary keys, `created_at`/`updated_at` everywhere, soft delete only where a user can undo.
Money in **integer cents**; never floats. Percentages as decimals with explicit scale.

**Identity and profile**
`users`, `user_profiles`, `financial_profiles` (encrypted sensitive columns),
`buyer_preferences` (requirements, weights, horizon, goal, risk posture)

**Property**
`properties` (canonical, geocoded), `property_sources` (each ingestion event and its source),
`property_attributes` (**one row per field per source** — this is what makes provenance real
rather than a comment), `property_price_history`, `property_history`

**Location**
`locations` (coordinates, matched OSM feature, our derived metrics — durable, because the
self-hosted ODbL stack permits storage where Google would not; see ADR 0002 §1),
`location_metrics` (metric, value, provider, retrieved_at, expires_at)

**Analysis**
`property_analyses` (immutable run record: model versions, rule-set version, confidence),
`analysis_scores` (subscore, weight, raw value, contribution),
`analysis_factors` (the human-readable reasons behind each subscore),
`risk_flags` (category, severity, status, evidence, source, distance, recommended action),
`mortgage_scenarios`, `financial_scenarios`, `ai_reports`

**Comparables**
`comparables`, `comparable_scores` (similarity, distance, inclusion/exclusion reasons)

**Provenance and market**
`data_sources` (one row per provider with its licence class),
`data_provenance` (value, source, retrieved_at, effective_at, confidence, licence class,
`expires_at` for retention-limited data),
`market_snapshots` (dated market context — never constants in code)

**User surfaces**
`saved_properties`, `property_comparisons`, `audit_logs`

A full `DATABASE.md` with column-level detail is produced in Phase C, before the first migration.

---

## 7. Frontend

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui. Server components for analysis
rendering, client components for the interactive scenario panel.

Design register: analytical, quiet, high-contrast, generous whitespace, one accent colour, no
gradients, no glowing AI motifs. Numbers set in a tabular-figure face. Ranges rendered as
ranges, never as a false-precision point value. Three visual states are first-class and designed
before the happy path:

- **Estimated** — value with an explicit assumption tooltip
- **Data unavailable** — a stated absence with the reason, never an em dash or a zero
- **Low confidence** — the number, deliberately de-emphasized, with the reason adjacent

Screens: landing, onboarding, dashboard, add property, analysis, score breakdown, financial
breakdown, location, risks, comparables, scenarios, saved, compare, settings.

---

## 8. AI layer

The layer runs at two points (ADR 0004). **Before scoring** it produces typed,
capped, pinned *judgements* that the deterministic engines consume as ordinary
inputs at `AI_INFERRED` quality. **After scoring** it narrates, as below.

Contract for the narration pass: **structured facts in, prose out.** The model receives a compact JSON bundle of
already-computed values plus a list of `unavailable` fields, and returns a validated JSON
document (summary, pros, cons, explanation, questions, what-would-change-this). Validation
rejects any numeric token not present in the input bundle, so a hallucinated figure fails
closed rather than reaching the user.

Cost control: nothing calls a model unless a deterministic stage has finished and its output has
changed. Explanations are cached against the analysis hash. Extraction is the only pre-analysis
model call and it is user-initiated.

Provider abstraction from day one — the AI layer speaks to an OpenAI-compatible
interface, not a vendor SDK. Local Ollama now; free hosted tiers later differ by a
base URL and a model name. Sampling is pinned (temperature 0, fixed seed, exact
model tag) and the tag is stored with every judgement.

---

## 9. Security, privacy, observability

- Session auth with httpOnly, SameSite cookies; CSRF on mutating routes; rate limits on
  analysis and extraction endpoints (both are expensive).
- Financial columns encrypted at rest; a redaction filter in the logging config means income,
  debt and balance fields cannot be logged even by accident.
- Structured events: `analysis_started/completed/failed`, `property_created`, `listing_parsed`,
  `location_enriched`, `score_generated`, `scenario_created`, `provenance_expired`. Identifiers
  only — never values.
- `audit_logs` records who read or changed a financial profile.

---

## 10. Deployment

Docker Compose for development: `api`, `web`, `postgres`, plus the location stack — `nominatim`,
`osrm` (or `valhalla`) and `overpass`, all built from a Geofabrik Ontario extract. The extract
import is a one-off job of a few hours; a monthly refresh keeps it current. Developers who do
not need location work can run without those three and let the adapters return `unavailable`,
which is a state the product handles by design.

Alembic migrations gated in CI. Postgres managed in production; the OSM services on one modest
VM. Secrets from the environment, never in the repo; `.env.example` carries names and shapes
only.

**Cost profile:** $0 in data licence fees. The infrastructure is one app host, one database and
one OSM box.
