# Research Report — AI Property Decision Engine (Ontario)

**Status:** Phase 0 research. No application code exists yet.
**Research performed:** 2026-09-03. Every external fact below carries a source and, where the
fact is a rule or a rate, an effective date. Where a claim could not be verified against a
primary source it is labelled **[UNVERIFIED]** and must not be relied on in code.

---

## 0. How to read this document

The product's first principle is that data must be labelled by provenance. This report holds
itself to the same standard:

| Label | Meaning |
|---|---|
| **[PRIMARY]** | Verified against the issuing authority's own page (ontario.ca, toronto.ca, cmhc-schl.gc.ca, crea.ca, osfi-bsif.gc.ca) |
| **[SECONDARY]** | From a reputable industry source (Ratehub, WOWA, CMT, law-firm commentary); good enough to plan with, must be re-verified before it lands in a rule table |
| **[UNVERIFIED]** | Encountered but not confirmed; an open question, not a finding |

Nothing here is legal advice. Sections 5 and 9 identify items needing a Canadian lawyer and,
for the mortgage-adjacent surfaces, a FSRA-aware reviewer before launch.

---

## 1. The central finding

**Everything this product wants to do is achievable without MLS access except one thing:
knowing what comparable properties actually sold for.**

In Ontario, recent sold prices are not public data. They are the private asset of the real
estate boards (via MLS) and of Teranet (via the land registry). Every route to them is gated
on being — or being contracted to — a licensed brokerage or board member:

- **CREA's DDF** is member-gated *and*, decisively, **display-only**. The DDF Policy and Rules
  (revised January 2024, §5(d)) state participants "may not use the Listing Content they
  receive through the DDF for any purpose other than: (i) to display on their National Pool
  Websites and Member Websites; (ii) to create a mobile app, the sole purpose of which is to
  advertise the Listing Content...; and (iii) to create marketing materials for their own
  Listing Content only." §5(i) adds that no portion may be "used or provided to any person or
  corporation for any purpose other than those expressly provided." §6 requires the "Powered by
  REALTOR.ca" logo, brokerage attribution and CREA watermarks on every displayed listing, and
  §5(k) obliges participants to actively defend their own site against scraping. On
  termination, "the Participant shall not display any Listing Content from the DDF and must
  destroy any and all local copies." **[PRIMARY]**

  A comparable-based valuation is not display. **DDF cannot legally feed a Value Score even if
  we obtained it.** This is the most important licensing fact in the entire report.

- **Board feeds (IDX / VOW / DLA).** In Ontario, TRREB data flows through PropTx and requires
  all three agreement types, executed by a licensed brokerage. VOW — the tier carrying sold
  data — is quoted around $1,500/year on top of board membership. **[SECONDARY]**

- **Aggregators** (Repliers, from ~$199/month) are an *integration* layer only: "All MLS data
  access must be obtained directly from the applicable real estate board/association and
  through a licensed REALTOR/brokerage." **[SECONDARY]** They remove engineering work, not the
  licensing requirement.

- **Teranet / GeoWarehouse** carries registry sale prices; access runs through participating
  real estate board membership. Teraview seats are quoted around $3,804/user/year, with
  assessment values a further ~$6,340/user/year. **[SECONDARY — figures need a direct quote]**

- **OnLand** (Ontario Land Registry) is publicly searchable per parcel, pay-per-search, with no
  bulk or API entitlement. **[SECONDARY]**

- **MPAC** licenses Ontario assessment data commercially — custom bulk extracts, an API, and
  aggregated market profiles. This is a *real* route, priced by negotiation. Note that from
  2026-04-01 MPAC's richest residential product (including square footage) is bundled with
  PropTx MLS data into an appraisal subscription restricted to AIC/CNAREA members, which
  suggests MPAC licenses willingly but tiers its best data to regulated professions.
  **[PRIMARY — MPAC press release and Data Strategy pages]**

