# Scoring Model v0.1 (proposal)

**Status:** Phase 0 proposal. Not implemented. Thresholds below are **starting points that have
not been validated against outcomes** — §9 sets out how they get earned.

**Version identifier:** `scoring_model_version = "0.1.0"`. Every stored score carries it. A
score computed under 0.1.0 is never silently recomputed under 0.2.0.

---

## 1. Non-negotiables

1. **The LLM never produces or adjusts a score.** It reads the finished decomposition and
   explains it.
2. **Determinism.** `(inputs, rule_set_version, scoring_model_version)` fully determines the
   result. No wall-clock reads, no randomness, no network inside the scoring engine.
3. **Every subscore is explainable in one sentence** naming its inputs and their contributions.
4. **Missing data lowers confidence; it does not lower the score.** Scoring an unknown as zero
   is fabrication in the other direction.
5. **Ranges over points** wherever the underlying quantity is uncertain.

---

## 2. Aggregation

```
buy_score = round( Σ (subscore_i × effective_weight_i) )
effective_weight_i = base_weight_i × user_modifier_i × availability_i  (renormalized to 1.0)
```

Base weights (from the brief), configurable and versioned:

| Component | Base weight |
|---|---|
| Affordability | 25% |
| Value | 20% |
| Personal fit | 15% |
| Location | 10% |
| Property quality | 10% |
| Investment potential | 8% |
| Risk | 7% |
| Market conditions | 5% |

**`availability_i`** is 1.0 when a subscore has enough inputs, 0.0 when it does not. A subscore
that cannot be computed is dropped and its weight is redistributed proportionally across the
rest — *and the analysis-level confidence falls*, which is how the user learns something is
missing. Weight redistribution is capped: if total redistributed weight exceeds **35%**, the
Buy Score is withheld entirely and the UI shows subscores only. A composite built from a third
of nothing is not a score.

**`user_modifier_i`** comes from the buyer profile, clamped to [0.5, 2.0]:

| Profile signal | Effect |
|---|---|
| Goal = investment | Investment ×1.75, Personal fit ×0.6 |
| Goal = primary residence | Personal fit ×1.2, Investment ×0.7 |
| Children in household, schools rated important | Location ×1.4, Property quality ×1.15 |
| Horizon < 3 years | Value ×1.3, Investment ×1.2, Risk ×1.2 |
| Horizon 10+ years | Value ×0.85, Personal fit ×1.2 |
| Monthly budget within 10% of computed ownership cost | Affordability ×1.4 |
| Risk posture = conservative | Risk ×1.4 |
| Risk posture = aggressive | Risk ×0.7 |

Modifiers multiply, then all weights renormalize to sum to 1. The applied weight vector is
stored with the analysis, so the user can be shown *why their score differs from someone else's
on the same house.*

---

## 3. Affordability (25%)

Inputs: monthly ownership cost, gross household income, monthly debt obligations, stated maximum
housing budget, down payment, qualification estimate, emergency fund.

Four sub-metrics, each scored 0–100, then combined:

| Metric | Definition | Weight within |
|---|---|---|
| Housing ratio | ownership cost ÷ gross monthly income | 30% |
| Total debt ratio | (ownership cost + debts) ÷ gross monthly income | 25% |
| Budget adherence | ownership cost ÷ stated maximum | 25% |
| Reserve months | liquid savings after closing ÷ ownership cost | 20% |

Starting piecewise anchors (**unvalidated**), interpolated linearly between points:

- Housing ratio: 0.25 → 100, 0.32 → 75, 0.39 → 50, 0.45 → 25, 0.55 → 0
  (0.32/0.39 chosen to sit near conventional GDS practice and the insured 39% limit)
- Total debt ratio: 0.30 → 100, 0.38 → 75, 0.44 → 50, 0.50 → 25, 0.60 → 0
  (0.44 is the insured TDS ceiling)
- Budget adherence: ≤0.85 → 100, 1.00 → 70, 1.10 → 40, 1.25 → 0
- Reserve months: ≥6 → 100, 3 → 70, 1 → 35, 0 → 0

The brief's published interpretation bands (90–100 very comfortable … 0–39 likely unaffordable)
are retained as *labels*, and the anchors above are what produce them.

**"Can afford" is not "may qualify."** The Affordability Score answers the first. The
qualification estimate — MQR-stressed payment, GDS/TDS against published limits, insured
eligibility — is reported next to it as a **separate, clearly labelled estimate that only a
lender can confirm**. The two are never merged into one number.

---

## 4. Value (20%)

