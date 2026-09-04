"""Building each subscore from what the engines and providers produced.

Every builder returns either a scored component with the sentences that explain it,
or an explicitly unavailable one with a reason. None of them invent an input.

AI judgements (ADR 0004) reach exactly two of these — property quality and risk —
through :func:`apply_capped`, which clamps the adjustment and records that it did.
"""

from __future__ import annotations

from decimal import Decimal

from app.engines.financial.contracts import AffordabilityResult, QualificationEstimate
from app.engines.scoring import curves
from app.engines.scoring.contracts import (
    BASE_WEIGHTS,
    CappedAdjustment,
    Component,
    Direction,
    Factor,
    Subscore,
)
from app.engines.valuation.contracts import FairValueRange, RiskFlag, RiskStatus

ZERO = Decimal(0)
ONE = Decimal(1)


def _scored(
    component: Component,
    score: Decimal,
    confidence: Decimal,
    factors: tuple[Factor, ...] = (),
) -> Subscore:
    bounded = max(ZERO, min(Decimal(100), score)).quantize(Decimal("0.01"))
    return Subscore(
        component=component,
        available=True,
        score=bounded,
        confidence=max(ZERO, min(ONE, confidence)),
        base_weight=BASE_WEIGHTS[component],
        effective_weight=ZERO,  # set by aggregate()
        contribution=ZERO,
        factors=factors,
    )


def _factor(component: Component, positive: bool, magnitude: str, sentence: str) -> Factor:
    return Factor(
        component=component,
        direction=Direction.POSITIVE if positive else Direction.NEGATIVE,
        magnitude=Decimal(magnitude),
        sentence=sentence,
    )


def apply_capped(score: Decimal, adjustment: CappedAdjustment | None) -> Decimal:
    """Apply a bounded AI adjustment to a subscore, or leave it alone."""
    if adjustment is None:
        return score
    return score + adjustment.applied_adjustment


def affordability_subscore(result: AffordabilityResult) -> Subscore:
    """Four sub-metrics, weighted, from the household's own numbers."""
    housing = curves.piecewise(result.housing_ratio, curves.HOUSING_RATIO)
    debt = curves.piecewise(result.total_debt_ratio, curves.TOTAL_DEBT_RATIO)
    reserve = curves.piecewise(result.reserve_months, curves.RESERVE_MONTHS)

    parts = [(housing, Decimal("0.30")), (debt, Decimal("0.25")), (reserve, Decimal("0.20"))]
    if result.budget_ratio is not None:
        parts.append(
            (curves.piecewise(result.budget_ratio, curves.BUDGET_ADHERENCE), Decimal("0.25"))
        )

    weight_total = sum(w for _, w in parts)
    score = sum((s * w for s, w in parts), start=ZERO) / weight_total

    factors: list[Factor] = []
    if result.housing_ratio <= Decimal("0.32"):
        factors.append(
            _factor(
                Component.AFFORDABILITY,
                True,
                "8",
                f"Housing would take {result.housing_ratio:.0%} of gross income, inside the "
                "range most lenders treat as comfortable.",
            )
        )
    else:
        factors.append(
            _factor(
                Component.AFFORDABILITY,
                False,
                "10",
                f"Housing would take {result.housing_ratio:.0%} of gross income.",
            )
        )
    if result.reserve_months < 3:
        factors.append(
            _factor(
                Component.AFFORDABILITY,
                False,
                "12",
                f"Only {result.reserve_months:.1f} months of ownership cost would be left in "
                "reserve after closing.",
            )
        )
    if result.cash_shortfall_cents > 0:
        factors.append(
            _factor(
                Component.AFFORDABILITY,
                False,
                "20",
                f"Closing needs ${result.cash_shortfall_cents / 100:,.0f} more cash than the "
                "savings on file.",
            )
        )
    if result.budget_ratio is not None and result.budget_ratio > 1:
        factors.append(
            _factor(
                Component.AFFORDABILITY,
                False,
                "12",
                f"The monthly cost is {result.budget_ratio - 1:.0%} above the maximum you set.",
            )
        )

    # Confidence is high here: these are our own calculations over the user's own
    # figures, not third-party data.
    return _scored(Component.AFFORDABILITY, score, Decimal("0.95"), tuple(factors))