**Consequence.** The honest MVP does not claim to know sold comparables. It computes exactly
what it can compute (money, rules, fit, location, risk), states the comparable gap as
*unavailable data* rather than papering over it, and treats sold-comp acquisition as a
deliberate, licensed, later step. That is not a weakness in the plan — Section 6 argues it is
the differentiation.

---

## 2. Data ecosystem inventory

Per-source detail is in `/docs/data/DATA_SOURCES.md`; licence terms in
`/docs/data/DATA_LICENSING.md`. What the research established:

### 2.1 Freely licensed and genuinely usable

| Domain | Source | Note |
|---|---|---|
| Interest rates | **Bank of Canada Valet API** — no key, no cost, no registration | Posted conventional 5-year mortgage series (V80691333/4/5), policy rate, prime. **[PRIMARY]** |
| Census / demographics | **Statistics Canada** WDS and 2021 Census Profile (SDMX REST) plus boundary files | Open licence; CSV/JSON/XML; geography down to dissemination area. **[PRIMARY]** |
| Rental market | **CMHC HMIP / Rental Market Survey** — vacancy, average rent by bedroom count and centre | Source acknowledgement required under CMHC's data licence. **[PRIMARY]** |
| Schools | **EQAO Open Data** plus `data.ontario.ca` "School Information and Student Demographics" | EQAO publishes explicitly for reuse under Ontario's Digital and Data Directive, 2021. **[PRIMARY]** |
| Municipal | **Toronto Open Data** (CKAN, per-dataset API) under the **Open Government Licence – Toronto**: worldwide, royalty-free, modify and distribute, attribution required | Zoning By-law 569-2013, development applications, property boundaries. **[PRIMARY]** |
| Property tax rates | Municipal by-laws, published per municipality | Toronto 2026 residential rate 0.7673%, Ottawa 1.2271%, Mississauga 1.0339% **[SECONDARY]**. Ingest from by-laws, never from rate-aggregator sites |
| Flood | **Conservation authorities** — 36 of them, each with its own portal; Conservation Ontario holds floodplain-mapping metadata; roughly 22,000 km of flood-prone area mapped | Fragmented; coverage is *not* provincial. **[PRIMARY/SECONDARY]** |

### 2.2 Commercially licensed, priced, available to us

| Domain | Source | Note |
|---|---|---|
| Assessment / property attributes | **MPAC** commercial data (extracts, API, market profiles) | Best single route to beds/baths/sqft/year-built at Ontario scale. Priced by negotiation |
| Location scores | **Local Logic** — 14 location scores, demographics, neighbourhood profiles, climate; from ~$500/month **[SECONDARY]** | Buys most of the Location Score in one integration; also a cost floor and a dependency |
| Geocoding / places | **Google Maps Platform** | See the caching trap, 2.4 |
| Walkability | **Walk Score API** | The free tier is for "consumer-facing applications only"; subscription sites are directed to Enterprise **[SECONDARY]** — likely disqualifies the free tier for a paid product |

### 2.3 Gated on brokerage or board status

MLS listing content (CREA DDF; TRREB/PropTx IDX + VOW + DLA) and Teranet/GeoWarehouse registry
sales. See Section 1.

### 2.4 The Google Maps caching trap

Google's Maps Platform terms prohibit exporting or scraping content for use outside the
services, and prohibit caching except where expressly permitted. The permissions are narrow:
latitude/longitude may be **temporarily cached for up to 30 consecutive calendar days** and
then must be deleted; **place IDs may be stored indefinitely.** **[PRIMARY — Maps Platform
Service Specific Terms; Geocoding and Places policies]**

Architectural consequence, recorded in `/docs/decisions/0001-initial-architecture.md`: the
`locations` table may durably store a place ID and *our own derived* metrics, but **must not**
durably store Google-sourced coordinates, place names, ratings or POI details. Either we
re-fetch, or we geocode with a provider whose licence permits storage. Building the schema the
naive way — a `locations` row full of cached Google fields — puts a licence violation at the
centre of the database.

---

## 3. Mortgage, tax and program rules (Ontario / Canada)

These become the seed contents of the versioned rule registry (brief, Phase 6). Each carries
jurisdiction, effective date and source. **None are to be hardcoded in business logic.**

