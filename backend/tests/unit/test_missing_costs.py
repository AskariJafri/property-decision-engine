"""A missing cost must never make a house look cheaper.

The failure this guards against is subtle and would be easy to ship: outside the
municipalities whose tax rates we have, property tax drops out of the monthly
figure. The cost falls, affordability improves, and the Buy Score goes *up* — a
property scoring better because we know less about it.
"""

from decimal import Decimal

from app.engines.financial.contracts import AffordabilityResult
from app.engines.scoring.subscores import affordability_subscore

COMFORTABLE = AffordabilityResult(
    housing_ratio=Decimal("0.28"),
    total_debt_ratio=Decimal("0.33"),
    budget_ratio=Decimal("0.95"),
    reserve_months=Decimal("5"),
    cash_required_cents=14_000_000,
    cash_shortfall_cents=0,
)


def test_a_complete_cost_scores_at_full_confidence():
    result = affordability_subscore(COMFORTABLE)
    assert result.confidence == Decimal("0.95")


def test_a_missing_cost_component_costs_confidence():
    complete = affordability_subscore(COMFORTABLE)
    partial = affordability_subscore(COMFORTABLE, missing_cost_components=("property tax",))
    assert partial.confidence < complete.confidence


def test_each_missing_component_is_named_in_a_factor():
    """The user sees which cost is absent, not just a lower confidence number."""
    result = affordability_subscore(
        COMFORTABLE, missing_cost_components=("property tax", "the condo fee")
    )
    sentences = " ".join(f.sentence for f in result.factors)
    assert "property tax" in sentences
    assert "the condo fee" in sentences
    assert "understated" in sentences


def test_the_score_is_not_secretly_penalised_instead():
    """Confidence carries the uncertainty; the score itself still reflects the
    numbers we actually have. Docking the score would be guessing in the other
    direction."""
    complete = affordability_subscore(COMFORTABLE)
    partial = affordability_subscore(COMFORTABLE, missing_cost_components=("property tax",))
    assert partial.score == complete.score


def test_confidence_never_goes_negative():
    result = affordability_subscore(
        COMFORTABLE, missing_cost_components=("a", "b", "c", "d", "e", "f")
    )
    assert result.confidence >= Decimal("0")
