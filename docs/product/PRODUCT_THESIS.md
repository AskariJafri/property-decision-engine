# Product Thesis

**Status:** Phase 1. Written after the Phase 0 research; read `/docs/research/RESEARCH_REPORT.md`
first, because the licensing findings there constrain everything below.

---

## 1. The one sentence

> Give me a property and my situation. I will do the analysis and explain whether this property
> makes sense **for me**.

The emphasis on *for me* is the whole product. Property valuation is a solved, commoditized,
free service in Canada. Personal suitability is not offered by anyone, because everyone who
could offer it is paid when a transaction closes.

---

## 2. Target customer

**Primary**
- Canadian home buyer, Ontario first.
- First-time buyer — the person who does not know what they do not know: that the insured cap
  bites at $1.5M, that Toronto charges a second land transfer tax, that a 30-year amortization
  is available to them and not to a move-up buyer, that FHSA and HBP stack.
- Move-up buyer — the person with equity, a bigger number, and more to lose from a 7%
  overpayment than a first-timer has from a 3% one.

**Secondary**
- Small investor (1–3 doors), who needs cash flow, cap rate and vacancy modelled honestly.
- Realtor, who wants a client-facing analysis they did not have to assemble by hand.
- Mortgage professional, who wants an affordability conversation started before the application.
- Financial planner, for whom a house purchase is the largest single item in a client plan.

Secondary segments are *deliberately not* MVP targets. Building for a realtor changes the
product into a sales tool, and the independence claim in §6 is the asset.

---

## 3. Jobs To Be Done

1. **"Tell me if I can actually afford this — not the bank's number, mine."**
   Distinguish *can I qualify* from *can I live with this*. The gap between the two is where
   people get hurt.
2. **"Tell me whether this price is defensible."**
   Not a point estimate. A range, with the reasoning and the confidence attached.
3. **"Tell me what this house costs me every month, everything included."**
   Mortgage, tax, insurance, condo fees, utilities, maintenance reserve — the number nobody
   assembles until after closing.
4. **"Tell me what I am not seeing."**
   The development application two streets over. The flood-regulated area. The condo fee that
   is low because the reserve fund is thin.
5. **"Tell me what would change your mind."**
   Rates up 1%. Income down. Fees up 20%. Sell in three years instead of ten.
6. **"Help me decide between the two I am torn about."**
   Comparison on the axes that matter to *this* buyer, not a generic feature grid.
7. **"Give me something I can act on tomorrow."**
   Questions to ask the realtor. An analytical offer range. What to verify before the deadline.

---

## 4. Pain points and existing alternatives

| The buyer's alternative today | Why it is insufficient |
|---|---|
| Portal AVM (HouseSigma, Wahi) | Values the property, knows nothing about the buyer; opaque; no ownership cost, no fit, no risk investigation list |
| Bank affordability calculator | Answers "what will we lend" — the lender's question, not the buyer's; ignores the property entirely |
| Mortgage broker | Excellent on qualification, paid on funding, silent on whether the *house* is a good idea |
| Realtor | Knows the market genuinely well; is paid when you buy; cannot be the check on the purchase |
| Spreadsheet | The most honest option available today, which is a damning statement about the market. Error-prone, no data, no risk layer, abandoned after two evenings |
| Generic AI chatbot | Confident arithmetic, invented property tax, hallucinated comparables, no provenance, no reproducibility |

The consistent failure is **advice with an incentive attached, or arithmetic with nothing
behind it.**

---

## 5. Why AI is useful here, and what it must never do

**Useful for:**
- Extraction — turning a listing PDF, a screenshot or a pasted description into structured,
  validated fields a human then confirms.
- Explanation — converting a deterministic score decomposition into language a nervous
  first-time buyer can act on.
- Question generation — "ask about permits for the basement finish" is a genuinely good use of
  a model that has read a lot of home inspections.
- Summarization and narrative comparison across saved properties.

**Never for:**
- Mortgage arithmetic, tax arithmetic, score arithmetic, or valuation arithmetic.
- Inventing a number that no source supplied.
- Overriding, adjusting or "sanity-checking" a deterministic result.
- Asserting that data exists when the provenance layer says it does not.

The AI sees the fact bundle *after* the engines are done. It has no ability to change a number,
only to explain the numbers it was given, and it is required to say when something is missing.

---

## 6. The moat

**Independence (business moat).** Every incumbent is a lead-generation business for agents or a
bank. We take money from the buyer, so we can tell the buyer to walk away. This is easy to
state and structurally hard for an incumbent to copy — it requires giving up their revenue model.

**Rule corpus (data moat, near term).** A versioned, dated, sourced registry of Ontario and
federal purchase rules: LTT and MLTT brackets including the April 2026 luxury bands, first-time
rebates and their eligibility tests, NRST/MNRST, insured-mortgage cliffs, amortization
eligibility, GDS/TDS, FHSA/HBP interaction. It compounds; every rule change makes the archive
more valuable and every competitor's hardcoded constant more wrong.

**Provenance graph (technical moat).** Every fact carries source, retrieval time, effective
date, confidence and licence class. This is expensive to retrofit and cheap to maintain if built
first — which is why it is in the schema on day one, not in a later hardening phase.

**Comparable dataset (data moat, later).** Licensed sold data via MPAC and eventually a
brokerage/VOW relationship. This is the expensive moat and the one that turns a good tool into
a defensible company. It is deliberately *not* an MVP dependency.

**Network effects:** weak and honestly so. A home purchase is rare and private; there is no
viral loop worth designing for. The nearest thing is an anonymized corpus of user-confirmed
property attributes and outcomes accumulating over time — real, slow, and not a launch strategy.

---

## 7. What this product is not

- Not a listing portal. We do not want to be searched; we want to be consulted.
- Not a mortgage broker. We estimate qualification; a lender decides it.
- Not an appraisal. An appraiser signs their name for lending purposes; we do not.
- Not an AVM company. Our fair-value range is a means to a decision, not the product.
- Not a chatbot with a real estate personality.

---

## 8. How we will know it works

- A user changes their behaviour: does not offer, offers lower, asks the questions we generated,
  or proceeds with the specific concerns we surfaced resolved.
- A user can explain *why* the score is what it is, to their partner, without us in the room.
- Zero incidents of a number appearing in the UI that cannot be traced to a source or a formula.
- The phrase "Data unavailable" appearing regularly, and users reporting it as trustworthy
  rather than broken.