### 3.1 Qualification

| Rule | Value | Effective | Source |
|---|---|---|---|
| Minimum qualifying rate (MQR), uninsured | greater of **5.25%** or contract rate **+ 2%** | current; reaffirmed into 2026 | OSFI **[PRIMARY]** |
| MQR exemption on a straight switch at renewal | no re-test where amount and amortization are unchanged | 2024-11-21 | OSFI / CMT **[SECONDARY]** |
| GDS limit (insured) | **39%** | current | CMHC **[SECONDARY]** |
| TDS limit (insured) | **44%** | current | CMHC **[SECONDARY]** |
| Heat cost floor inside GDS | ~$100/mo condo, ~$150/mo house | current | industry practice **[SECONDARY]** |
| Condo fee inclusion in GDS | **50%** of the fee | current | CMHC **[SECONDARY]** |
| Minimum credit score (insured) | 600 | current | **[SECONDARY]** |

### 3.2 Default insurance

| Rule | Value | Effective | Source |
|---|---|---|---|
| Maximum insurable purchase price | **$1,500,000** | 2024-12-15 | **[SECONDARY]** |
| 30-year amortization eligibility | first-time buyers **or** new builds | 2024-12-15 | **[SECONDARY]** |
| Minimum down payment | 5% to $500k; 10% on the portion $500k–$1.5M; 20% above $1.5M | current | **[SECONDARY]** |
| Premium, LTV up to 65% | 0.60% | current | CMHC **[PRIMARY]** |
| 65.01–75% | 1.70% | current | CMHC **[PRIMARY]** |
| 75.01–80% | 2.40% | current | CMHC **[PRIMARY]** |
| 80.01–85% | 2.80% | current | CMHC **[PRIMARY]** |
| 85.01–90% | 3.10% | current | CMHC **[PRIMARY]** |
| 90.01–95% | 4.00% (4.50% on a non-traditional down payment) | current | CMHC **[PRIMARY]** |
| 30-year amortization surcharge | reported **+0.20%** | 2024-12-15 | **[UNVERIFIED]** — absent from CMHC's consumer premium page; confirm before use |

The premium is added to the principal and amortized. Ontario also charges **RST 8% on the
premium**, payable at closing rather than financed — **[UNVERIFIED]**; confirm with the Ontario
Ministry of Finance before it enters the closing-cost engine.

### 3.3 Ontario Land Transfer Tax **[PRIMARY — ontario.ca]**

Marginal, on the value of the consideration, for agreements after 2016-11-14:

| Portion | Rate |
|---|---|
| up to $55,000 | 0.5% |
| $55,000.01–$250,000 | 1.0% |
| $250,000.01–$400,000 | 1.5% |
| over $400,000 | 2.0% |
| over $2,000,000 (one or two single-family residences only) | 2.5% |

First-time buyer refund: up to **$4,000** — full relief to roughly **$368,000** of price.
**[SECONDARY]**

### 3.4 Toronto Municipal Land Transfer Tax **[PRIMARY — toronto.ca]**

Property with one or two single-family residences, **effective 2026-04-01**:

| Portion | Rate |
|---|---|
| up to $55,000 | 0.5% |
| $55,000.01–$250,000 | 1.0% |
| $250,000.01–$400,000 | 1.5% |
| $400,000.01–$2,000,000 | 2.0% |
| $2,000,000.01–$3,000,000 | 2.5% |
| $3,000,000.01–$4,000,000 | **4.40%** |
| $4,000,000.01–$5,000,000 | **5.45%** |
| $5,000,000.01–$10,000,000 | **6.50%** |
| $10,000,000.01–$20,000,000 | **7.55%** |
| over $20,000,000 | **8.60%** |

All other property: 0.5 / 1.0 / 1.5 / 2.0%, top band from $400,000. MLTT administration fee
**$102.56 + HST**; post-registration rebate processing fee **$221.22**. Toronto first-time
purchaser rebate up to **$4,475**; conditions include age 18+, occupancy as principal residence
within 9 months, never having owned a home anywhere in the world, and Canadian citizenship or
permanent residence (or attaining it within 18 months). **[PRIMARY]**

