# Database Design

**Status:** Phase B. Migrations are written in Phase C; this document is what they implement.
**Engine:** PostgreSQL 16. PostGIS enabled (the risk engine intersects points with flood
polygons; doing that in Python would be slower and worse).

---

## Conventions

| Rule | Reason |
|---|---|
| `uuid` primary keys, generated application-side | No enumerable IDs in URLs; no round trip to learn an ID |
| `created_at`, `updated_at` — `timestamptz`, never naive | Everything is dated; a naive timestamp is a bug waiting for a DST boundary |
| **Money is `bigint` cents.** Column names end `_cents` | Floats are prohibited in financial paths (ADR 0001 §8) |
| Rates and ratios are `numeric(9,6)` | Exact decimal; no binary float drift in a stress test |
| Enums are Postgres native types | The set of statuses is a schema fact, not a convention |
| Soft delete only where a user can undo | Everything else is a hard delete, because PIPEDA deletion must actually delete |
| No `ON DELETE CASCADE` from user to analysis | Deletion is a deliberate service operation with an audit trail, not a foreign-key side effect |

---

## 1. Identity and profile

### `users`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| email | citext UNIQUE NOT NULL | |
| password_hash | text NOT NULL | argon2 |
| email_verified_at | timestamptz NULL | |
| created_at / updated_at | timestamptz NOT NULL | |
| deleted_at | timestamptz NULL | set at deletion request; a worker hard-deletes after the grace window |

### `user_profiles`
Non-sensitive personal context: display name, locale, pilot city, notification preferences.

### `financial_profiles`
**The sensitive table.** One current row per user, with history retained (`valid_from`,
`valid_to`) so an analysis can be replayed against the profile as it stood.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users | |
| gross_annual_income_cents | bigint | **encrypted at rest** (pgcrypto or app-layer AEAD) |
| household_income_cents | bigint | encrypted |
| monthly_debt_payments_cents | bigint | encrypted |
| down_payment_cents | bigint | encrypted |
| available_savings_cents | bigint | encrypted |
| fhsa_balance_cents | bigint | encrypted |
| rrsp_hbp_available_cents | bigint | encrypted |
| emergency_fund_cents | bigint | encrypted |
| desired_max_monthly_cents | bigint | encrypted |
| first_time_buyer | boolean | |
| credit_score_band | enum | `under_600, 600_659, 660_719, 720_maximum, unknown` — a **band**, never a score |
| residency_status | enum | `citizen_or_pr, foreign_national, unknown` — drives NRST |
| valid_from / valid_to | timestamptz | |

Encrypted columns are `bytea`. They are never selected into a log line; the redaction filter in
`core/logging.py` is the second line of defence, not the first.

### `buyer_preferences`
Requirements and posture: min/max bedrooms and bathrooms, property types, parking and garage
requirements, basement and yard preferences, work location (as a `geography(Point,4326)`), max
commute minutes and mode, household size, children, school/walkability/quiet/resale importance
(0–5), `time_horizon` enum (`under_3, 3_to_5, 5_to_10, over_10`), `goal` enum
(`primary_residence, investment, house_hack, mixed`), `risk_posture` enum
(`conservative, balanced, aggressive`), and an optional `weight_overrides` jsonb for users who
want to tune the scoring weights directly.

---

## 2. Property

### `properties`
Canonical, deduplicated by normalized address.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| created_by_user_id | uuid FK | who first entered it |
| address_normalized | text NOT NULL | normalization key |
| street, unit, city, province, postal_code | text | |
| geom | geography(Point,4326) | from self-hosted Nominatim; **storable permanently** (ODbL) |
| geocode_confidence | numeric(4,3) | |
| osm_feature_id | text NULL | matched OSM element, for re-resolution |
| jurisdiction | text NOT NULL | e.g. `ON/Toronto` — the rule-registry lookup key |
| property_type | enum | `detached, semi, townhouse, condo_apartment, condo_town, duplex, other` |
| listing_price_cents | bigint NULL | |
| created_at / updated_at | timestamptz | |

UNIQUE `(address_normalized, unit)`. Index GIST on `geom`.

### `property_sources`
One row per ingestion event: `source_type` (`manual, pasted_text, pdf, screenshot`),
`source_url` (nullable, recorded only when the user supplies one — **we never fetch it**),
`raw_payload_ref` (object-store key), `extracted_at`, `confirmed_by_user_at`.

