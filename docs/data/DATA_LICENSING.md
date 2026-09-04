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

### OpenStreetMap, self-hosted (Nominatim + OSRM/Valhalla + Overpass) — **the location stack**
| Field | Finding |
|---|---|
| Datasets | Geofabrik Ontario extract: addresses, street network, POIs |
| Cost | $0 in fees; one VM |
| Commercial use | Permitted |
| Licence | **ODbL** — attribution required; share-alike attaches to derived *databases*, not to a "produced work" such as a rendered analysis page |
| **Storage** | **Permanent.** Coordinates, POIs and our derived metrics may all be stored — the decisive advantage over Google |
| Public-instance limits | Not applicable once self-hosted. The OSMF Nominatim policy explicitly directs geocoding-dependent applications to run their own service, and Overpass directs heavy users to planet downloads — self-hosting *is* the sanctioned path **[PRIMARY]** |
| Attribution | "© OpenStreetMap contributors" wherever derived values are displayed |
| Class | `open` with obligations |
| Open question | Whether our stored derived metrics (walk scores, amenity counts) constitute a derived database triggering share-alike. `NEEDS COUNSEL`. Mitigation if it does: publish the derived metric table, which costs us nothing we care about |

### OpenRouteService (development stopgap only)
| Field | Finding |
|---|---|
| Free tier | 2,500 requests/day, 40,000/month, 40 concurrent, covering directions, matrix, isochrones, geocoding **[SECONDARY]** |
| Class | `open` within quota |
| Note | Development and early users only; the self-hosted stack is the production answer |

### Google Maps Platform — **not used**
| Field | Finding |
|---|---|
| Why not | Costs money, and its caching rules forbid the durable coordinate storage the schema wants |
| Terms (for the record) | Coordinates cacheable **30 consecutive days** then deletion; **place IDs indefinitely**; no export or scraping of content for use outside the services |
| Class | `restricted` — retained here so that a future decision to adopt it inherits the constraint rather than rediscovering it |

### Local Logic / Walk Score — **not used**
| Field | Finding |
|---|---|
| Local Logic | From ~$500/month **[SECONDARY]**. Replaced by our own metrics over self-hosted OSM |
| Walk Score | Free API restricted to consumer-facing applications; paid products directed to Enterprise **[SECONDARY]**. Replaced by our own walkability metric |
| Class | `prohibited` by policy — not for legal reasons, because they cost money |

### GTFS feeds (municipal transit agencies, Metrolinx)
| Field | Finding |
|---|---|
| What | Stop locations, routes, service frequency |
| Licence | Per agency; most publish openly for reuse **[UNVERIFIED per agency]** |
| Class | `open` per agency, confirmed one at a time |

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

### MPAC — **not used in the free stack**
| Field | Finding |
|---|---|
| Why not | Negotiated licence fee. Replaced by user-entered attributes plus open-data cross-checks (ADR 0002 §4) |
| Class | `licensed` if ever adopted |

### Listing portals (REALTOR.ca, HouseSigma, Wahi, Zolo, Zoocasa, Redfin.ca, brokerage sites)
| Field | Finding |
|---|---|
| Terms | Prohibit commercial use, screen scraping and database scraping |
| **Class** | **`prohibited`** |
| Precedent | *Century 21 Canada LP v. Rogers Communications Inc.*, 2011 BCSC 1196: browse-wrap terms held enforceable, copyright infringement found in copied listings and photographs, fair dealing rejected, injunction and damages granted **[PRIMARY — CanLII]** |
| Enforcement environment | CREA's DDF Rules oblige every participant to monitor for scraping and report it (§5(k)–(l)) |
| Policy | We do not collect from them. Not for enrichment, not for a demo, not for evaluation. A user may upload or paste a document they already have, and a user may read a page and type in a number — neither is us fetching from a source that forbids it |

### User-supplied content (listing text, PDFs, screenshots, comparable sales)
| Field | Finding |
|---|---|
| What | Everything the user chooses to give us about a property, including sold comparables their realtor sent them |
| Licence | The user supplies it for the purpose of their own analysis |
| Class | `open` to us for that user's analysis; **not** redistributable, not poolable across users without separate consent |
| Provenance | `user_asserted`, `user_asserted_extracted`, or `user_supplied_comparable`; confidence capped per `SCORING_MODEL.md` §8 |
| Note | Aggregating user-supplied MLS-derived figures into a shared corpus would recreate the licensing problem by another route. Per-user scope is a **hard** boundary, enforced in the repository layer |

---

## 3. Standing policy

1. **No source without a row.** A new integration starts with a row here, not with code.
2. **No storage the row forbids.** Enforced by `ProviderPolicy` and the provenance repository.
3. **Attribution ships with the data.** Attribution strings live in `data_sources` and render
   wherever the derived value renders.
4. **Retention is scheduled, not remembered.** `expires_at` on retention-limited facts; a sweeper
   deletes them; deletion is tested.
5. **Automated collection follows the licence, not the technical possibility.** Permitted:
   bulk downloads and API access to open-licensed government and OSM data, plus polite,
   `robots.txt`-respecting fetches of public government pages with no prohibiting terms —
   cached once, not per user. Prohibited: any automated collection from MLS-derived sites
   (ADR 0002 §2). If a data need can only be met by the prohibited kind, the answer to the user
   is "Data unavailable" or "tell us what you know".
6. **User-supplied data stays with that user.** Never pooled into a shared corpus without
   separate, explicit consent — pooling MLS-derived figures across users would recreate the
   licensing problem by another route.
7. **Re-review annually,** and whenever a provider announces terms changes.

---

## 4. Open licensing questions

| # | Question | Blocks | Status |
|---|---|---|---|
| 1 | Does ODbL share-alike reach our stored derived metrics (walk score, amenity counts)? | Nothing — mitigation is to publish the derived table | `NEEDS COUNSEL`, low urgency |
| 2 | Per-agency GTFS licences for the pilot region | The transit metric | Confirm one at a time |
| 3 | Conservation authority terms for the pilot region's flood layers | The flood risk flag | Confirm before integration |
| 4 | Municipal open-data licences outside Toronto | Risk flags beyond the pilot city | Per municipality |

Deferred, and only relevant if the owner later reverses the zero-cost decision: MPAC commercial
terms; whether a board would permit VOW-derived comparable analysis in a non-brokerage product;
Walk Score's written position on paid products; Local Logic caching rights.