The April 2026 luxury bands are the best single argument for a versioned rule registry: any
system that hardcoded Toronto MLTT in 2025 is now silently wrong above $3M.

### 3.5 Buyer programs

| Program | Value | Source |
|---|---|---|
| FHSA annual contribution | **$8,000** (up to $16,000 in a year with carry-forward) | **[SECONDARY]** |
| FHSA lifetime | **$40,000** | **[SECONDARY]** |
| RRSP Home Buyers' Plan withdrawal | **$60,000** per person | CRA **[SECONDARY]** |
| HBP and FHSA on the same home | permitted; conditions tested at each withdrawal | CRA **[SECONDARY]** |

### 3.6 Other transfer taxes

Non-Resident Speculation Tax: **25%**, province-wide, on residential property with one to six
single-family residences, effective 2022-10-25. Toronto adds a **10%** Municipal NRST from
2025-01-01, for a combined 35%. **[SECONDARY]** This affects a minority of users and is a
catastrophic omission for the ones it hits, so the closing-cost engine must ask residency
status rather than assume it.

### 3.7 Market context at the time of writing

BoC policy rate **2.25%** (held 2026-09-02, seventh consecutive hold); prime **4.45%**; best
five-year fixed roughly **3.94%–4.09%** depending on insured status and source. TRREB July 2026
average price **$940,800** (−5.4% y/y), sales-to-new-listings 41% (balanced). Ontario-wide MLS
HPI composite benchmark **$749,800** (−3.9% y/y), average price **$797,486**, around 96 days on
market. **[SECONDARY]**

These are *context*, not constants. They belong in a dated market snapshot, never in code.

---

## 4. Competitor analysis

### HouseSigma
- **What it does:** free consumer portal for Ontario and BC with AI home-value estimates, sold
  history and comparable sales; markets newer risk analysis, estimate confidence and area
  supply/demand ratios. Licensed brokerage; 2M+ registered users. **[SECONDARY]**
- **Data:** the real asset — board MLS data including solds, held by virtue of being a brokerage.
- **Money:** free to the user; the agent relationship is the product.
- **Weakness:** it answers "what is this worth, and what sold nearby," not "should *I* buy
  *this*." It knows nothing about the user's income, debts, down payment, FHSA, commute or
  horizon. The estimate is a black box with a confidence badge, not a decomposition.
- **Opportunity left open:** the entire personal dimension, and explainability.

### Wahi
- Instant home value estimates with a claimed ~90% accuracy, up to 21 years of sold history,
  per-address valuation drivers and error margins, AI listing notes (July 2025), co-buyer
  tools; licensed, GTA-focused. **[SECONDARY]**
- **Weakness:** same shape — valuation-first, user-agnostic. Its transparency about drivers and
  error margins is the closest competitor behaviour to our thesis and is worth studying.

### Zoocasa
- Search portal *and* registered brokerage (ON, BC, AB, NS); wholly owned by eXp World Holdings
  since 2022; agent lead generation is the business. **[SECONDARY]**

### Houseful
- An **RBC** platform combining real estate and financing, licensed as a brokerage in ON, AB,
  MB and BC, referring buyers to licensed agents, with AI that predicts a buyer's next action.
  **[SECONDARY]**
- **The closest strategic threat:** a bank that owns the mortgage relationship moving into the
  buying decision. Its structural advantage is financing; its structural constraint is that a
  lender-owned tool cannot credibly tell you not to buy.

### REALTOR.ca (CREA)
- The listing system of record. Terms prohibit commercial use, screen scraping and database
  scraping. **[PRIMARY — restated inside the DDF Rules]** Treat as un-ingestible.

### Zillow / Redfin in Canada
- **[UNVERIFIED]** — search surfaced a 2019-era Redfin Canada launch announcement and generic
  US comparisons. Whether either runs a Canadian consumer AVM today is unresolved. Do not cite
  in product materials until confirmed.

