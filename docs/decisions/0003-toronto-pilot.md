# ADR 0003 — Toronto as the pilot city

- **Date:** 2026-09-04
- **Status:** Accepted (owner decision)
- **Context:** `RESEARCH_REPORT.md` §9 open question 1; the pilot city determines the first
  municipal, flood and transit integrations.

---

## Decision

The City of Toronto is the pilot jurisdiction for V1.

## Why it is a good choice

- **The best open data in Ontario.** A mature CKAN portal under the Open Government Licence –
  Toronto, which grants a worldwide, royalty-free right to use, modify and distribute with
  attribution. Everything the risk and location engines need is published and free.
- **One conservation authority covers it.** TRCA publishes regulated areas and regulatory flood
  lines as ArcGIS Open Data, so the flood flag is a real integration rather than 36 of them.
- **It exercises the hardest rules.** Toronto is the only municipality with a second land
  transfer tax, and the April 2026 luxury bands push MLTT to 8.60%. Building against Toronto
  first means the rule registry is stressed on day one instead of after launch.
- **TTC publishes GTFS**, so the transit metric has a real feed.

## Why it is also the hardest case, and that is fine

Toronto affordability means many analyses will return low Affordability scores and, in some
cases, a withheld Buy Score. That is the product working, and it is better to discover the
"this house does not work for you" path in the pilot than to discover it after expanding.

## Concrete sources this unlocks

| Need | Source | Access |
|---|---|---|
| Zoning designation | Toronto Open Data — **Zoning By-law** (569-2013) | CKAN, OGL-Toronto |
| Development applications nearby | Toronto Open Data — **Development Applications** | CKAN, OGL-Toronto |
| Lot geometry / footprint cross-check | Toronto Open Data — **Property Boundaries** | CKAN, OGL-Toronto |
| Neighbourhood context | Toronto Open Data — **Neighbourhood Profiles** + StatCan census | CKAN + StatCan |
| Transit metric | Toronto Open Data — **TTC Routes and Schedules** (GTFS) | CKAN, OGL-Toronto |
| Flood risk | **TRCA Open Data** — Regulated Area, Floodline (polygon and line) | ArcGIS Open Data / REST |
| Property tax rate | City of Toronto **Property Tax Rates & Fees** (by-law, annual) | toronto.ca |
| Land transfer tax | Ontario LTT + **Toronto MLTT** incl. 2026-04-01 luxury bands | rule registry |

TRCA's floodline polygon carries a `FloodPlainSource` attribute distinguishing mapped flood
plains from *estimated* ones. That distinction maps directly onto our `CONFIRMED` / `POTENTIAL`
status semantics and must be preserved through the pipeline rather than flattened — an estimated
flood plain is `POTENTIAL`, a mapped one inside the line is `CONFIRMED`, and a property outside
TRCA's jurisdiction or coverage is `UNKNOWN`.

## Consequences

- The risk engine's first three flags are Toronto-specific: zoning designation mismatch,
  development application within a radius, flood plain / regulated area intersection.
- Municipal adapters must be written as `MunicipalDataProvider` implementations from the start,
  because municipality number two will have a different portal and a different licence. Toronto
  is the first implementation, not the shape of the interface.
- Outside Toronto, the MLTT rule simply does not resolve for that jurisdiction, and the closing
  cost engine returns Ontario LTT alone. That falls out of the rule registry's `as_of` +
  jurisdiction lookup, with no special-casing.
- Expansion order after Toronto, on open-data quality: Ottawa, Mississauga, Hamilton.
