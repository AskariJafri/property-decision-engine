# ADR 0002 — Zero-cost data strategy, and the collection policy

- **Date:** 2026-09-04
- **Status:** Accepted (owner directive: "I want everything free")
- **Supersedes:** the paid-provider assumptions in ADR 0001 and the first cut of
  `DATA_SOURCES.md`
- **Context:** the owner has directed that the product carry no data licence fees.

---

## Decision 1 — The stack costs $0 in licence fees, and self-hosts the OSM toolchain

Every paid provider in the original plan has a free replacement, and in two cases the free
option is *better* for us because its licence permits storage that the paid one forbids.

| Was | Now | Why the swap works |
|---|---|---|
| Google Geocoding (~$5/1k, **may not store results**) | **Self-hosted Nominatim** on a Geofabrik Ontario extract | ODbL: we may store coordinates permanently. This deletes the 30-day retention machinery from ADR 0001 §3 |
| Google Distance Matrix (commute times) | **Self-hosted OSRM or Valhalla** on the same extract | Unlimited matrices, no per-call cost, deterministic and reproducible |
| Google Places (amenities) | **Self-hosted Overpass** on the same extract | Full POI query language; we compute our own amenity metrics |
| Walk Score (free tier bars paid products) | **Our own walkability metric** from OSM POIs + street network | We control and can explain the formula, which the Location Score needed anyway |
| Local Logic (~$500/mo) | **Our own location metrics** + StatCan census | Slower to build, fully explainable, no vendor dependency |
| MPAC attributes (negotiated $) | **User-entered attributes**, cross-checked against municipal open data where it exists | Degrades quality, not legality. See Decision 3 |

**The public OSM services are not the plan.** Nominatim's usage policy caps the public instance
at 1 request/second, forbids systematic and bulk querying outright, and states that applications
whose primary function is geocoding "must run their own service." Overpass's policy sends large
or frequent users to planet downloads. So we do exactly what those policies tell us to do:
download the published Ontario extract and run our own instances. That is the sanctioned path,
it is free, it removes every rate limit, and it makes the whole location layer reproducible
offline.

**"Free" means no licence fees, not no cost.** The OSM toolchain needs a VM — a Nominatim import
of an Ontario extract plus Overpass and OSRM is a modest-server job, not a laptop job, and the
import takes hours. Budget one box.

**Free fallbacks before self-hosting is up:** OpenRouteService's free key (2,500 requests/day,
40,000/month, covering directions, matrix, isochrones and geocoding) is enough for development
and early users, and is a legitimate stopgap. It is not the production answer.

---

## Decision 2 — Automated collection is permitted from open-licensed sources, and prohibited from MLS-derived sites

This is the line, stated precisely so nobody has to re-litigate it in a code review.

### Permitted, and we will build it

- **Bulk downloads of published open data**: Geofabrik OSM extracts, StatCan boundary files and
  Census Profile (SDMX), CMHC HMIP tables, EQAO datasets, Ontario Data Catalogue.
- **Programmatic access to government open-data APIs**: Toronto CKAN, municipal ArcGIS REST
  endpoints, conservation authority GIS services, GTFS feeds. Under the Open Government Licence
  – Toronto and its provincial/federal equivalents, we may "use, modify, and distribute the
  datasets… for any lawful purpose" with attribution. Automated retrieval of data published for
  reuse is the intended use of these endpoints.
- **Fetching a public government page that has no terms prohibiting it** — e.g. a municipal
  by-law page carrying this year's tax rate — with `robots.txt` honoured, a real User-Agent, one
  request at a time, and results cached so we fetch once rather than per user.

These are, informally, "scraping". They carry no meaningful legal risk because the publisher has
licensed reuse, and they are free. The crawler infrastructure gets built.

### Prohibited, and I will not build it

Automated collection from **REALTOR.ca, HouseSigma, Wahi, Zolo, Zoocasa, Redfin.ca, brokerage
websites, or any other MLS-derived source.**