### Local Logic
- Not a competitor but a **supplier** (and a plausible acquirer of this category). 250M+ North
  American addresses; location, demographic, neighbourhood and climate APIs; from ~$500/month.
  **[SECONDARY]**

### The pattern
Every Canadian incumbent is, underneath, a **lead-generation business for real estate agents or
for a bank**. Revenue arrives when a transaction happens. None of them can wholeheartedly ship
the sentence *"this is a bad purchase for you — walk away"*, and that sentence is the product.

---

## 5. Regulatory findings

- **Mortgage brokering (Ontario MBLAA 2006, administered by FSRA).** No person may deal or
  trade in mortgages for remuneration without a licence, and "dealing" is defined broadly
  enough to include soliciting, assessing, underwriting and **providing information on
  borrowing or lending through mortgages**. O. Reg. 407/07 sets out exemptions, and a *simple
  referral* exemption exists subject to prescribed disclosure, limited information sharing and
  the borrower's written consent. **[SECONDARY]**
  **Design consequence:** present a *qualification estimate*, framed as an estimate computed
  from published rules, never a lender-specific recommendation, never remunerated by a lender.
  The moment a referral fee appears, the referral exemption's conditions become mandatory.
  **This needs FSRA-aware legal review before launch.**
- **Real estate trading (TRESA).** We do not list, trade or represent parties. Details
  **[UNVERIFIED]**; same review, with attention to anything resembling advice on an offer price.
- **AI regulation.** There is **no Canadian AI act in force.** AIDA (inside Bill C-27) died when
  Parliament was prorogued on **2025-01-06**, and as of mid-2026 no successor has been
  introduced. What governs is a patchwork: PIPEDA; the OPC's reading of its fairness principles
  as requiring transparency about automated decision-making and recourse where decisions carry
  significant consequences; Quebec's Law 25 automated-decision rules (relevant only on
  expansion); ISED's voluntary code; OSFI E-23 model risk (binding on federally regulated
  institutions, not on us, but a useful template). **[SECONDARY]**
  **Design consequence:** transparency, reproducibility and human recourse are the closest thing
  to a compliance regime this product has. Build to the strictest plausible future rule rather
  than to the current vacuum.
- **Privacy (PIPEDA).** Income, debts, savings balances and credit-score bands are sensitive.
  Minimize, encrypt at rest, never log, and make deletion a first-class path.

---

## 6. Differentiation

Not "AI for real estate." The defensible position is narrower and harder to copy:

1. **We are the only party in the flow with no transaction incentive.** Portals monetize agent
   leads; banks monetize mortgages. A paid analysis product can say no.
2. **Personal fit is the axis nobody computes.** Competitors value *the property*. We evaluate
   *the match* between a property and one household's income, debts, FHSA/HBP capacity,
   commute, size, horizon and risk posture — exactly the data the portals never ask for.
3. **Determinism and reproducibility.** Same inputs plus same model version yields the same
   score, with every input, formula, assumption and source printable. No competitor exposes the
   arithmetic.
4. **Provenance as a visible product surface.** "Data unavailable" and confidence bands as
   first-class UI states differentiate precisely because they cost incumbents credibility to
   imitate.
5. **Ontario-rule depth.** Toronto's April 2026 luxury MLTT, NRST/MNRST, the FHSA + HBP
   interaction, the insured $1.5M cliff, 30-year amortization eligibility — modelled exactly,
   versioned and dated.

The moat is not the model. It is (a) the rule corpus with effective dates, (b) the provenance
graph, and (c) eventually a licensed comparable dataset — in that order.

---

## 7. What can be built without MLS

**Fully, today:** onboarding and financial profile; mortgage math and a qualification estimate;
closing costs including Ontario LTT, Toronto MLTT and NRST; monthly ownership cost;
affordability scoring and stress scenarios; personal-fit scoring; location intelligence; risk
flags from open municipal, flood and zoning data; the scenario engine; rent-vs-buy; AI
explanation over structured facts; saved properties and comparison.

