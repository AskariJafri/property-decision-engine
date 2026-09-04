"""The seeded rule registry: every rate, bracket and threshold, dated and sourced.

Sourced from ``docs/research/RESEARCH_REPORT.md`` §3, carrying that document's
verification labels into :class:`~app.engines.rules.Verification`. Two consequences
are load-bearing:

**Nothing UNVERIFIED is active.** The 30-year amortization premium surcharge and
Ontario's RST on the insurance premium are both reported at 0.20% and 8%
respectively, and neither could be confirmed against its issuing authority. They
are seeded inactive, which means the engine cannot charge them — and says so, in
an assumption the user sees, rather than quietly guessing.

**Money is integer cents throughout**, including bracket thresholds, so a bracket
boundary lands exactly on $55,000.00 and not on 54999.999999999996.

Brackets are ``(threshold_cents, rate)`` pairs, marginal and ascending: each rate
applies to the portion of consideration above its threshold and below the next.
"""

from __future__ import annotations

from datetime import date

from app.engines.rules import Rule, RuleSet, Verification

ONTARIO_LTT = "https://www.ontario.ca/document/land-transfer-tax/calculating-land-transfer-tax"
TORONTO_MLTT = (
    "https://www.toronto.ca/services-payments/property-taxes-utilities/"
    "municipal-land-transfer-tax-mltt/municipal-land-transfer-tax-mltt-rates-and-fees/"
)
TORONTO_REBATE = (
    "https://www.toronto.ca/services-payments/property-taxes-utilities/"
    "municipal-land-transfer-tax-mltt/municipal-land-transfer-tax-mltt-rebate-opportunities/"
)
CMHC_PREMIUM = (
    "https://www.cmhc-schl.gc.ca/consumers/home-buying/"
    "mortgage-loan-insurance-for-consumers/cmhc-mortgage-loan-insurance-cost"
)
OSFI_MQR = (
    "https://www.osfi-bsif.gc.ca/en/supervision/financial-institutions/banks/"
    "minimum-qualifying-rate-uninsured-mortgages"
)
CRA_HBP = (
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/"
    "rrsps-related-plans/what-home-buyers-plan.html"
)

# --- Land transfer tax -------------------------------------------------------------

#: Ontario, for one or two single family residences. The 2.5% band above $2M applies
#: only to that class; everything else tops out at 2.0%.
_ON_LTT_SFR = [
    [0, "0.005"],
    [5_500_000, "0.01"],
    [25_000_000, "0.015"],
    [40_000_000, "0.02"],
    [200_000_000, "0.025"],
]
_ON_LTT_OTHER = _ON_LTT_SFR[:4]

#: Toronto, effective 2026-04-01. The luxury bands above $3M are the reason this
#: registry exists: a system that hardcoded these in 2025 is now wrong by six
#: figures on a $5M sale and nobody notices until closing.
_TO_MLTT_SFR_2026 = [
    [0, "0.005"],
    [5_500_000, "0.01"],
    [25_000_000, "0.015"],
    [40_000_000, "0.02"],
    [200_000_000, "0.025"],
    [300_000_000, "0.044"],
    [400_000_000, "0.0545"],
    [500_000_000, "0.065"],
    [1_000_000_000, "0.0755"],
    [2_000_000_000, "0.086"],
]
_TO_MLTT_SFR_PRIOR = _TO_MLTT_SFR_2026[:5]
_TO_MLTT_OTHER = _TO_MLTT_SFR_2026[:4]