The reason is a Canadian judgment on precisely this conduct. In *Century 21 Canada Limited
Partnership v. Rogers Communications Inc.*, 2011 BCSC 1196, Zoocasa indexed listings and
photographs from Century 21's site. The BC Supreme Court:

- held the **browse-wrap terms of use enforceable** — the first Canadian decision to do so
  squarely — so merely accessing the site formed a contract that the scraping breached;
- found **copyright infringement** in the copied photographs and descriptions;
- **rejected the fair dealing defence**;
- granted an **injunction** barring further access contrary to the terms, plus damages.

The damages were small. The injunction is what matters: a court order shutting off the data this
product would be built on. Layer on CREA's own DDF Rules, which oblige every participant to
monitor for scraping and report it (§5(k)–(l)) — the ecosystem is instrumented to catch this —
and the exposure is not "a little dangerous", it is the single risk that can end the company
after the work is done rather than before.

There is also a product argument, which is the one I'd weigh even if the legal one vanished.
This product's entire differentiation (`PRODUCT_THESIS.md` §6) is that it is the trustworthy,
provenance-labelled, independent party in a market of conflicted ones. A provenance record whose
`source` field reads "scraped from a site that forbade it" is not a provenance record. It is the
thing the product exists to be an alternative to.

---

## Decision 3 — Sold comparables come from the user, for free

The one genuinely gated dataset is recent sold prices. The free, legal, zero-infrastructure
route is the human who is already entitled to see them:

- The user's own realtor sends them comparable sales by email. Let them **paste that.**
- The user can look at a free consumer portal themselves and type in what a nearby comparable
  sold for. A person reading a website is not a robot harvesting it, and no term of use is
  breached by a human looking at a page and remembering a number.
- Every user-supplied comparable is stored with provenance `user_supplied_comparable`,
  confidence capped, source noted, and is fully usable by the similarity and valuation engines.

**Consequence for the product.** The comparable engine (`SCORING_MODEL.md` §5) ships in the MVP
after all — it just runs on 3–8 user-entered comps instead of 500 licensed ones. Confidence
scales with how many the user supplies and how well they match, which turns the data gap into an
honest, visible dial the user can improve by doing five minutes of work. A user who pastes six
good comps gets a genuinely useful fair-value range. A user who pastes none gets the wide
market-benchmark range and is told why it is wide.

This is better than the original plan, not worse: it is free, it is legal, it makes the user a
participant in the analysis, and it degrades gracefully.

---

## Decision 4 — MPAC attributes are replaced by user entry plus open cross-checks

Without an MPAC licence we lose authoritative square footage, year built and assessed value.
Replacement: the user enters what the listing says (they have the listing), and we cross-check
against whatever the municipality publishes openly — building footprints, permit records,
property boundaries where available. Where a cross-check contradicts the user, we surface the
contradiction rather than picking a winner.

**What we give up, stated plainly:** the Property Quality subscore leans harder on user-asserted
data, so its confidence factor is lower (0.65 per `SCORING_MODEL.md` §8), and analysis-level
confidence falls accordingly. That is the correct behaviour — the product is designed to show
exactly this.

---

## Net effect

| | Original plan | Free plan |
|---|---|---|
| Licence fees | MPAC (negotiated) + Local Logic ~$500/mo + Maps usage | **$0** |
| Infrastructure | app server + Postgres | app server + Postgres + **one OSM box** |
| Geocoding storage | forbidden beyond 30 days | **permitted permanently** (ODbL) |
| Location score | vendor scores | our own, fully explainable |
| Comparables | none in MVP | **user-supplied, in MVP** |
| Property attributes | MPAC-verified | user-asserted + open cross-checks |
| Legal exposure | low | low |

The free stack is not a compromised version of the product. The only real loss is
authoritative property attributes, and the only real addition is a server to run.