**Partially:** the Value Score — computable from asking price against user-supplied or
assessment-derived attributes plus market-level benchmarks (HPI, average price, days on
market), presented as a **wide** fair-value range at **low confidence**, explicitly labelled as
lacking sold comparables.

**Not at all:** true comparable-sales analysis, sold price history, listing-specific days on
market (unless the user supplies it), and any claim of AVM-grade accuracy.

**The MVP therefore ships twelve of the thirteen promised outputs at full strength and one —
fair value — with an honest confidence penalty.** `/docs/scoring/SCORING_MODEL.md` §7 defines
how missing data reduces confidence and redistributes weight instead of silently scoring zero.

---

## 8. Risk register

### Technical
| Risk | Severity | Mitigation |
|---|---|---|
| Provider licences forbid the storage the schema assumes (Google) | High | Provenance layer enforces a per-field storage policy; TTL sweeper; adapters declare retention |
| Listing URL and PDF extraction is unreliable and legally fraught | High | LLM extracts into a strict Pydantic schema, always user-confirmed; no scraping of prohibited sites; user-initiated upload only |
| 36 conservation authorities means 36 flood integrations | Medium | Start with the CA covering the pilot region; elsewhere return "Data unavailable", never "no flood risk" |
| Rule drift (rates, brackets, programs change mid-year) | High | Versioned rule tables with effective dates; scores stamped with the rule-set version; regression fixtures per version |
| Score reproducibility across model upgrades | Medium | The score record stores inputs, weights and model version; recompute-on-read is forbidden |

### Business
| Risk | Severity | Mitigation |
|---|---|---|
| Crossing the FSRA mortgage-advice line | High | Estimates only, no lender recommendation, no lender remuneration, legal review pre-launch |
| A bank-owned incumbent (Houseful/RBC) bundles the same analysis free | High | Compete on independence and depth; never take referral revenue that compromises it |
| Willingness to pay is unproven for a once-in-seven-years purchase | High | Price per analysis or per short subscription window, not annual SaaS |
| A published score that ages badly (buyer regrets the purchase) | Medium | Ranges not points; "what could change this"; a stored snapshot of what was known when |

### Data
| Risk | Severity | Mitigation |
|---|---|---|
| No sold comps means a weak Value Score | High | Honest confidence; an MPAC licence as the first paid data step; a brokerage-partner path to VOW later |
| User-entered property data is wrong or optimistic | High | Provenance marks it `user_asserted`; cross-check against assessment where licensed; flag contradictions |
| Temptation to scrape aggregators | High | Prohibited by policy; DATA_LICENSING.md is the gate — no source enters the system without a licence row |
| Free-tier terms (Walk Score) exclude paid products | Medium | Buy Local Logic, or compute our own amenity metrics from OSM and municipal data |

---

## 9. Open questions for the project owner

1. **Pilot geography.** Toronto proper (best open data, worst affordability, new luxury MLTT) or
   a 905 municipality? This decides the first flood, zoning and development integrations.
   **Still open.**
2. ~~**Budget for licensed data.**~~ **Answered 2026-09-04: no licence fees.** See
   [ADR 0002](../decisions/0002-zero-cost-data-strategy.md) — self-hosted OSM replaces Google,
   Walk Score and Local Logic; user-supplied comparables replace board data; user-entered
   attributes replace MPAC.
3. **Business model.** Per-analysis fee, subscription, or free with a later brokerage/lender
   relationship? The answer changes both the FSRA analysis and the independence claim.
   **Still open.**
4. **Brokerage strategy.** Deferred by ADR 0002, not closed: without it, the statistical/ML
   valuation in V3 has no corpus to learn from. Worth revisiting once V1 has users.
5. **Named legal review.** Who signs off on the mortgage-adjacent language before launch?
   **Still open.**

---

## 10. Source index