def default_rules() -> tuple[Rule, ...]:
    """Every rule the financial engine resolves, with its source and effective date."""
    return (
        # --- Ontario land transfer tax ---------------------------------------------
        Rule(
            jurisdiction="ON",
            name="ltt.brackets.sfr",
            value={"brackets": _ON_LTT_SFR},
            effective_from=date(2017, 1, 1),
            source_url=ONTARIO_LTT,
            verification=Verification.PRIMARY,
            note="Agreements after 2016-11-14. 2.5% band applies to one or two "
            "single family residences only.",
        ),
        Rule(
            jurisdiction="ON",
            name="ltt.brackets.other",
            value={"brackets": _ON_LTT_OTHER},
            effective_from=date(2017, 1, 1),
            source_url=ONTARIO_LTT,
            verification=Verification.PRIMARY,
        ),
        Rule(
            jurisdiction="ON",
            name="ltt.first_time_buyer_refund_max_cents",
            value={"amount_cents": 400_000},
            effective_from=date(2017, 1, 1),
            source_url=ONTARIO_LTT,
            verification=Verification.SECONDARY,
            note="Full relief to roughly $368,000 of consideration.",
        ),
        # --- Toronto municipal land transfer tax -----------------------------------
        Rule(
            jurisdiction="ON/Toronto",
            name="mltt.brackets.sfr",
            value={"brackets": _TO_MLTT_SFR_PRIOR},
            effective_from=date(2017, 3, 1),
            effective_to=date(2026, 3, 31),
            source_url=TORONTO_MLTT,
            verification=Verification.SECONDARY,
            note="Superseded by the graduated luxury bands on 2026-04-01. Retained so "
            "an analysis dated before that reproduces exactly.",
        ),
        Rule(
            jurisdiction="ON/Toronto",
            name="mltt.brackets.sfr",
            value={"brackets": _TO_MLTT_SFR_2026},
            effective_from=date(2026, 4, 1),
            source_url=TORONTO_MLTT,
            verification=Verification.PRIMARY,
            version=2,
            note="City Council 2025-12-17; in force 2026-04-01.",
        ),
        Rule(
            jurisdiction="ON/Toronto",
            name="mltt.brackets.other",
            value={"brackets": _TO_MLTT_OTHER},
            effective_from=date(2017, 3, 1),
            source_url=TORONTO_MLTT,
            verification=Verification.PRIMARY,
        ),
        Rule(
            jurisdiction="ON/Toronto",
            name="mltt.first_time_buyer_rebate_max_cents",
            value={"amount_cents": 447_500},
            effective_from=date(2017, 3, 1),
            source_url=TORONTO_REBATE,
            verification=Verification.PRIMARY,
            note="Never owned a home anywhere in the world; principal residence "
            "within 9 months; citizen or PR (or within 18 months).",
        ),
        Rule(
            jurisdiction="ON/Toronto",
            name="mltt.administration_fee_cents",
            value={"amount_cents": 10_256, "hst_rate": "0.13"},
            effective_from=date(2024, 1, 1),
            source_url=TORONTO_MLTT,
            verification=Verification.PRIMARY,
        ),
        # --- Non-resident speculation tax ------------------------------------------
        Rule(
            jurisdiction="ON",
            name="nrst.rate",
            value={"rate": "0.25"},
            effective_from=date(2022, 10, 25),
            source_url="https://www.ontario.ca/document/non-resident-speculation-tax",
            verification=Verification.SECONDARY,
            note="Province-wide, residential with one to six single family residences.",
        ),
        Rule(
            jurisdiction="ON/Toronto",
            name="mnrst.rate",
            value={"rate": "0.10"},
            effective_from=date(2025, 1, 1),
            source_url=TORONTO_MLTT,
            verification=Verification.SECONDARY,
            note="Stacks with the provincial NRST for a combined 35%.",
        ),
        # --- Mortgage default insurance --------------------------------------------
        Rule(
            jurisdiction="CA",
            name="insured.premium_bands",
            value={
                "bands": [
                    ["0.65", "0.006"],
                    ["0.75", "0.017"],
                    ["0.80", "0.024"],
                    ["0.85", "0.028"],
                    ["0.90", "0.031"],
                    ["0.95", "0.040"],
                ]
            },
            effective_from=date(2024, 1, 1),
            source_url=CMHC_PREMIUM,
            verification=Verification.PRIMARY,
            note="Premium on the loan amount, by loan-to-value. Financed into the "
            "principal and amortized.",
        ),
        Rule(
            jurisdiction="CA",
            name="insured.max_price_cents",
            value={"amount_cents": 150_000_000},
            effective_from=date(2024, 12, 15),
            source_url=CMHC_PREMIUM,
            verification=Verification.SECONDARY,
        ),
        Rule(
            jurisdiction="CA",
            name="insured.down_payment_tiers",
            value={"tiers": [[0, "0.05"], [50_000_000, "0.10"]], "uninsurable_min": "0.20"},
            effective_from=date(2024, 12, 15),
            source_url=CMHC_PREMIUM,
            verification=Verification.SECONDARY,
            note="5% to $500k, 10% on the portion from $500k to $1.5M, 20% above.",
        ),
        Rule(
            jurisdiction="CA",
            name="insured.max_amortization_years",
            value={"standard": 25, "first_time_or_new_build": 30},
            effective_from=date(2024, 12, 15),
            source_url=CMHC_PREMIUM,
            verification=Verification.SECONDARY,
        ),
        Rule(
            jurisdiction="CA",
            name="insured.amortization_surcharge",
            value={"rate": "0.002"},
            effective_from=date(2024, 12, 15),
            source_url=CMHC_PREMIUM,
            verification=Verification.UNVERIFIED,
            active=False,
            note="Reported at +0.20% for a 30-year insured amortization but absent "
            "from CMHC's published premium page. Inactive until confirmed: the engine "
            "declares the omission rather than guessing the number.",
        ),
        Rule(
            jurisdiction="ON",
            name="insured.premium_sales_tax_rate",
            value={"rate": "0.08"},
            effective_from=date(2024, 1, 1),
            source_url="https://www.ontario.ca/page/retail-sales-tax",
            verification=Verification.UNVERIFIED,
            active=False,
            note="Ontario RST on the insurance premium, payable at closing rather "
            "than financed. Reported at 8%; not confirmed against the Ministry of "
            "Finance. Inactive.",
        ),
        # --- Qualification ----------------------------------------------------------
        Rule(
            jurisdiction="CA",
            name="mqr.floor",
            value={"rate": "0.0525", "buffer": "0.02"},
            effective_from=date(2021, 6, 1),
            source_url=OSFI_MQR,
            verification=Verification.PRIMARY,
            note="Qualify at the greater of 5.25% and the contract rate plus 2%.",
        ),
        Rule(
            jurisdiction="CA",
            name="qualification.debt_service_limits",
            value={"gds": "0.39", "tds": "0.44"},
            effective_from=date(2021, 1, 1),
            source_url="https://www.cmhc-schl.gc.ca/",
            verification=Verification.SECONDARY,
        ),
        Rule(
            jurisdiction="CA",
            name="qualification.heat_floor_cents",
            value={"house": 15_000, "condo": 10_000, "condo_fee_inclusion": "0.5"},
            effective_from=date(2021, 1, 1),
            source_url="https://www.cmhc-schl.gc.ca/",
            verification=Verification.SECONDARY,
            note="Monthly heating floors used in GDS, and the half of a condo fee "
            "that counts toward it.",
        ),
        # --- Buyer programs ---------------------------------------------------------
        Rule(
            jurisdiction="CA",
            name="programs.fhsa",
            value={"annual_cents": 800_000, "lifetime_cents": 4_000_000},
            effective_from=date(2023, 4, 1),
            source_url="https://www.canada.ca/en/revenue-agency/services/tax/individuals/"
            "topics/first-home-savings-account.html",
            verification=Verification.SECONDARY,
        ),
        Rule(
            jurisdiction="CA",
            name="programs.hbp_max_cents",
            value={"amount_cents": 6_000_000},
            effective_from=date(2024, 4, 16),
            source_url=CRA_HBP,
            verification=Verification.SECONDARY,
        ),
        # --- Ownership cost defaults ------------------------------------------------
        # Assumptions, not rules, and labelled as such wherever they reach a total.
        Rule(
            jurisdiction="ON",
            name="ownership.defaults",
            value={
                "home_insurance_annual_cents": 180_000,
                "condo_insurance_annual_cents": 60_000,
                "utilities_monthly_house_cents": 35_000,
                "utilities_monthly_condo_cents": 15_000,
                "maintenance_reserve_rate": "0.01",
                "maintenance_reserve_rate_condo": "0.002",
            },
            effective_from=date(2026, 1, 1),
            source_url="https://www.cmhc-schl.gc.ca/",
            verification=Verification.SECONDARY,
            note="Planning defaults, used only when the user supplies nothing. Every "
            "one of them surfaces as a visible assumption.",
        ),
        Rule(
            jurisdiction="ON/Toronto",
            name="property_tax.residential_rate",
            value={"rate": "0.007673", "year": 2026},
            effective_from=date(2026, 1, 1),
            source_url="https://www.toronto.ca/services-payments/property-taxes-utilities/"
            "property-tax/property-tax-rates-and-fees/",
            verification=Verification.SECONDARY,
            note="Applied to purchase price as a proxy for assessed value. MPAC "
            "assessments are frozen at a 2016 valuation date, so this overstates tax "
            "on a recently appreciated home — an estimate, and labelled one.",
        ),
        # --- Closing cost estimates -------------------------------------------------
        Rule(
            jurisdiction="ON",
            name="closing.estimates",
            value={
                "legal_fees_cents": 200_000,
                "title_insurance_cents": 50_000,
                "home_inspection_cents": 60_000,
                "appraisal_cents": 40_000,
                "moving_cents": 150_000,
                "adjustments_cents": 100_000,
                "status_certificate_cents": 10_000,
            },
            effective_from=date(2026, 1, 1),
            source_url="https://www.ratehub.ca/closing-costs",
            verification=Verification.SECONDARY,
            note="Typical Ontario ranges. Estimates, flagged individually.",
        ),
    )


def default_rule_set(label: str = "2026.09.1") -> RuleSet:
    """The registry snapshot the engines resolve against."""
    return RuleSet(label=label, rules=default_rules())
