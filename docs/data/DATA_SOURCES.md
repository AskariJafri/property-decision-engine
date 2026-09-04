# Data Sources

**Status:** Phase 0 inventory, researched 2026-09-03. Licence terms for each source are in
`DATA_LICENSING.md`; a source may not be integrated until it has a row in **both** files.

Confidence labels follow `/docs/research/RESEARCH_REPORT.md` §0.

---

## 1. Financial and rate data

### Bank of Canada — Valet API
- **What:** policy rate, prime, posted conventional mortgage rates (series V80691333/4/5),
  historical series for scenario anchoring.
- **Access:** `https://www.bankofcanada.ca/valet/` — no registration, no key, no cost. **[PRIMARY]**
- **Use:** default rate assumptions, rate-change scenarios, market snapshots.
- **Caveat:** *posted* rates are not *contract* rates. Users must be able to enter their own
  quoted rate, and the UI must say which one is in play.
- **Backup:** user-entered rate (always available, and always preferred when supplied).

### Mortgage contract rates (market)
- **Status: unsolved.** No free, licensed API of actual best-available broker rates was found.
  Ratehub/WOWA/nesto publish them on-page; scraping them is out of scope by policy.
- **MVP approach:** user enters their quoted rate; Valet posted rates provide the fallback
  default, clearly labelled as a posted-rate proxy and dated.

---

## 2. Property attributes

### MPAC (Municipal Property Assessment Corporation)
- **What:** assessed value, property class, and — in the richer products — structural
  attributes including square footage, for every property in Ontario.
- **Access:** commercial licensing; custom bulk extracts, an API, aggregated market profiles.
  Priced by negotiation. **[PRIMARY]**
- **Note:** from 2026-04-01, MPAC's residential appraisal bundle with PropTx is restricted to
  AIC/CNAREA members — evidence that the best tier is gated to regulated professions.
- **Use:** the single highest-value paid integration; turns user-asserted attributes into
  cross-checked ones.

### User input (MVP primary source)
- **What:** everything: beds, baths, sqft, lot, year built, parking, basement, condo fee,
  property tax, listing price.
- **Provenance:** `user_asserted`, confidence medium, flagged wherever it contradicts another
  source.

### Listing documents supplied by the user
- **What:** PDF, screenshot, or pasted text the user already possesses.
- **Pipeline:** LLM extraction into a strict schema, Pydantic validation, **user confirmation
  before anything is stored**.
- **Boundary:** the user uploads; we do not fetch from sites whose terms prohibit it.

---

## 3. Sold prices and comparables

### CREA DDF — **not usable for this product**
Display-only under the DDF Policy and Rules; see `/docs/research/RESEARCH_REPORT.md` §1.

### Real estate board feeds (TRREB via PropTx: DLA + IDX + VOW)
- **What:** the only comprehensive source of Ontario sold prices and true days-on-market.
- **Access:** licensed brokerage, board membership, three executed agreements; VOW around
  $1,500/year. **[SECONDARY]**
- **Status:** post-MVP, contingent on a brokerage relationship.

### Repliers (aggregator)
- **What:** normalized MLS API across Canadian and US boards, from ~$199/month. **[SECONDARY]**
- **Status:** an integration convenience once board authorization exists; not a way around it.

### Teranet / GeoWarehouse / OnLand
- **What:** registry sale prices and title data.
- **Access:** GeoWarehouse via participating board membership; OnLand pay-per-search, no bulk
  entitlement; Teraview seats quoted around $3,804/user/year plus ~$6,340/user/year for
  assessment values. **[SECONDARY — needs a direct quote]**

---

## 4. Location intelligence

### Google Maps Platform
- **Use:** geocoding, distance/commute matrices, place lookups.
- **Hard constraint:** content may not be cached or stored except **place IDs (indefinitely)**
  and **coordinates (up to 30 consecutive days)**. **[PRIMARY]**
- **Consequence:** derive metrics, store metrics, discard content. See
  `/docs/decisions/0001-initial-architecture.md`.

### Local Logic
- **What:** up to 14 location scores (character, services, transportation) at address,
  neighbourhood, city and metro level; demographics; neighbourhood profiles; climate.
- **Access:** commercial, from ~$500/month. **[SECONDARY]**
- **Use:** the fastest credible Location Score; evaluate against building our own from open data.

### Walk Score
- **What:** Walk/Transit/Bike Score.
- **Access:** free tier restricted to consumer-facing applications; subscription products are
  directed to Enterprise. **[SECONDARY]**
- **Assessment:** probably unusable on the free tier for a paid product. Do not integrate before
  the licence question is answered in writing.