**v1 (MVP).** Inputs: asking price, property attributes, municipal/market benchmarks (MLS HPI
benchmark for the area, average price, days on market), price per square foot where sqft is
known, **plus any comparable sales the user supplies** (ADR 0002 §3 — the user pastes what their
realtor sent, or types in what they looked up themselves).

```
fair_value_range = benchmark_value × attribute_adjustment × [1 − spread, 1 + spread]
```

`spread` and confidence are both driven by how much comparable evidence exists:

| Evidence | Spread | Confidence cap | UI must say |
|---|---|---|---|
| Market benchmarks only | ±12% | 45% | "No comparable sales — add some to narrow this" |
| 1–2 user-supplied comps | ±9% | 60% | how many comps, and how well they match |
| 3–5 comps, mean similarity ≥ 0.80 | ±6% | 75% | as above |
| 6+ comps, mean similarity ≥ 0.85 | ±4% | 85% | as above |

This turns the one genuinely gated dataset into a **dial the user can turn**: five minutes of
pasting produces a materially tighter range, and the UI says so rather than silently offering a
vague answer. The score is a function of where the asking price sits in the resulting range: at
or below the low bound → high score; above the high bound → falling, steeply past +10%.

**v2+ .** Statistical, then ML valuation. The interface — `(property, market_context, comps[]) →
FairValueRange + confidence + evidence[]` — is fixed now so the model behind it can be replaced
without touching the score.

Never emit a point value. "Estimated fair value $832,451" is a lie about precision even when the
midpoint is right.

---

## 5. Comparables (feeds Value)

Similarity is an explicit weighted distance, not a nearest-neighbour shortcut:

| Dimension | Weight | Notes |
|---|---|---|
| Geographic distance | 20% | decay by distance; neighbourhood boundary crossing penalized |
| Sale recency | 20% | decay per month; >12 months heavily penalized |
| Property type | 15% | hard filter in practice |
| Living area | 15% | % difference |
| Bedrooms / bathrooms | 10% | |
| Lot size | 8% | detached only |
| Age / year built | 7% | |
| Parking, basement, condition | 5% | |

Each comparable stores similarity, distance, sale date, attributes, **and the reasons for
inclusion or exclusion in plain language**. A comparable below 70% similarity is excluded and
the exclusion is shown, because "we ignored the cheap one across the tracks, here's why" is more
trust-building than a silent filter.

**Source of comparables in the MVP: the user.** The engine does not care where a comp came from
— it needs an address, a sale date, a price and whatever attributes are known. User-supplied
comps carry `user_supplied_comparable` provenance and a source-quality factor of 0.65 (§8), and
each one is stored scoped to that user; they are never pooled into a shared corpus, because
pooling MLS-derived figures across users recreates the licensing problem the design avoids.

Missing attributes on a comp reduce its similarity confidence rather than excluding it: a user
who knows only "sold $845k in June, same street, similar size" has still told us something worth
using, and the engine says how much weight it gave that.

---

## 6. The other subscores

**Personal fit (15%).** Requirement-by-requirement matching against the buyer profile. Hard
requirements (minimum bedrooms, parking if required, maximum commute) that fail cap the subscore
at 40 and are named. Soft preferences contribute proportionally. Exceeding a requirement gives
diminishing credit — a fourth bedroom for a couple who asked for two is not twice as good.

**Location (10%).** Commute time to the stated work location (the single heaviest input for most
buyers), transit access, grocery/healthcare/park proximity, school proximity *with the catchment
caveat*, walkability. Sourced per DATA_SOURCES §4; any component unavailable is dropped and
noted rather than defaulted.

**Property quality (10%).** Age, size versus household need, lot, bed/bath count, parking,
basement type, renovation and condition indicators where evidenced. Condition is the weakest
input in the MVP — most of it is user-asserted — so its internal weight is small and its
confidence is explicit. We do not infer condition from listing adjectives.

**Investment (8%).** Expected rent (CMHC RMS for the zone and bedroom count), operating costs,
mortgage constant, cash flow, cap rate, cash-on-cash, vacancy allowance, and appreciation
**scenarios** — never an appreciation *forecast*. If the user's goal is a primary residence this
subscore is reported but down-weighted per §2.

**Market conditions (5%).** Sales-to-new-listings ratio, months of inventory, days on market,
price trend, all from a dated `market_snapshot`. Never from a model's memory.

**Risk (7%).** Starts at 100 and is reduced by confirmed and potential flags. Confirmed flags
carry full severity weight; potential flags carry a fraction (start: 40%); **`UNKNOWN` reduces
confidence, not the score.** This is the rule that keeps "we couldn't check for flooding" from
masquerading as "this house floods".

