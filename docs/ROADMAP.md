# Roadmap

**Status:** Phase 0 output. Phases A–L follow the development strategy in the project brief.
Each phase ends with: tests run, code reviewed, errors fixed, documentation updated, commit.

---

## Development phases

| Phase | Theme | Exit criteria |
|---|---|---|
| **A ✅** | Research | The document set; pilot city and data budget answered (ADR 0002, 0003) |
| **B ✅** | Architecture | `DATABASE.md`, `API.md`, engine contracts, `ProviderPolicy` registry, repo scaffold; CI green — ruff, ruff format, mypy strict, 41 tests |
| **C** | Database | Alembic migrations for identity, property, provenance, analysis; migrations apply cleanly against Postgres in CI |
| **D** | Financial engine | Mortgage, insurance premium, LTT/MLTT/NRST, ownership cost, qualification estimate, stress cases — all pure, all fixture-tested, rule registry seeded and dated |
| **E** | Scoring engine | Subscores, weights, user modifiers, missing-data handling, confidence; reproducibility test passes across runs |
| **F** | Backend API | Profile, property, analyze, scenarios, compare; OpenAPI published; auth, rate limits, redacted logging |
| **G** | Frontend | Onboarding, dashboard, add property, analysis page, score breakdown, scenarios; the three data states (estimated / unavailable / low confidence) built before the happy path |
| **H** | Property ingestion | Manual, PDF, image, pasted text; strict-schema extraction with mandatory user confirmation |
| **I** | Location intelligence | Geocoding, commute, amenities, schools, transit; provider adapters with policy enforcement |
| **J** | AI explanation | Fact-bundle prompt, validated JSON output, numeric-token guard, caching |
| **K** | Testing | Financial fixtures at every price cliff, scoring regression, API tests, Playwright E2E, hallucination-prevention suite |
| **L** | Deployment | Managed Postgres, migrations gated in CI, secrets from environment, observability dashboards |

---

## The first four weeks

Assumes one engineer, no MLS data, pilot municipality chosen at the start of week 1.

### Week 1 — Foundation and the money that must be right
- Repo scaffold per `/docs/architecture/ARCHITECTURE.md` §2; CI (ruff, mypy, pytest) green.
- **Start the OSM box on day one** — Geofabrik Ontario extract importing into Nominatim, OSRM
  and Overpass in the background while other work proceeds. The import takes hours; starting it
  in week 3 would block week 3. OpenRouteService's free key covers development until it is up.
- `DATABASE.md`, then Alembic migrations for `users`, `user_profiles`, `financial_profiles`,
  `buyer_preferences`, `properties`, `property_attributes`, `data_sources`, `data_provenance`.
- Rule registry table plus the seed loader; load the `[PRIMARY]` rules from
  `RESEARCH_REPORT.md` §3, each with source URL and effective date. Nothing `[UNVERIFIED]`.
- Financial engine part one: amortization and payment maths, down payment rules, insured
  eligibility, CMHC premium bands.
- **Deliverable:** `pytest` proves a mortgage payment against hand calculation and against a
  published calculator, at $400k / $500k / $999,999 / $1.5M / $1,500,001 / $2M.

### Week 2 — Closing costs, qualification, and the rest of the money
- Ontario LTT, Toronto MLTT including the 2026-04-01 luxury bands, both first-time rebates with
  their eligibility tests, NRST/MNRST, legal, title, inspection, appraisal, moving, adjustments.
- Monthly ownership cost: mortgage, property tax, insurance, condo fees, utilities, maintenance
  reserve — each with input, formula, assumption and source attached to the output.
- Qualification estimator: MQR stress, GDS/TDS against the registry limits, insured eligibility,
  with "a lender confirms this" wired into the response object rather than added later in the UI.
- **Deliverable:** the Phase 30 fixture matrix passes — Toronto vs non-Toronto, first-time vs
  repeat, condo vs freehold, at every price cliff.

### Week 3 — Scoring, risk, and the API
- Scoring engine: all eight subscores, base weights, user modifiers, weight redistribution, the
  35% withholding rule, confidence computation.
- Risk engine with `CONFIRMED / POTENTIAL / UNKNOWN`; first real risk source (pilot
  municipality's development applications and zoning) behind a provider adapter with a policy.
- FastAPI surface: profile, property create, analyze, get analysis; OpenAPI published.
- **Deliverable:** an end-to-end analysis over a real Ontario address, JSON only, fully sourced,
  reproducible twice with identical output.

### Week 4 — The page a human reads
- Next.js app: onboarding (progressive disclosure, not fifty questions), add property, analysis
  page with score breakdown, financial breakdown, risks, scenarios.
- The three data states built as components first: estimated, data unavailable, low confidence.
- AI explanation layer with the numeric-token guard and caching.
- Playwright E2E: onboarding → add property → analysis → scenario.
- **Deliverable:** a person who is not us enters their situation and a real listing and gets a
  Buy Score they can explain to their partner without help.

**Explicitly not in the first four weeks:** ML valuation, rent-vs-buy, property comparison,
monitoring, mobile, payments. User-supplied comparables land in week 4 if the analysis page is
ahead of schedule, week 5 otherwise — the similarity engine is small, and the Value Score is
noticeably weak without it.

---

## Product versions

| Version | Theme |
|---|---|
| **V1** | The MVP above: analysis of one property against one household, no MLS, user-supplied comparables |
| **V2** | Depth on free data — more municipalities' zoning/development/flood layers, richer own-built location metrics, better cross-checks against open building and permit data |
| **V3** | Statistical then ML valuation behind the unchanged `FairValueRange` interface |
| **V4** | AI property search ("best 3-bed under $900k within 30 minutes of my office") |
| **V5** | Rent vs buy over 5/10/15 years with labelled assumptions |
| **V6** | Investment mode — cash flow, cap rate, house-hack modelling |
| **V7** | Agent/realtor dashboard (only once independence is structurally protected) |
| **V8** | Property monitoring and alerts |
| **V9** | Offer intelligence |
| **V10** | Home-buying copilot |

---

## Dependencies that gate the version plan

- **V1 requires** one OSM box and nothing else that costs money.
- **V3 (statistical/ML valuation) requires** a sold-transaction history of meaningful size. The
  free stack does not produce one: user-supplied comps are scoped to their own user and are not
  pooled (`DATA_LICENSING.md` §3.6). So V3 is genuinely blocked until either the owner reverses
  the zero-cost decision (MPAC, then a board/VOW relationship) or a consented, separately
  licensed corpus exists. **This is the real cost of the free stack** — not the MVP, the
  long-term valuation moat.
- **V4 (AI property search) requires** listing search, which requires MLS display rights — a
  fee and a brokerage relationship, and the point at which the DDF display-only rules bite
  again. Not reachable on free data.
- **V7 (agent dashboard)** should not ship before the independence question in
  `PRODUCT_THESIS.md` §6 is settled structurally.
