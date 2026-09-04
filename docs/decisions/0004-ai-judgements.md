# ADR 0004 — AI that improves the decision without touching the arithmetic

- **Date:** 2026-09-04
- **Status:** Accepted (owner directive: "add AI to enhance decisions over the rules based engine,
  use local models for now, later we can ship free APIs")
- **Context:** ADR 0001 §5 put the AI layer strictly downstream of every engine, where it could
  only narrate. The owner wants it to contribute to the decision itself.

---

## The problem with the obvious version

The obvious reading is "let the model adjust the score." That breaks three things at once:

1. **Reproducibility.** A language model is not a function. The same property analysed twice
   would produce two different Buy Scores, and `property_analyses.inputs_hash` — the thing that
   makes an analysis auditable and replayable — would mean nothing.
2. **Explainability.** "The model felt 78 was more appropriate" is not a factor a user can
   argue with, and every factor in this product has to be arguable.
3. **The brief.** Phase 8: *"Do NOT let GPT arbitrarily decide the score."* Phase 17: *"never
   override deterministic calculations."* Phase 43: *"CALCULATIONS MUST BE DETERMINISTIC."*

So the score arithmetic stays deterministic. What changes is **what the arithmetic is allowed to
know**, and that turns out to be where the real gain was anyway.

---

## Decision — AI is a bounded input producer, not an output modifier

The model runs *before* scoring, produces **typed judgements**, and the deterministic engines
consume those judgements the way they consume any other input: through the provenance layer, at
`AI_INFERRED` quality (0.5, the lowest class above unavailable), with a hard cap on how far any
one judgement can move a subscore.

```
listing text, photos, open data
        │
        ▼
   AI judgement  ──▶  ai_judgements row (pinned: model, prompt hash, output, version)
        │
        ▼
   deterministic engines  ──▶  score  ──▶  AI explanation (narration, as before)
```

This is a genuine increase in what the product can reason about. A rule cannot read *"roof
replaced 2009, furnace original, sold as is where is, buyer to verify all measurements"* and
know that it is looking at three separate problems. A model can, and once it has, the finding is
just another input with a source and a confidence.

### The five judgement types

| Type | What the model produces | Where it lands | Cap |
|---|---|---|---|
| `condition_signal` | Renovation recency, deferred-maintenance indicators, age-of-systems mentions, "as-is" framing | Property Quality subscore | ±8 points |
| `listing_red_flags` | Phrases that map to investigation items — no survey, estate sale, tenanted, seller does not warrant | Risk flags, always `POTENTIAL` | ±6 points |
| `omission_signals` | What a listing conspicuously does **not** say (no roof age, no inspection, no fee schedule) | Questions to ask; confidence penalty | 0 |
| `preference_interpretation` | Free-text wants → structured hard/soft requirements and weights | Personal Fit — **after the user confirms** | see below |
| `decision_review` | Internal inconsistencies in the finished analysis ("comfortable affordability, 0.4 months of reserve") | A surfaced flag for the user | 0 |

**Caps are absolute.** Even a completely wrong `condition_signal` moves the Buy Score by at most
a couple of points after weighting. The failure mode of a hallucinating model is a slightly
mis-scored subscore with a visible AI-inferred label, not a wrong recommendation.

**`preference_interpretation` upgrades its own provenance.** The model proposes; the user
confirms in the UI; on confirmation the judgement is rewritten as `USER_ASSERTED`. After that it
is not an AI input at all, which is the correct outcome — the user really did say it, we just
parsed it.

**AI may only ever raise `POTENTIAL`.** `CONFIRMED` requires a data source. `UNKNOWN` is
produced by absence of coverage and never by a model. A model cannot clear a flag, only add one.

---

## How reproducibility survives

Judgements are **pinned, not regenerated**. Every `ai_judgements` row stores the model
identifier, the prompt hash, sampling parameters, the raw structured output and a
`judgement_version`. The analysis references judgement rows by id, and `inputs_hash` covers
them.

So the contract from ADR 0001 §6 holds exactly as written:

> `(analysis_inputs, rule_set_version, scoring_model_version)` determines the score.

— with pinned judgements now part of `analysis_inputs`. Re-running the model produces a *new*
judgement and therefore a *new* analysis row, which the user sees as "your analysis changed, and
here is what changed." That was already the design for a re-run; nothing new is needed.

This matters because temperature 0 is **not** determinism. Model versions shift, quantisations
differ, hardware changes results at the margin. Pinning the output is the only honest way to
have a model in a reproducible pipeline.

---

## Local models now, hosted free tiers later

The runtime speaks the **OpenAI-compatible chat-completions shape**, so moving from local to
hosted is a base-URL and model-name change, not a rewrite.

- **Now: Ollama** at `http://localhost:11434/v1`. Free, private, and the privacy argument is
  real — extraction runs over documents describing someone's finances and home, and those bytes
  never leaving the machine is a genuine product claim, not a cost saving.
- **Later: free hosted tiers** behind the same interface, ordered as a preference ladder with
  failover. Availability comes from distinct provider *keys*, not distinct models on one key,
  since free quotas meter per key.
- **Sampling is pinned:** temperature 0, fixed seed where the backend honours one, model tag
  recorded verbatim (`llama3.1:8b-instruct-q4_K_M`, not `llama3`).

**Degradation is a first-class path.** No model configured, model down, or output failing
validation ⇒ the judgement is `UNAVAILABLE` with a reason, its subscore contribution drops to
zero, weight redistributes, and confidence falls. An analysis without AI is a slightly less
informed analysis, never a failed one. That is exactly how every other provider behaves.

---

## What still guards the output

Unchanged from ADR 0001 §5, and now applied to judgements as well as narration:

1. **Numeric-token guard** — no number in model output that is not in the input bundle.
2. **Strict schema** — judgements are validated into typed objects; a malformed judgement is
   discarded, not repaired.
3. **Evidence required** — every judgement item must quote the span it came from. A
   `condition_signal` with no supporting text is dropped.
4. **`analysis_factors` allowlist** — the explainer may only discuss factors that exist as rows.

---

## Consequences

- `ai_judgements` joins the schema in Phase C, because the channel is a storage decision even
  though the prompts are Phase J.
- `SCORING_MODEL.md` gains the caps table and a rule that AI-derived contributions are always
  rendered with their source class visible.
- The scoring engine needs a "capped adjustment" primitive it did not previously need.
- CI gains a determinism test: the same pinned judgement plus the same inputs must produce the
  same score across runs, with the model stubbed out entirely.
- The product can now say something it could not say yesterday — *"the listing says the furnace
  is original and does not mention the roof"* — while still being unable to say a number nobody
  computed.