---

## 6.5 AI judgements (ADR 0004)

A model may contribute to a subscore, and only through a capped, evidence-bearing,
**pinned** judgement. It never adjusts a finished score.

| Judgement | Subscore | Cap | Effect |
|---|---|---|---|
| `condition_signal` | Property quality | ±8 | Renovation recency, deferred maintenance, "as-is" framing |
| `listing_red_flags` | Risk | ±6 | Adds `POTENTIAL` flags only; never `CONFIRMED` |
| `omission_signals` | — | 0 | Generates questions; lowers confidence |
| `preference_interpretation` | Personal fit | 0 until confirmed | Becomes `USER_ASSERTED` on confirmation, then scores normally |
| `decision_review` | — | 0 | Surfaces an internal inconsistency for the user |

Three properties make this safe enough to leave in the scoring path:

1. **The cap is absolute.** `apply_judgement()` clamps after weighting, so no
   distribution of item weights and no claimed confidence can exceed the bound.
   A completely wrong judgement costs a couple of points on the Buy Score.
2. **Judgements are pinned, not regenerated.** The stored output, model id, prompt
   hash and sampling parameters are what the score is computed from, so
   reproducibility survives a nondeterministic model. Re-asking creates a new
   analysis, never a different answer to the old one.
3. **Contributions are labelled.** An AI-derived factor renders with its source
   class visible, at `AI_INFERRED` quality (0.5) in the confidence term of §8.

Unavailable model, failed validation, or missing evidence ⇒ the judgement is
unavailable, its contribution is zero, and §7 applies as for any other missing input.

## 7. Missing data

Each subscore declares its minimum viable input set. Behaviour:

1. **Optional input missing** → drop it, renormalize within the subscore, reduce that subscore's
   confidence, and record a `missing_input` factor row that surfaces in the UI.
2. **Required input missing** → the subscore is unavailable; weight redistributes (§2); the
   analysis-level confidence falls.
3. **Redistributed weight > 35%** → no Buy Score. Subscores and the money numbers still show.

The user always sees a list titled *what we could not check* — never a silent hole.

---

## 8. Confidence

Computed, not vibed:

```
confidence = Σ (weight_i × subscore_confidence_i)   # over available subscores
subscore_confidence = coverage × freshness × source_quality
```

- **coverage** = share of the subscore's inputs present, weighted by their internal importance
- **freshness** = decay on `retrieved_at`/`effective_at` (market data ages in weeks; assessment
  data in years)
- **source_quality** = per-provenance-class factor: verified 1.0, calculated 1.0, licensed
  third-party 0.9, estimated 0.7, user-asserted 0.65, AI-inferred 0.5

Reported as a percentage with its reasons: "8 strong comparables, recent sales, complete
attributes" versus "2 weak comparables, no sold data, square footage unconfirmed".

---

## 9. Calibration plan (how the thresholds get earned)

The anchors in §3–§6 are defensible priors, not validated parameters. Before v1.0:

1. **Fixture suite** — 30+ hand-built Ontario scenarios spanning the $400k/$500k/$1M/$1.5M/$2M
   price cliffs, Toronto and non-Toronto, first-time and repeat, condo and freehold. Verified
   against manual calculation and, for the money paths, against published calculators.
2. **Sensitivity analysis** — vary each anchor ±20%, measure Buy Score movement. Any anchor that
   moves the score more than 5 points on a typical file is over-powered and gets re-cut.
3. **Expert review** — a mortgage broker and a realtor walk 10 real files and flag anything
   that reads wrong.
4. **Outcome tracking (post-launch)** — for users who consent, compare the score at analysis
   time with what happened (did they buy, at what price, how did the ownership cost land).
   This is the only path to genuinely validated thresholds.

Until step 4 has data, the product must not describe the Buy Score as *accurate*. It is
*transparent and reproducible*, which is a different and more honest claim.

---

## 10. Stored artefact

```
property_analyses:      buy_score, confidence, scoring_model_version, rule_set_version,
                        weights_applied (JSON), inputs_hash, created_at
analysis_scores:        component, raw_value, subscore, base_weight, effective_weight,
                        contribution, confidence, availability
analysis_factors:       component, direction (+/−), magnitude, sentence, source_ids[]
risk_flags:             category, severity, status, evidence, source, distance_m,
                        explanation, recommended_action
```

`analysis_factors` is what the UI's "why we like it / what concerns us" lists render, and what
the AI layer is given to explain. If a factor is not in that table, it may not appear in the
explanation.
