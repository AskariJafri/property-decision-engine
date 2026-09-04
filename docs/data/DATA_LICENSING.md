# Data Licensing

**Status:** Phase 0. Researched 2026-09-03. This document is a **gate**, not a reference: no
external source may be integrated until it has a completed row here, and no field may be stored
whose row says it may not be.

**This is not legal advice.** Terms are summarized from public pages on the date shown. Anything
marked `NEEDS COUNSEL` must be reviewed by a Canadian lawyer before the source reaches
production.

---

## 1. Licence classes used in code

| Class | Meaning | Storage |
|---|---|---|
| `open` | Open licence permitting commercial use, modification and redistribution with attribution | Durable |
| `licensed` | Paid or agreement-based, commercial use permitted within the contract | Durable, per contract |
| `restricted` | Usable but with hard storage/retention/display limits | Limited, TTL enforced |
| `prohibited` | May not be used by this product at all | None |

The `ProviderPolicy` object in `providers/` carries this class, plus `may_store_values`,
`max_retention_days` and `attribution_required`. The provenance repository refuses writes that
contradict it (`/docs/architecture/ARCHITECTURE.md` §5).

---

## 2. Source register

### CREA — DDF (REALTOR.ca listing content)
| Field | Finding |
|---|---|
| Provider | Canadian Real Estate Association |
| Dataset | MLS listing content via the Data Distribution Facility |
| Purpose we would want | Comparable analysis, valuation, property attributes |
| Licence | DDF Policy and Rules, revised January 2024 |
| Commercial use | Member-gated; participation requires CREA membership and brokerage opt-in |
| **Permitted uses** | **Display only** on National Pool / Member Websites; a mobile app whose *sole* purpose is advertising that content; marketing materials for one's own listings (§5(d)) |
| Prohibited | Any other use whatsoever (§5(i)); no more than ten websites (§5(e)); no consumer comments on listings (§5(g)); no display anywhere but a permitted site (§5(h)) |
| Attribution | "Powered by REALTOR.ca" logo linking to the listing, min 90px wide, 1:1; listing brokerage name; CREA watermarks on images; MLS/REALTOR trademark statement on every page (§6) |
| Retention | On termination, must destroy all local copies (§9) |
| Anti-scraping | Participants must actively monitor for and block scraping, and report it (§5(k)–(l)) |
| **Class** | **`prohibited`** for our purposes |
| Verdict | A comparable-based valuation is not display. DDF cannot feed our engines. Do not design around it |

### Real estate boards (TRREB via PropTx) — IDX / VOW / DLA
| Field | Finding |
|---|---|
| Access | Licensed brokerage + board membership + three executed agreements |
| Cost | VOW around $1,500/year plus membership **[SECONDARY]** |
| Use | VOW tier carries sold data; permitted uses are set by the board agreement, not by CREA |
| Class | `licensed` — **only** once agreements exist |
| Status | Post-MVP. `NEEDS COUNSEL` on whether an analysis product is a permitted VOW use |

### Repliers (aggregator)
| Field | Finding |
|---|---|
| What | Normalized MLS API, from ~$199/month |
| Licence | Integration/compliance support only; underlying data rights must come from the board |
| Class | `licensed` (their software) over `licensed` (board data) |
| Verdict | Useful later; changes engineering cost, not legal standing |

### MPAC
| Field | Finding |
|---|---|
| Dataset | Ontario assessment values and property attributes |
| Access | Commercial licensing: bulk extracts, API, market profiles |
| Cost | By negotiation |
| Restrictions | Contract-specific; expect limits on redistribution and on display of assessed values |
| Class | `licensed` |
| Action | Request terms and pricing; this is the first paid data decision |

### Teranet / GeoWarehouse / OnLand
| Field | Finding |
|---|---|
| What | Registry sale prices, title |
| Access | GeoWarehouse through participating board membership; OnLand pay-per-search, no bulk right |
| Cost | Teraview ~$3,804/user/yr; +~$6,340/user/yr with assessment values **[SECONDARY]** |
| Class | `licensed` if contracted; **`prohibited` to bulk-collect via per-search access** |
| Note | Per-search public access is not a data feed. Automating it would breach the terms and is out of scope by policy |

### Google Maps Platform
| Field | Finding |
|---|---|
| Datasets | Geocoding, Places, Routes/Distance Matrix |
| Commercial use | Permitted under the Maps Platform terms, pay-as-you-go |
| **Caching** | Prohibited except as expressly permitted: **coordinates up to 30 consecutive calendar days**, then deletion; **place IDs indefinitely** |
| Prohibited | Exporting, extracting or scraping content for use outside the services |
| Attribution | Required per the terms wherever content is displayed |
| **Class** | **`restricted`** — `may_store_values=False` except place IDs; `max_retention_days=30` for coordinates |
| Consequence | Store place ID + our derived metrics. Never a table of cached Google fields |

