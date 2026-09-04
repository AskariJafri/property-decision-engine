# Compliance Notes

**Status:** Phase 0 findings, researched 2026-09-03. **Not legal advice.** Every item marked
`NEEDS COUNSEL` requires a Canadian lawyer, and the mortgage items require someone familiar with
FSRA practice, before launch.

---

## 1. Mortgage brokering — Ontario MBLAA 2006 (FSRA)

**Finding.** No person may deal or trade in mortgages for remuneration without a licence.
"Dealing" is defined broadly and includes soliciting, assessing, underwriting and *providing
information on borrowing or lending through mortgages*. O. Reg. 407/07 sets out exemptions, and
a *simple referral* exemption exists subject to prescribed disclosure, limited information
sharing, and the borrower's written consent. **[SECONDARY]**

**How the product stays on the right side of the line:**
- We produce a **qualification estimate** computed from published rules, labelled as an estimate,
  with "only a lender or licensed broker can confirm this" attached to the value itself in the
  response object — not merely printed in a footer.
- We do not solicit on behalf of any lender, do not recommend a lender or product, do not
  transmit an application, and take no remuneration from a lender.
- We do not tell a user they qualify. We tell them what the published rules produce given the
  numbers they entered.
- **If a referral relationship is ever introduced**, the simple-referral exemption's conditions
  (disclosure, limited information, written consent) become mandatory and the independence claim
  in `PRODUCT_THESIS.md` §6 must be re-examined. `NEEDS COUNSEL`.

## 2. Real estate trading — TRESA

We do not list, trade, or represent parties to a transaction. The grey area is the **suggested
offer range**: it must read as analysis of comparables and market conditions, never as advice on
what to offer. Language review required. **[UNVERIFIED]** in its details. `NEEDS COUNSEL`.

## 3. AI regulation

There is **no AI act in force in Canada.** AIDA died with Bill C-27 at prorogation on
**2025-01-06**; as of mid-2026 no successor has been introduced. What applies:

- **PIPEDA**, with the OPC reading its fairness principles to require transparency about
  automated decision-making and recourse where decisions carry significant consequences.
- **Quebec Law 25** automated-decision rules — not applicable to an Ontario-only launch;
  relevant the moment we accept a Quebec user.
- **ISED's voluntary code** for generative AI.
- **OSFI E-23** model risk — binding on federally regulated institutions, not on us, but a
  sensible template for how we version and validate models.

**Product consequence:** transparency, reproducibility, and a human path to challenge a result
are the compliance regime. Building to the strictest plausible future rule now is cheaper than
retrofitting after one is enacted.

## 4. Privacy — PIPEDA

- **Minimize.** Collect income, debts, savings and credit *band* only because the analysis needs
  them; ask for nothing that no engine consumes.
- **Encrypt** sensitive financial columns at rest.
- **Never log** income, debts, balances, or account identifiers — enforced by a redaction filter
  in the logging configuration, not by developer discipline.
- **Delete on request**, including derived analyses, with the deletion path tested.
- **Consent** is purpose-specific; using stored financial data to train anything requires
  separate, explicit consent.
- **Audit** reads and writes of financial profiles in `audit_logs`.

## 5. Consumer-facing claims

The product must not claim, in copy or in UI, to be:
- an appraisal, a mortgage approval, insurance advice, a home inspection, or tax advice;
- "accurate" in valuation terms until §9 of `SCORING_MODEL.md` has produced validation data.

Standing disclaimer, shown adjacent to the Buy Score and not buried in a footer:

> This analysis is for informational purposes and is not financial, mortgage, legal, tax,
> insurance, or home-inspection advice.

**But disclaimers are not the control.** The controls are: ranges instead of point values,
confidence shown with every headline number, "Data unavailable" as a real state, deterministic
arithmetic, and an AI layer that cannot introduce a number.

## 6. Data licensing

Covered in `/docs/data/DATA_LICENSING.md`, which is a gate on integration. Summary of the two
hard rules: **no scraping of any source whose terms prohibit it, ever**; and **no storage a
provider's licence forbids**, enforced by `ProviderPolicy` in code.

## 7. Pre-launch checklist

- [ ] FSRA-aware review of every mortgage-adjacent string and of the qualification estimator
- [ ] TRESA review of the offer-range language
- [ ] Privacy policy, consent flow, deletion path implemented and tested
- [ ] Licence row present for every integrated source; attribution rendering verified
- [ ] Retention sweeper deleting Google-derived coordinates at 30 days, with a test
- [ ] Log-redaction test proving financial values cannot reach logs
- [ ] Disclaimer placement reviewed on every surface that shows a score or a dollar figure
