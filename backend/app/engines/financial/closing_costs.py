"""Closing costs: land transfer taxes, rebates, and the cash a buyer actually needs.

The land transfer taxes are the part worth being pedantic about. A Toronto buyer
pays two of them, both marginal, and since 1 April 2026 the municipal one runs to
8.60% at the top. A $4M house attracts about $57,000 more municipal tax than the
same house did in March. Nothing here is hardcoded: the brackets resolve out of
the dated registry, so an analysis of a March closing reproduces March's number.

Rebates are the other trap. Both first-time rebates are **capped**, so they cannot
be modelled as an exemption threshold — a $900,000 Toronto purchase gets exactly
$4,000 provincially and $4,475 municipally, no more, and a $300,000 purchase gets
only as much as it owes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.core.money import Cents, apply_rate, cents
from app.engines.base import EngineResult, TraceBuilder
from app.engines.financial.contracts import (
    BuyerFinancials,
    ClosingCostLine,
    ClosingCostResult,
    MortgageResult,
    PropertyFinancials,
    PropertyKind,
    ResidencyStatus,
)
from app.engines.rules import RuleNotFoundError, RuleSet

#: A condominium unit is a single family residence for land transfer tax purposes,
#: so the graduated luxury bands reach it too. Only ``OTHER`` falls outside.
_SINGLE_FAMILY = {
    PropertyKind.DETACHED,
    PropertyKind.SEMI,
    PropertyKind.TOWNHOUSE,
    PropertyKind.CONDO_APARTMENT,
    PropertyKind.CONDO_TOWNHOUSE,
    PropertyKind.DUPLEX,
}


def marginal_tax(consideration: Cents, brackets: list[list[Any]]) -> Cents:
    """Sum a marginal bracket table over the consideration.

    Brackets are ``(threshold_cents, rate)`` ascending; each rate applies to the
    portion above its own threshold and below the next one.
    """
    parsed = [(int(row[0]), Decimal(str(row[1]))) for row in brackets]
    total = 0
    for index, (threshold, rate) in enumerate(parsed):
        if consideration <= threshold:
            break
        ceiling = parsed[index + 1][0] if index + 1 < len(parsed) else consideration
        portion = min(consideration, ceiling) - threshold
        total += apply_rate(cents(portion), rate)
    return cents(total)


def _bracket_rule_name(kind: PropertyKind, prefix: str) -> str:
    return f"{prefix}.brackets.sfr" if kind in _SINGLE_FAMILY else f"{prefix}.brackets.other"


def compute_closing_costs(
    *,
    property_: PropertyFinancials,
    buyer: BuyerFinancials,
    mortgage: MortgageResult,
    rules: RuleSet,
    as_of: date,
) -> EngineResult[ClosingCostResult]:
    """Every line a buyer pays on closing, with its source and whether it is an estimate."""
    trace = TraceBuilder()
    price = property_.purchase_price_cents
    lines: list[ClosingCostLine] = []
    rebates = 0

    # --- Provincial land transfer tax ----------------------------------------------
    ltt_rule = rules.get("ON", _bracket_rule_name(property_.property_kind, "ltt"), as_of=as_of)
    ltt = trace.step(
        "Ontario land transfer tax",
        "marginal brackets over consideration",
        {"consideration_cents": price, "brackets": ltt_rule.value["brackets"]},
        marginal_tax(price, ltt_rule.value["brackets"]),
        unit="cents",
        rule_keys=(f"ON/{ltt_rule.name}",),
    )
    lines.append(
        ClosingCostLine(
            key="ltt_ontario",
            label="Ontario land transfer tax",
            amount_cents=ltt,
            rule_keys=(f"ON/{ltt_rule.name}",),
        )
    )

    if buyer.first_time_buyer:
        refund_rule = rules.get("ON", "ltt.first_time_buyer_refund_max_cents", as_of=as_of)
        refund = min(ltt, cents(int(refund_rule.value["amount_cents"])))
        rebates += refund
        lines.append(
            ClosingCostLine(
                key="ltt_ontario_ftb_refund",
                label="Ontario first-time buyer refund",
                amount_cents=cents(-refund),
                rule_keys=("ON/ltt.first_time_buyer_refund_max_cents",),
            )
        )
        trace.step(
            "Ontario first-time buyer refund",
            "min(ltt, refund_cap)",
            {"ltt_cents": ltt, "cap_cents": refund_rule.value["amount_cents"]},
            refund,
            unit="cents",
        )

    # --- Municipal land transfer tax ------------------------------------------------
    # Outside Toronto this simply does not resolve, and that is a normal answer
    # rather than a failure: the buyer pays provincial tax alone.
    try:
        mltt_rule = rules.get(
            property_.jurisdiction,
            _bracket_rule_name(property_.property_kind, "mltt"),
            as_of=as_of,
        )
    except RuleNotFoundError:
        mltt_rule = None

    if mltt_rule is not None:
        mltt = trace.step(
            "municipal land transfer tax",
            "marginal brackets over consideration",
            {"consideration_cents": price, "brackets": mltt_rule.value["brackets"]},
            marginal_tax(price, mltt_rule.value["brackets"]),
            unit="cents",
            rule_keys=(f"{mltt_rule.jurisdiction}/{mltt_rule.name}",),
        )
        lines.append(
            ClosingCostLine(
                key="mltt",
                label="Toronto municipal land transfer tax",
                amount_cents=mltt,
                rule_keys=(f"{mltt_rule.jurisdiction}/{mltt_rule.name}",),
            )
        )
        if buyer.first_time_buyer:
            rebate_rule = rules.get(
                property_.jurisdiction, "mltt.first_time_buyer_rebate_max_cents", as_of=as_of
            )
            rebate = min(mltt, cents(int(rebate_rule.value["amount_cents"])))
            rebates += rebate
            lines.append(
                ClosingCostLine(
                    key="mltt_ftb_rebate",
                    label="Toronto first-time buyer rebate",
                    amount_cents=cents(-rebate),
                    rule_keys=(f"{property_.jurisdiction}/mltt.first_time_buyer_rebate_max_cents",),
                )
            )
        fee_rule = rules.find(property_.jurisdiction, "mltt.administration_fee_cents", as_of=as_of)
        if fee_rule is not None:
            base = int(fee_rule.value["amount_cents"])
            with_tax = base + apply_rate(cents(base), Decimal(str(fee_rule.value["hst_rate"])))
            lines.append(
                ClosingCostLine(
                    key="mltt_admin_fee",
                    label="MLTT administration fee",
                    amount_cents=cents(with_tax),
                    rule_keys=(f"{property_.jurisdiction}/mltt.administration_fee_cents",),
                )
            )

    # --- Non-resident speculation tax ------------------------------------------------
    if buyer.residency_status is ResidencyStatus.FOREIGN_NATIONAL:
        nrst_rule = rules.get("ON", "nrst.rate", as_of=as_of)
        nrst = apply_rate(price, Decimal(str(nrst_rule.value["rate"])))
        lines.append(
            ClosingCostLine(
                key="nrst",
                label="Ontario non-resident speculation tax",
                amount_cents=nrst,
                rule_keys=("ON/nrst.rate",),
            )
        )
        mnrst_rule = rules.find(property_.jurisdiction, "mnrst.rate", as_of=as_of)
        if mnrst_rule is not None:
            lines.append(
                ClosingCostLine(
                    key="mnrst",
                    label="Toronto municipal non-resident speculation tax",
                    amount_cents=apply_rate(price, Decimal(str(mnrst_rule.value["rate"]))),
                    rule_keys=(f"{property_.jurisdiction}/mnrst.rate",),
                )
            )
    elif buyer.residency_status is ResidencyStatus.UNKNOWN:
        # 25% of the price is far too large a number to assume either way.
        trace.assume(
            "residency_status",
            "unknown",
            "Residency was not stated, so no non-resident speculation tax is included. "
            "A foreign national would pay 25% provincially, and a further 10% in Toronto.",
        )

    # --- Professional and moving costs -------------------------------------------------
    estimates = rules.get("ON", "closing.estimates", as_of=as_of).value
    estimate_lines = [
        ("legal_fees", "Legal fees", "legal_fees_cents"),
        ("title_insurance", "Title insurance", "title_insurance_cents"),
        ("home_inspection", "Home inspection", "home_inspection_cents"),
        ("appraisal", "Appraisal", "appraisal_cents"),
        ("moving", "Moving", "moving_cents"),
        ("adjustments", "Adjustments (tax and utility)", "adjustments_cents"),
    ]
    if property_.property_kind in {PropertyKind.CONDO_APARTMENT, PropertyKind.CONDO_TOWNHOUSE}:
        estimate_lines.append(
            ("status_certificate", "Status certificate", "status_certificate_cents")
        )

    for key, label, field in estimate_lines:
        lines.append(
            ClosingCostLine(
                key=key,
                label=label,
                amount_cents=cents(int(estimates[field])),
                rule_keys=("ON/closing.estimates",),
                is_estimate=True,
                note="Typical Ontario range; your quote will differ.",
            )
        )

    # Ontario RST on the insurance premium is reported at 8% but unverified, so the
    # rule is inactive and the engine says what it has left out.
    if mortgage.insurance_premium_cents > 0:
        rst = rules.find("ON", "insured.premium_sales_tax_rate", as_of=as_of)
        if rst is None:
            trace.assume(
                "insured.premium_sales_tax",
                "excluded",
                "Ontario is reported to charge 8% retail sales tax on the mortgage "
                "insurance premium, payable at closing rather than financed. That rate "
                "could not be confirmed, so it is excluded — budget for roughly "
                f"${apply_rate(mortgage.insurance_premium_cents, Decimal('0.08')) / 100:,.0f} "
                "more than shown.",
            )

    total = trace.step(
        "total closing costs",
        "sum of all lines, rebates included as negatives",
        {"line_count": len(lines)},
        cents(sum(line.amount_cents for line in lines)),
        unit="cents",
    )

    return trace.finish(
        ClosingCostResult(lines=tuple(lines), total_cents=total, rebates_cents=cents(rebates))
    )
