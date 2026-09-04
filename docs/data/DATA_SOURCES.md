# Data Sources — zero-cost stack

**Status:** revised 2026-09-04 per `/docs/decisions/0002-zero-cost-data-strategy.md`.
**Licence fees: $0.** Every source below is free to use commercially, or is supplied by the user.
Licence terms per source are in `DATA_LICENSING.md`; a source may not be integrated until it has
a row in **both** files.

Confidence labels follow `/docs/research/RESEARCH_REPORT.md` §0.

---

## 1. The self-hosted OSM core

One machine, one Ontario extract, three services. This replaces Google Maps, Walk Score and
Local Logic entirely, and its licence lets us store what Google's does not.

| Service | Purpose | Source data |
|---|---|---|
| **Nominatim** | Geocoding and reverse geocoding | Geofabrik Ontario extract |
| **OSRM** or **Valhalla** | Commute times, distance matrices, isochrones | same extract |
| **Overpass** | POI queries — groceries, schools, parks, clinics, transit stops | same extract |

**Why self-hosted rather than the public instances:** the OSMF Nominatim policy caps public use
at 1 request/second, prohibits systematic and bulk querying, and states that applications whose
primary function is geocoding must run their own service. Overpass's policy directs heavy users
to planet downloads. Self-hosting is the sanctioned path, not a workaround. **[PRIMARY]**

- **Licence:** ODbL — attribution required; share-alike applies to derived *databases*.
- **Storage:** permanent. Coordinates, place records and our derived metrics may all be stored.
- **Cost:** $0 in fees; one VM and a few hours of import time.
- **Refresh:** re-import the extract monthly.
- **Stopgap while the box is being built:** OpenRouteService free key — 2,500 requests/day,
  40,000/month, covering directions, matrix, isochrones and geocoding. Development only.
  **[SECONDARY]**

### Metrics we compute ourselves from this core
- Commute time to the user's stated work location, by car and by transit
- Walkability: count and diversity of amenities within walking isochrones, plus intersection
  density from the street network
- Distance to nearest grocery, pharmacy, clinic, park, school, transit stop
- Transit access: stops within 800 m weighted by service frequency (from GTFS, §4)

Every metric is our formula over open data, so it can be printed, argued with and reproduced —
which the Location Score needed anyway.

---

## 2. Financial and rate data

### Bank of Canada — Valet API
- Policy rate, prime, posted conventional mortgage series (V80691333/4/5), full history.
- No registration, no key, no cost. **[PRIMARY]**
- Used for default rate assumptions, scenario anchors and dated market snapshots.
- *Posted* rates are not *contract* rates: the user's own quoted rate always wins, and the UI
  says which is in play.

### Mortgage contract rates
No free licensed feed of best-available broker rates exists, and the comparison sites that
publish them prohibit collection. **Resolution:** the user enters their quoted rate; the Valet
posted rate is the labelled, dated fallback default. This is honest and costs nothing.

---

## 3. Property attributes — user-supplied, cross-checked

MPAC is out (no licence fee budget). The MVP source of property facts is the user, who has the
listing in front of them.

| Input path | How | Provenance |
|---|---|---|
| Manual entry | Form | `user_asserted` |
| Paste listing text | Textarea → LLM extraction → strict Pydantic schema → **user confirms** | `user_asserted_extracted` |
| Upload listing PDF | Same pipeline | `user_asserted_extracted` |
| Upload screenshot | Same pipeline, vision extraction | `user_asserted_extracted` |

**We do not fetch listing URLs from sites whose terms prohibit it** (ADR 0002 §2). The user
uploads what they already have; they can copy the page text themselves in two keystrokes, and
the result is identical data with zero exposure.

**Free cross-checks**, where the municipality publishes them: building footprints (implies
footprint area), building permits (implies renovations), property boundaries (implies lot size),
zoning designation. Contradictions between a user value and an open-data value are **surfaced**,
never silently resolved.

---

## 4. Neighbourhood, transit, schools

| Source | What | Licence | Cost |
|---|---|---|---|
| **Statistics Canada** — 2021 Census Profile (SDMX REST), WDS, boundary files | Income and tenure mix, dwelling types, DA/CT geography for neighbourhood context | Open Government Licence – Canada, acknowledgement | $0 **[PRIMARY]** |
| **CMHC HMIP / Rental Market Survey** | Average rent by bedroom count and zone, vacancy, turnover — the rent input to the Investment Score and rent-vs-buy | CMHC data licence, acknowledgement | $0 **[PRIMARY]** |
| **GTFS feeds** (municipal agencies, Metrolinx) | Stop locations and service frequency for the transit metric | per-agency, generally open | $0 **[UNVERIFIED per agency]** |
| **EQAO Open Data** | Assessment results by school and board | published for reuse under Ontario's Digital and Data Directive, 2021 | $0 **[PRIMARY]** |
| **Ontario Data Catalogue** — School Information and Student Demographics | School locations, levels, enrolment, board | Open Government Licence – Ontario | $0 **[PRIMARY]** |

