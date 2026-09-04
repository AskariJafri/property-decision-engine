# AI Property Decision Engine

> Give me a property and my situation. I will do the analysis and explain whether this property
> makes sense **for me**.

A property decision engine for Ontario home buyers. It combines a household's finances and
requirements with a property's details, computes the money deterministically, scores the match,
surfaces the risks worth investigating, and explains the result — labelling every number as
verified, calculated, estimated, assumed, AI-inferred, or unavailable.

**Status: Phase 0 (research and architecture). No application code exists yet.**

---

## What is here

| Document | What it holds |
|---|---|
| [`docs/research/RESEARCH_REPORT.md`](docs/research/RESEARCH_REPORT.md) | The Ontario data ecosystem, mortgage and tax rules with effective dates, competitors, and the risk register |
| [`docs/product/PRODUCT_THESIS.md`](docs/product/PRODUCT_THESIS.md) | Customer, jobs to be done, why existing tools fail, the moat |
| [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) | System shape, engines, provider abstractions, data model proposal |
| [`docs/data/DATA_SOURCES.md`](docs/data/DATA_SOURCES.md) | Every candidate source, what it gives us, and in what order to integrate |
| [`docs/data/DATA_LICENSING.md`](docs/data/DATA_LICENSING.md) | The licence gate — no source is integrated without a row here |
| [`docs/scoring/SCORING_MODEL.md`](docs/scoring/SCORING_MODEL.md) | Buy Score v0.1: components, weights, missing data, confidence, calibration plan |
| [`docs/compliance/COMPLIANCE.md`](docs/compliance/COMPLIANCE.md) | FSRA, TRESA, AI regulation, PIPEDA, and the pre-launch checklist |
| [`docs/decisions/0001-initial-architecture.md`](docs/decisions/0001-initial-architecture.md) | The eight decisions that shape everything after |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phases A–L, the first four weeks, and V1–V10 |

## Principles

1. Trust over hype · 2. Transparency over magic · 3. Data over LLM guessing ·
4. Explainability over black boxes · 5. Ranges over false precision ·
6. Sourced fact over unsourced claim · 7. User-specific over generic ·
8. Deterministic calculation · 9. Missing data stays visible · 10. Every score is explainable.

The AI layer never performs financial arithmetic, never invents a number, and never overrides a
deterministic result. It explains what the engines computed.

## Two facts that shape the whole build

1. **Ontario sold prices are not public.** CREA's DDF is display-only under its own rules; board
   feeds require a licensed brokerage. The MVP therefore ships without MLS data and says so,
   rather than pretending to a comparable analysis it cannot lawfully perform.
2. **Some data may not be stored.** Google Maps content may not be cached beyond place IDs and
   30-day coordinates, so licence terms are enforced by a code path, not by a policy document.

## Not

Not a listing portal, not a mortgage broker, not an appraisal, not an AVM company, not a chatbot.

---

This analysis is for informational purposes and is not financial, mortgage, legal, tax,
insurance, or home-inspection advice.