Government and primary:
- Ontario — Calculating Land Transfer Tax: https://www.ontario.ca/document/land-transfer-tax/calculating-land-transfer-tax
- City of Toronto — MLTT rates and fees: https://www.toronto.ca/services-payments/property-taxes-utilities/municipal-land-transfer-tax-mltt/municipal-land-transfer-tax-mltt-rates-and-fees/
- City of Toronto — MLTT rebate opportunities: https://www.toronto.ca/services-payments/property-taxes-utilities/municipal-land-transfer-tax-mltt/municipal-land-transfer-tax-mltt-rebate-opportunities/
- City of Toronto — Open Data Licence: https://www.toronto.ca/city-government/data-research-maps/open-data/open-data-licence/
- OSFI — Minimum qualifying rate for uninsured mortgages: https://www.osfi-bsif.gc.ca/en/supervision/financial-institutions/banks/minimum-qualifying-rate-uninsured-mortgages
- CMHC — Mortgage loan insurance cost: https://www.cmhc-schl.gc.ca/consumers/home-buying/mortgage-loan-insurance-for-consumers/cmhc-mortgage-loan-insurance-cost
- CMHC — Rental Market Survey data tables: https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/rental-market
- Bank of Canada — Valet API: https://www.bankofcanada.ca/valet/docs
- Bank of Canada — policy rate release, 2026-09-02: https://www.bankofcanada.ca/2026/09/fad-press-release-2026-09-02/
- Statistics Canada — Developers: https://www.statcan.gc.ca/en/developers
- Statistics Canada — 2021 Census Profile Web Data Service: https://www12.statcan.gc.ca/wds-sdw/2021profile-profil2021-eng.cfm
- CRA — The Home Buyers' Plan: https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/what-home-buyers-plan.html
- EQAO — Open Data: https://www.eqao.com/about-eqao/open-data/
- Ontario Data Catalogue — School information and student demographics: https://data.ontario.ca/dataset/school-information-and-student-demographics
- Conservation Ontario — Floodplain mapping: https://conservationontario.ca/conservation-authorities/flood-erosion-management/floodplain-mapping
- Ontario — Flood hazard identification and mapping: https://www.ontario.ca/page/flood-hazard-identification-and-mapping
- MPAC — Data Strategy: https://www.mpac.ca/en/OurServices/DataStrategy
- MPAC — PropTx partnership, 2026-04-01: https://www.mpac.ca/en/News/PressRelease/PropTxpartnersMPACdeliverOntariosmostcomprehensiveresidentialappraisaldatasolution

Industry and licence:
- CREA — DDF Policy and Rules, revised January 2024: https://www.crea.ca/files/technology/english/DDFR-Policy-and-Rules-February-2024-ENG.pdf
- CREA — DDF support: https://support.crea.ca/DDF
- Google Maps Platform — Service Specific Terms: https://cloud.google.com/maps-platform/terms/maps-service-terms
- Google — Geocoding API policies: https://developers.google.com/maps/documentation/geocoding/policies
- Repliers — Guide to MLS data feeds in Ontario: https://repliers.com/a-comprehensive-guide-to-mls-data-feeds-in-ontario/
- Local Logic — pricing: https://locallogic.co/pricing/ and location scores: https://locallogic.co/platform/datasets/location-scores/
- Walk Score — professional pricing: https://www.walkscore.com/professional/pricing.php
- Teranet — Teranet Ontario: https://www.teranet.ca/registry-solutions/teranet-ontario/

Market and commentary (secondary):
- Ratehub — Ontario land transfer tax: https://www.ratehub.ca/land-transfer-tax-ontario
- Canadian Mortgage Trends — OSFI leaves the stress test in place, January 2026: https://www.canadianmortgagetrends.com/2026/01/osfi-leaves-mortgage-stress-test-in-place-reaffirms-lti-limits-for-lenders/
- WOWA — CMHC mortgage rules: https://wowa.ca/cmhc-mortgage-rules
- TRREB — Market outlook: https://market-outlook.trreb.ca/
- Storeys — eXp acquires Zoocasa: https://storeys.com/canadian-real-estate-brokerage-zoocasa-acquired-by-exp-realty/
- HousingWire — Houseful company profile: https://www.housingwire.com/company-profile/houseful/