### Local Logic
| Field | Finding |
|---|---|
| Datasets | Location scores, demographics, neighbourhood profiles, climate |
| Cost | From ~$500/month **[SECONDARY]** |
| Restrictions | Contract-specific; confirm redistribution and caching rights before design |
| Class | `licensed` (pending contract) |

### Walk Score
| Field | Finding |
|---|---|
| Restriction | Free API is for consumer-facing applications; subscription sites directed to Enterprise **[SECONDARY]** |
| Class | `restricted` pending written clarification; treat as `prohibited` until then |

### Bank of Canada — Valet API
| Field | Finding |
|---|---|
| Access | Free, no key, no registration |
| Terms | Bank of Canada website terms of use; attribution expected |
| Class | `open` (attribution) |

### Statistics Canada
| Field | Finding |
|---|---|
| Datasets | Census Profile (SDMX), Web Data Service, boundary files |
| Licence | Open Government Licence – Canada; reproduction permitted with acknowledgement |
| Class | `open` (attribution: "Adapted from Statistics Canada, 2021 Census") |

### CMHC — HMIP / Rental Market Survey
| Field | Finding |
|---|---|
| Licence | CMHC data licence; source acknowledgement required; "as is" |
| Class | `open` (attribution) |

### EQAO / Ontario Data Catalogue
| Field | Finding |
|---|---|
| Licence | EQAO publishes without copyright restriction under Ontario's Digital and Data Directive, 2021; Ontario datasets generally under the Open Government Licence – Ontario |
| Class | `open` (attribution) |
| Gap | School **attendance boundaries** are not provincially published — see DATA_SOURCES §6 |

### City of Toronto Open Data
| Field | Finding |
|---|---|
| Licence | Open Government Licence – Toronto: worldwide, royalty-free, non-exclusive, use/modify/distribute for any lawful purpose, attribution required |
| Class | `open` (attribution: "Contains information licensed under the Open Government Licence – Toronto") |
| Note | Every other municipality needs its own row; do not assume Toronto's licence generalizes |

### Conservation authorities
| Field | Finding |
|---|---|
| Licence | Per authority; many publish open GIS, some restrict redistribution |
| Class | Per source; default `restricted` until the specific authority's terms are read |
| Rule | Absence of mapping is `UNKNOWN`, never "no risk" |

### OpenStreetMap / Overpass
| Field | Finding |
|---|---|
| Licence | ODbL — attribution, and share-alike on derived *databases* |
| Class | `open` with obligations |
| Note | `NEEDS COUNSEL` on whether our derived amenity metrics constitute a derived database |

### Listing portals (REALTOR.ca, HouseSigma, Wahi, Zolo, brokerage sites)
| Field | Finding |
|---|---|
| Terms | Prohibit commercial use, screen scraping and database scraping |
| **Class** | **`prohibited`** |
| Policy | We do not scrape them. Ever. Not for "enrichment", not for a demo, not for evaluation. A user may upload a document they already have; we do not fetch on their behalf from a source that forbids it |

---

## 3. Standing policy

1. **No source without a row.** A new integration starts with a row here, not with code.
2. **No storage the row forbids.** Enforced by `ProviderPolicy` and the provenance repository.
3. **Attribution ships with the data.** Attribution strings live in `data_sources` and render
   wherever the derived value renders.
4. **Retention is scheduled, not remembered.** `expires_at` on retention-limited facts; a sweeper
   deletes them; deletion is tested.
5. **Scraping is not an engineering decision.** It is prohibited by policy. If a data need can
   only be met by scraping, the answer to the user is "Data unavailable".
6. **Re-review annually,** and whenever a provider announces terms changes.

---

## 4. Open licensing questions

| # | Question | Blocks |
|---|---|---|
| 1 | MPAC commercial terms and pricing for a consumer analysis product | Property attributes at scale |
| 2 | Would a board permit a VOW-derived comparable analysis in a non-brokerage consumer product? | The comparable engine, the moat |
| 3 | Walk Score written position on paid consumer products | Location Score composition |
| 4 | Local Logic caching and redistribution terms | Whether scores can be stored per analysis |
| 5 | Does ODbL share-alike reach our derived metrics? | Using OSM as the amenity fallback |
| 6 | Which geocoder permits durable coordinate storage at acceptable cost? | Schema design for `locations` |