### `property_attributes`
**One row per field per source.** This is what makes provenance real instead of aspirational.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| property_id | uuid FK | |
| field | text NOT NULL | `bedrooms`, `sqft`, `year_built`, `condo_fee_cents`, … |
| value | jsonb NOT NULL | typed by field; validated on write |
| provenance_id | uuid FK → data_provenance | |
| superseded_by | uuid NULL FK → self | correction chain, never an in-place update |

UNIQUE `(property_id, field, provenance_id)`. The "current best value" for a field is resolved
by a documented precedence — verified > calculated > user_asserted > estimated — and that
resolution is a *function*, not a stored column, so it cannot silently drift.

### `property_price_history`
`property_id`, `price_cents`, `event` (`listed, reduced, increased, relisted, sold`),
`event_date`, `provenance_id`. In V1 populated only from what the user supplies.

---

## 3. Location

### `locations`
One row per geocoded point we have enriched. Holds coordinates and **our derived metrics** —
permanently, because the self-hosted OSM stack is ODbL (ADR 0002 §1).

### `location_metrics`
| Column | Type |
|---|---|
| location_id | uuid FK |
| metric | text (`commute_minutes_car`, `walk_amenity_count_800m`, `nearest_grocery_m`, …) |
| value | numeric |
| unit | text |
| provenance_id | uuid FK |
| computed_at | timestamptz |
| expires_at | timestamptz NULL |

`expires_at` exists for any provider whose policy caps retention. In the free stack nothing does,
but the column and its sweeper stay — the mechanism is what keeps a future restricted provider
from being wired in carelessly.

---

## 4. Provenance — the spine

### `data_sources`
One row per provider. `key`, `name`, `licence_class` (`open, licensed, restricted, prohibited`),
`may_store_values`, `max_retention_days`, `attribution_text`, `source_url`, `terms_url`,
`reviewed_at`. **A `prohibited` row exists on purpose** — REALTOR.ca and the portals are recorded
here so that any attempt to attach a fact to them fails a foreign-key-plus-check rather than
being a code review question.

### `data_provenance`
Every externally sourced or derived fact.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| data_source_id | uuid FK | |
| source_class | enum | `verified, calculated, estimated, assumed, ai_inferred, user_asserted, unavailable` |
| retrieved_at | timestamptz | when we got it |
| effective_at | timestamptz NULL | when it was true (assessment year, by-law year, sale date) |
| confidence | numeric(4,3) | 0–1 |
| expires_at | timestamptz NULL | enforced by the retention sweeper |
| unavailable_reason | text NULL | required when `source_class = 'unavailable'` |
| notes | text NULL | |

CHECK: `source_class = 'unavailable'` implies `unavailable_reason IS NOT NULL`. **A missing
value must state why it is missing** — that constraint is the product's central promise written
as SQL.

### `rules`
The versioned rule registry (ADR 0001 §4).

| Column | Type |
|---|---|
| id | uuid PK |
| jurisdiction | text (`CA`, `ON`, `ON/Toronto`) |
| rule_name | text (`ltt.brackets`, `mltt.brackets`, `mqr.floor`, `insured.max_price_cents`, …) |
| value | jsonb |
| effective_from | date NOT NULL |
| effective_to | date NULL |
| source_url | text NOT NULL |
| verification | enum (`primary, secondary, unverified`) |
| active | boolean NOT NULL |
| version | integer |

UNIQUE `(jurisdiction, rule_name, version)`. CHECK: `verification = 'unverified'` implies
`active = false` — nothing unverified can reach a calculation, enforced by the database rather
than by care.

### `rule_sets`
A named, immutable snapshot: `id`, `label` (`2026.09.1`), `resolved_at`, `rule_ids uuid[]`.
Every analysis stores the `rule_set_id` it used, which is what makes a replay exact.

---

## 5. Analysis

### `property_analyses`
Immutable. A re-run inserts a new row.

`id`, `user_id`, `property_id`, `financial_profile_id`, `buyer_preferences_id`, `rule_set_id`,
`scoring_model_version`, `buy_score` (smallint NULL — **nullable, because the model withholds it
when more than 35% of weight is unavailable**), `score_withheld_reason`, `confidence`,
`weights_applied` jsonb, `inputs_hash` (sha256 of the canonical input bundle),
`fair_value_low_cents`, `fair_value_high_cents`, `suggested_offer_low_cents`,
`suggested_offer_high_cents`, `monthly_ownership_cost_cents`, `closing_costs_cents`,
`cash_required_cents`, `created_at`.

`inputs_hash` is what proves reproducibility: same hash plus same versions must yield the same
score, and there is a test that asserts it.