def value_subscore(*, asking_cents: int, fair_value: FairValueRange) -> Subscore:
    """Where the asking price sits in the fair-value range."""
    span = fair_value.high_cents - fair_value.low_cents
    if span <= 0:
        position = ZERO if asking_cents <= fair_value.low_cents else ONE
    else:
        position = (Decimal(asking_cents - fair_value.low_cents) / Decimal(span)).quantize(
            Decimal("0.0001")
        )

    score = curves.piecewise(position, curves.PRICE_POSITION)
    inside = fair_value.low_cents <= asking_cents <= fair_value.high_cents
    factors = (
        _factor(
            Component.VALUE,
            inside,
            "10" if inside else "15",
            (
                "The asking price sits inside the estimated fair-value range."
                if inside
                else (
                    "The asking price is below the estimated range."
                    if asking_cents < fair_value.low_cents
                    else "The asking price is "
                    f"${(asking_cents - fair_value.high_cents) / 100:,.0f} above the top of "
                    "the estimated range."
                )
            ),
        ),
    )
    return _scored(Component.VALUE, score, fair_value.confidence, factors)


def personal_fit_subscore(
    *,
    bedrooms: int | None,
    min_bedrooms: int | None,
    bathrooms: Decimal | None,
    min_bathrooms: int | None,
    has_parking: bool | None,
    requires_parking: bool | None,
    commute_minutes: int | None,
    max_commute_minutes: int | None,
) -> Subscore:
    """Requirement-by-requirement matching, with hard failures capped at 40.

    A house that fails something the household called mandatory does not get to be
    a 78 because it is lovely in other ways.
    """
    checks: list[tuple[Decimal, Decimal, bool]] = []  # score, weight, is_hard_failure
    factors: list[Factor] = []

    if min_bedrooms is not None:
        if bedrooms is None:
            checks.append((Decimal(50), Decimal("0.3"), False))
        elif bedrooms >= min_bedrooms:
            # Exceeding a requirement earns diminishing credit: a fourth bedroom for
            # a couple who asked for two is not twice as good.
            surplus = min(bedrooms - min_bedrooms, 2)
            checks.append((Decimal(90) + Decimal(5) * surplus, Decimal("0.3"), False))
            factors.append(
                _factor(
                    Component.PERSONAL_FIT, True, "8", f"{bedrooms} bedrooms meets your minimum."
                )
            )
        else:
            checks.append((Decimal(20), Decimal("0.3"), True))
            factors.append(
                _factor(
                    Component.PERSONAL_FIT,
                    False,
                    "25",
                    f"{bedrooms} bedrooms is below the {min_bedrooms} you require.",
                )
            )

    if min_bathrooms is not None and bathrooms is not None:
        meets = bathrooms >= Decimal(min_bathrooms)
        checks.append((Decimal(95) if meets else Decimal(30), Decimal("0.2"), not meets))

    if requires_parking:
        if has_parking is None:
            checks.append((Decimal(50), Decimal("0.15"), False))
        else:
            checks.append(
                (Decimal(100) if has_parking else Decimal(0), Decimal("0.15"), not has_parking)
            )
            if not has_parking:
                factors.append(
                    _factor(Component.PERSONAL_FIT, False, "20", "No parking, which you require.")
                )

    if max_commute_minutes and commute_minutes is not None:
        ratio = Decimal(commute_minutes) / Decimal(max_commute_minutes)
        checks.append(
            (
                curves.piecewise(ratio, curves.COMMUTE_ADHERENCE),
                Decimal("0.35"),
                ratio > Decimal("1.3"),
            )
        )
        factors.append(
            _factor(
                Component.PERSONAL_FIT,
                ratio <= 1,
                "12",
                f"A {commute_minutes} minute commute against your {max_commute_minutes} minute "
                "maximum.",
            )
        )

    if not checks:
        return unavailable_fit()

    weight_total = sum(w for _, w, _ in checks)
    score = sum((s * w for s, w, _ in checks), start=ZERO) / weight_total
    if any(hard for _, _, hard in checks):
        score = min(score, Decimal(40))

    coverage = Decimal(len(checks)) / Decimal(4)
    return _scored(
        Component.PERSONAL_FIT, score, min(ONE, coverage + Decimal("0.3")), tuple(factors)
    )