### OpenStreetMap / Overpass (fallback)
- **What:** POIs — groceries, schools, parks, clinics, transit stops.
- **Licence:** ODbL, attribution and share-alike on derived databases. **[SECONDARY]**
- **Use:** the independent path to amenity metrics if the commercial options are refused.

### Transit
- **What:** GTFS static feeds from municipal agencies and Metrolinx for stop proximity and
  service frequency.
- **Status:** per-agency licences to confirm; most publish openly. **[UNVERIFIED]**

---

## 5. Neighbourhood and demographics

### Statistics Canada
- **What:** 2021 Census Profile via SDMX REST; Web Data Service; boundary files
  (dissemination area, census tract, CSD, CMA).
- **Access:** open, CSV/JSON/XML, no key. **[PRIMARY]**
- **Use:** neighbourhood context, income and tenure mix, dwelling types, geographic joins.

### CMHC — Housing Market Information Portal
- **What:** Rental Market Survey: average rent by bedroom count, vacancy, availability, turnover,
  by centre and zone; housing starts and completions.
- **Access:** free, portal plus community wrappers; source acknowledgement required. **[PRIMARY]**
- **Use:** the rent input to the Investment Score, and the rent side of rent-vs-buy.

---

## 6. Schools

### EQAO Open Data
- **What:** assessment results by school and board, published for reuse under Ontario's Digital
  and Data Directive, 2021. **[PRIMARY]**

### Ontario Data Catalogue — School Information and Student Demographics
- **What:** school locations, levels, enrolment, board attribution. **[PRIMARY]**
- **Gap:** **attendance boundaries** are held by individual boards, not published provincially.
  Until a boundary source exists, the product must say *nearby schools*, never *your school* —
  claiming a catchment we cannot verify is exactly the fabrication the brief prohibits.

---

## 7. Risk data

### Flood — Conservation Authorities (36 of them) and Conservation Ontario
- **What:** regulated areas, floodplain mapping; roughly 22,000 km mapped, about 90% riverine.
- **Access:** per-authority GIS portals and open-data sites; Conservation Ontario holds mapping
  metadata. **[PRIMARY/SECONDARY]**
- **Consequence:** coverage is *not* provincial. Outside a mapped area the honest answer is
  `UNKNOWN`, never "no flood risk". This is the sharpest test of the `CONFIRMED / POTENTIAL /
  UNKNOWN` discipline in the whole product.

### Zoning and development applications — municipal open data
- **Toronto:** Zoning By-law 569-2013 and development application datasets via CKAN under the
  Open Government Licence – Toronto. **[PRIMARY]**
- **Other municipalities:** varying portals and licences; each needs its own row here.
- **Use:** "development application 0.8 km away" style flags, with distance, status and a link.

### Infrastructure proximity
- **What:** rail corridors, highways, airports, transmission corridors.
- **Source:** municipal and provincial GIS, OSM. **[UNVERIFIED]** per layer.

---

## 8. Taxes and municipal charges

### Property tax rates
- **What:** residential rates by municipality, set annually by by-law (Toronto 2026: 0.7673%;
  Ottawa 1.2271%; Mississauga 1.0339% **[SECONDARY]**).
- **Approach:** ingest from municipal by-laws or municipal open data with the by-law year
  recorded; do not scrape rate-comparison sites.
- **Fallback:** where the rate is unknown, use the user's stated tax figure from the listing and
  mark it `user_asserted`; if neither exists, `unavailable`.

### Land transfer taxes and programs
Ontario LTT, Toronto MLTT (including the 2026-04-01 luxury bands), first-time rebates,
NRST/MNRST, FHSA, HBP — all captured with brackets, thresholds and effective dates in
`/docs/research/RESEARCH_REPORT.md` §3, and loaded into the rule registry from there.

---

## 9. Market context

- **TRREB / CREA published statistics** — average price, MLS HPI benchmark, sales-to-new-listings
  ratio, days on market. Published as reports and press releases, not as a licensed feed.
  Ingest as a dated `market_snapshot`; attribute the publisher. **[SECONDARY]**
- **CMHC** starts and completions for supply context. **[PRIMARY]**

---

## 10. Integration order (recommended)

1. Bank of Canada Valet (free, immediate, unblocks the financial engine's defaults)
2. Statistics Canada (free, unblocks neighbourhood context)
3. Municipal open data for the pilot city (free, unblocks zoning/development risk flags)
4. CMHC rental (free, unblocks the Investment Score)
5. Geocoding (paid, small; decide storage-permitting provider vs Google)
6. EQAO + Ontario school data (free)
7. Conservation authority for the pilot region (free)
8. **MPAC (paid)** — the first real cheque, and the biggest single jump in quality
9. Local Logic (paid) *or* an OSM-derived amenity engine
10. Board/VOW sold data (requires a brokerage relationship) — the moat step