### `analysis_scores`
Per component: `component` enum, `raw_value`, `subscore`, `base_weight`, `effective_weight`,
`contribution`, `confidence`, `available` boolean, `unavailable_reason`.

### `analysis_factors`
The sentences the UI renders and the AI layer is allowed to use: `component`, `direction`
(`positive, negative, neutral`), `magnitude`, `sentence`, `provenance_ids uuid[]`.
**If a factor is not in this table, it may not appear in an explanation.**

### `risk_flags`
`category` enum (`flood, zoning, development, environmental, condition, tax, condo_fee,
special_assessment, price_history, insurance, infrastructure, noise`), `severity`
(`low, medium, high`), `status` (`confirmed, potential, unknown`), `evidence` text,
`provenance_id`, `distance_m` NULL, `explanation`, `recommended_action`.

`status = 'unknown'` rows reduce analysis confidence and **must not** reduce the Risk subscore
(`SCORING_MODEL.md` §6). Enforced in the engine and asserted in tests.

### `calculation_traces`
Every financial figure's working, stored so the UI can show it and an auditor can check it:
`analysis_id`, `step_name`, `formula`, `inputs` jsonb, `output` jsonb, `unit`,
`assumptions` jsonb, `rule_ids uuid[]`.

### `mortgage_scenarios`, `financial_scenarios`
Scenario runs against an analysis: `changed_assumptions` jsonb plus the recomputed outputs.

### `ai_judgements`, `analysis_judgements`
The ADR 0004 channel. A judgement stores the validated `output`, the quoted
`evidence`, `confidence`, the `influence_cap` that applied, plus `model_id`,
`prompt_hash`, `sampling` and `judgement_version` — everything needed to replay it
rather than re-ask for it. `analysis_judgements` records which pinned judgements an
analysis consumed and what each one actually moved, with a `capped` flag (a
judgement that is always capped is calibrated wrong, and that is worth counting).

`risk_flags.ai_judgement_id` carries a CHECK: a flag sourced from a judgement must
have `status = 'potential'`. A model may raise a suspicion; only a data source can
confirm one.

### `ai_reports`
`analysis_id`, `model`, `prompt_hash`, `output` jsonb (summary, pros, cons, explanation,
questions, what_would_change), `validated_at`, `numeric_guard_passed` boolean, `created_at`.
The guard flag is stored because "the model tried to invent a number" is an event worth counting.

---

## 6. Comparables

### `comparables`
`id`, `owner_user_id` **NOT NULL** — user-supplied comps are scoped to their supplier and are
never pooled (`DATA_LICENSING.md` §3.6). Plus `address`, `geom`, `sale_price_cents`, `sale_date`,
attributes jsonb, `provenance_id`.

There is deliberately **no global comparable pool** in V1. Adding one is a licensing decision,
not a schema migration, and the `owner_user_id NOT NULL` constraint makes that explicit.

### `comparable_scores`
`analysis_id`, `comparable_id`, `similarity` numeric(4,3), `distance_m`, `included` boolean,
`inclusion_reason`, `exclusion_reason`, `weight`.

---

## 7. Market and user surfaces

- **`market_snapshots`** — `jurisdiction`, `as_of`, `metric`, `value`, `publisher`,
  `provenance_id`. Market context is dated data, never a constant in code.
- **`saved_properties`**, **`property_comparisons`** (`analysis_ids uuid[]`, computed verdicts).
- **`audit_logs`** — `actor_user_id`, `action`, `entity`, `entity_id`, `at`, `ip_hash`.
  Financial-profile reads and writes are audited; **values are never recorded**, only the fact of
  access.

---

## 8. Indexing

`properties(address_normalized)`; GIST on `properties.geom`, `comparables.geom`;
`property_attributes(property_id, field)`; `property_analyses(user_id, created_at DESC)`;
`data_provenance(data_source_id, retrieved_at)`; partial index on
`data_provenance(expires_at) WHERE expires_at IS NOT NULL` for the sweeper;
`rules(jurisdiction, rule_name, effective_from DESC) WHERE active`.

---

## 9. What the schema refuses to allow

1. A fact with no source — `data_provenance` is not nullable on any externally sourced field.
2. A missing value with no reason — CHECK constraint on `unavailable`.
3. An unverified rule in a calculation — CHECK constraint on `active`.
4. A comparable that belongs to everybody — `owner_user_id NOT NULL`.
5. A recomputed analysis silently replacing an old one — no UPDATE path on `property_analyses`.
6. Money in floats — no `double precision` column exists in a financial path.