def unavailable_fit() -> Subscore:
    from app.engines.scoring.engine import unavailable

    return unavailable(
        Component.PERSONAL_FIT,
        "No requirements on file to match against — tell us what you need and this "
        "becomes the most useful number here.",
    )


def property_quality_subscore(
    *,
    year_built: int | None,
    as_of_year: int,
    square_feet: int | None,
    adjustment: CappedAdjustment | None = None,
) -> Subscore:
    """Age and size, adjusted by a capped condition judgement where one exists."""
    if year_built is None and square_feet is None:
        from app.engines.scoring.engine import unavailable

        return unavailable(
            Component.PROPERTY_QUALITY,
            "No year built or floor area supplied, so there is nothing to assess.",
        )

    parts: list[tuple[Decimal, Decimal]] = []
    factors: list[Factor] = []
    if year_built is not None:
        age = Decimal(max(0, as_of_year - year_built))
        parts.append((curves.piecewise(age, curves.PROPERTY_AGE), Decimal("0.6")))
        if age > 60:
            factors.append(
                _factor(
                    Component.PROPERTY_QUALITY,
                    False,
                    "10",
                    f"Built in {year_built}; major systems in a home this age are often at or "
                    "past their service life.",
                )
            )
    if square_feet is not None:
        parts.append((Decimal(75), Decimal("0.4")))

    weight_total = sum(w for _, w in parts)
    score = sum((s * w for s, w in parts), start=ZERO) / weight_total
    score = apply_capped(score, adjustment)

    # Condition is the weakest input in the MVP — mostly user-asserted — so the
    # confidence says so rather than the score pretending otherwise.
    confidence = Decimal("0.55") if year_built and square_feet else Decimal("0.4")
    if adjustment is not None:
        factors.append(
            _factor(
                Component.PROPERTY_QUALITY,
                adjustment.applied_adjustment > 0,
                str(abs(adjustment.applied_adjustment)),
                "Adjusted for condition signals found in the listing text (AI-inferred).",
            )
        )
    return _scored(Component.PROPERTY_QUALITY, score, confidence, tuple(factors))


def risk_subscore(
    flags: tuple[RiskFlag, ...], adjustment: CappedAdjustment | None = None
) -> Subscore:
    """Starts at 100 and is reduced by what is actually known.

    ``UNKNOWN`` flags reduce **confidence**, never the score. "We could not check
    for flooding" must never render as "this house floods".
    """
    severity_cost = {"high": Decimal(25), "medium": Decimal(12), "low": Decimal(5)}
    score = Decimal(100)
    factors: list[Factor] = []
    unknowns = 0

    for flag in flags:
        if flag.status is RiskStatus.UNKNOWN:
            unknowns += 1
            continue
        cost = severity_cost[flag.severity.value]
        if flag.status is RiskStatus.POTENTIAL:
            cost *= Decimal("0.4")  # a suspicion is not a finding
        score -= cost
        factors.append(
            _factor(Component.RISK, False, str(cost), f"{flag.explanation} ({flag.status.value})")
        )

    score = apply_capped(max(ZERO, score), adjustment)
    confidence = max(Decimal("0.3"), Decimal("0.9") - Decimal("0.15") * unknowns)
    return _scored(Component.RISK, score, confidence, tuple(factors))


def qualification_factors(estimate: QualificationEstimate) -> tuple[Factor, ...]:
    """Sentences about qualification, which informs affordability without scoring it."""
    if estimate.may_qualify:
        return (
            _factor(
                Component.AFFORDABILITY,
                True,
                "6",
                f"At the {estimate.stressed_rate:.2%} stress-test rate the debt-service ratios "
                f"clear the published guidelines ({estimate.gds:.0%} of {estimate.gds_limit:.0%}).",
            ),
        )
    return tuple(
        _factor(Component.AFFORDABILITY, False, "18", reason)
        for reason in estimate.blocking_reasons
    )