**School catchments remain unavailable.** Boundaries are held by individual boards, not published
provincially. The product says *nearby schools*, never *your school*. Claiming a catchment we
cannot verify is precisely the fabrication the brief prohibits, and no amount of free data fixes
it.

---

## 5. Risk data

| Source | What | Licence | Cost |
|---|---|---|---|
| **Conservation authorities** (36) + Conservation Ontario | Regulated areas, floodplain mapping — ~22,000 km mapped, ~90% riverine | per authority; many publish open GIS | $0 **[PRIMARY/SECONDARY]** |
| **Municipal open data** (Toronto CKAN and equivalents) | Zoning by-law, development applications, permits | Open Government Licence – Toronto: worldwide, royalty-free, use/modify/distribute, attribution | $0 **[PRIMARY]** |
| **OSM (self-hosted Overpass)** | Rail corridors, highways, airports, transmission lines, industrial land | ODbL | $0 |

Coverage is not provincial for flood. Outside a mapped area the answer is `UNKNOWN`, never "no
flood risk" — the sharpest test of the status discipline in the whole product.

---

## 6. Taxes, market context, rules

- **Property tax rates:** ingested from municipal by-law pages and municipal open data, with the
  by-law year recorded. Where a rate is unknown, use the user's figure from the listing
  (`user_asserted`); failing that, `unavailable`. We do not collect from rate-comparison sites.
- **Land transfer taxes and buyer programs:** Ontario LTT, Toronto MLTT including the 2026-04-01
  luxury bands, first-time rebates, NRST/MNRST, FHSA, HBP — captured with brackets and effective
  dates in `RESEARCH_REPORT.md` §3 and loaded into the rule registry. All from government pages.
  $0.
- **Market context:** TRREB and CREA publish average price, MLS HPI benchmark,
  sales-to-new-listings and days on market in public reports and press releases. Ingested by
  hand or from the published PDF/release as a dated, attributed `market_snapshot`. Not a feed,
  not scraped from a portal. **[SECONDARY]**

---

## 7. Sold comparables — supplied by the user

The only genuinely gated dataset. Free, legal route: the person who is already entitled to see
them (ADR 0002 §3).

- Paste the comparable-sales email a realtor sent.
- Type in a sold price the user looked up themselves.
- Each comp is stored with `user_supplied_comparable` provenance, an address, a sale date, a
  price and whatever attributes the user has, and then runs through the normal similarity engine.

**Confidence scales with what the user supplies:** six well-matched comps produce a genuinely
useful fair-value range; zero comps produce the wide market-benchmark range with the reason
stated. The data gap becomes a dial the user can turn, rather than a hole we hide.

---

## 8. What is deliberately not used

| Source | Why not |
|---|---|
| CREA DDF | Display-only under its own Rules; a valuation is not display |
| Board IDX/VOW feeds | Require a licensed brokerage; also a fee |
| MPAC | Negotiated licence fee |
| Teranet / GeoWarehouse / OnLand | Fee and/or board membership; per-search access is not a feed |
| Local Logic, Walk Score | Fee, or free-tier terms that bar paid products |
| Google Maps Platform | Fee, and may not store what we need to store |
| REALTOR.ca, HouseSigma, Wahi, Zolo, Zoocasa, brokerage sites | Terms prohibit collection; *Century 21 v. Rogers*, 2011 BCSC 1196. See ADR 0002 §2 |

---

## 9. Build order

1. **OSM box** — Ontario extract, Nominatim + OSRM + Overpass (unblocks all location work)
2. **Bank of Canada Valet** (unblocks financial defaults)
3. **Rule registry seed** from government pages (unblocks the whole money engine)
4. **Statistics Canada** (neighbourhood context)
5. **Municipal open data for the pilot city** — zoning, development applications (risk flags)
6. **CMHC rental** (Investment Score, rent-vs-buy)
7. **EQAO + Ontario school data**
8. **Conservation authority for the pilot region**
9. **GTFS for the pilot region** (transit metric)
10. **User-supplied comparables** in the UI (the Value Score)
