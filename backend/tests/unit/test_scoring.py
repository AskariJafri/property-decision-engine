"""Aggregation, weighting, missing data, and the refusal to score."""

from decimal import Decimal

import pytest

from app.ai.contracts import (
    Evidence,
    Judgement,
    JudgementItem,
    JudgementType,
    apply_judgement,
)
from app.engines.financial.contracts import AffordabilityResult
from app.engines.scoring.contracts import BASE_WEIGHTS, Component, Subscore
from app.engines.scoring.curves import HOUSING_RATIO, piecewise
from app.engines.scoring.engine import aggregate, clamp_modifier, modifiers_for, unavailable
from app.engines.scoring.subscores import (
    affordability_subscore,
    property_quality_subscore,
    risk_subscore,
    value_subscore,
)
from app.engines.valuation.contracts import (
    FairValueRange,
    RiskCategory,
    RiskFlag,
    RiskSeverity,
    RiskStatus,
    ValuationBasis,
)

ONE = Decimal(1)


def scored(component: Component, score: str, confidence: str = "0.9") -> Subscore:
    return Subscore(
        component=component,
        available=True,
        score=Decimal(score),
        confidence=Decimal(confidence),
        base_weight=BASE_WEIGHTS[component],
        effective_weight=Decimal(0),
        contribution=Decimal(0),
    )


def full_set(score: str = "80") -> tuple[Subscore, ...]:
    return tuple(scored(c, score) for c in Component)


class TestCurves:
    def test_interpolates_between_anchors(self):
        # Halfway between 0.25 -> 100 and 0.32 -> 75
        assert piecewise(Decimal("0.285"), HOUSING_RATIO) == Decimal("87.50")

    def test_clamps_at_both_ends(self):
        assert piecewise(Decimal("0.10"), HOUSING_RATIO) == Decimal("100")
        assert piecewise(Decimal("0.90"), HOUSING_RATIO) == Decimal("0")


class TestAggregation:
    def test_a_uniform_set_scores_itself(self):
        result = aggregate(subscores=full_set("80"))
        assert result.buy_score == 80
        assert result.withheld_reason is None
        assert sum(result.weights_applied.values()) == pytest.approx(
            Decimal("1"), abs=Decimal("0.001")
        )

    def test_weights_sum_to_one_after_redistribution(self):
        subscores = (
            *[scored(c, "80") for c in Component if c is not Component.VALUE],
            unavailable(Component.VALUE, "no comparables supplied"),
        )
        result = aggregate(subscores=subscores)
        assert sum(result.weights_applied.values()) == pytest.approx(
            Decimal("1"), abs=Decimal("0.001")
        )
        assert result.redistributed_weight == BASE_WEIGHTS[Component.VALUE]

    def test_a_missing_component_does_not_drag_the_score_down(self):
        """Dropping is not zeroing. An 80 everywhere else stays an 80."""
        complete = aggregate(subscores=full_set("80")).buy_score
        partial = aggregate(
            subscores=(
                *[scored(c, "80") for c in Component if c is not Component.VALUE],
                unavailable(Component.VALUE, "no comparables"),
            )
        ).buy_score
        assert complete == partial == 80

    def test_but_it_does_cost_confidence(self):
        complete = aggregate(subscores=full_set("80")).confidence
        partial = aggregate(
            subscores=(
                *[scored(c, "80") for c in Component if c is not Component.VALUE],
                unavailable(Component.VALUE, "no comparables"),
            )
        ).confidence
        assert partial < complete

    def test_past_thirty_five_percent_missing_there_is_no_score(self):
        dropped = {Component.VALUE, Component.AFFORDABILITY}  # 45% of base weight
        subscores = tuple(
            unavailable(c, "not computed") if c in dropped else scored(c, "80") for c in Component
        )
        result = aggregate(subscores=subscores)
        assert result.buy_score is None
        assert result.withheld_reason is not None
        assert "45%" in result.withheld_reason
        # ...and the subscores still stand on their own.
        assert [s for s in result.subscores if s.available and s.score == Decimal("80")]

    def test_duplicate_components_are_refused(self):
        with pytest.raises(ValueError, match="duplicate"):
            aggregate(subscores=(scored(Component.RISK, "80"), scored(Component.RISK, "60")))

    def test_the_same_inputs_always_produce_the_same_score(self):
        subscores = full_set("73")
        mods = {Component.RISK: Decimal("1.4")}
        assert aggregate(subscores=subscores, modifiers=mods) == aggregate(
            subscores=subscores, modifiers=mods
        )


class TestModifiers:
    def test_an_investor_and_a_family_read_the_same_house_differently(self):
        subscores = (
            *[scored(c, "80") for c in Component if c is not Component.INVESTMENT],
            scored(Component.INVESTMENT, "30"),
        )
        investor = aggregate(
            subscores=subscores,
            modifiers=modifiers_for(
                goal="investment",
                horizon="3_to_5",
                risk_posture="balanced",
                has_children=False,
                schools_importance=0,
                budget_pressure=False,
            ),
        )
        family = aggregate(
            subscores=subscores,
            modifiers=modifiers_for(
                goal="primary_residence",
                horizon="over_10",
                risk_posture="balanced",
                has_children=True,
                schools_importance=5,
                budget_pressure=False,
            ),
        )
        assert investor.buy_score is not None and family.buy_score is not None
        assert investor.buy_score < family.buy_score

    def test_modifiers_are_clamped(self):
        assert clamp_modifier(Decimal("9")) == Decimal("2.0")
        assert clamp_modifier(Decimal("0.01")) == Decimal("0.5")

    def test_no_profile_can_turn_the_composite_into_one_component(self):
        subscores = (
            *[scored(c, "0") for c in Component if c is not Component.INVESTMENT],
            scored(Component.INVESTMENT, "100"),
        )
        result = aggregate(
            subscores=subscores,
            modifiers=dict.fromkeys(Component, Decimal("0.5"))
            | {Component.INVESTMENT: Decimal("2")},
        )
        assert result.buy_score is not None and result.buy_score < 40


class TestSubscoreBuilders:
    def test_affordability_reads_the_household_numbers(self):
        comfortable = affordability_subscore(
            AffordabilityResult(
                housing_ratio=Decimal("0.26"),
                total_debt_ratio=Decimal("0.31"),
                budget_ratio=Decimal("0.9"),
                reserve_months=Decimal("8"),
                cash_required_cents=100,
                cash_shortfall_cents=0,
            )
        )
        strained = affordability_subscore(
            AffordabilityResult(
                housing_ratio=Decimal("0.44"),
                total_debt_ratio=Decimal("0.52"),
                budget_ratio=Decimal("1.2"),
                reserve_months=Decimal("0.4"),
                cash_required_cents=100,
                cash_shortfall_cents=500_000,
            )
        )
        assert comfortable.score is not None and strained.score is not None
        assert comfortable.score > 80 > strained.score
        assert any("more cash" in f.sentence for f in strained.factors)

    def test_value_scores_by_position_in_the_range(self):
        cheap = value_subscore(
            asking_cents=80_000_000,
            fair_value=FairValueRange(
                low_cents=82_000_000,
                high_cents=84_500_000,
                basis=ValuationBasis.USER_COMPARABLES,
                confidence=Decimal("0.75"),
                note="",
            ),
        )
        dear = value_subscore(
            asking_cents=95_000_000,
            fair_value=FairValueRange(
                low_cents=82_000_000,
                high_cents=84_500_000,
                basis=ValuationBasis.USER_COMPARABLES,
                confidence=Decimal("0.75"),
                note="",
            ),
        )
        assert cheap.score is not None and dear.score is not None
        assert cheap.score > dear.score
        assert cheap.confidence == Decimal("0.75")

    def test_property_quality_is_unavailable_without_any_attribute(self):
        result = property_quality_subscore(year_built=None, as_of_year=2026, square_feet=None)
        assert result.available is False
        assert result.unavailable_reason


class TestRiskAndUnknowns:
    def _flag(self, status: RiskStatus, severity: RiskSeverity = RiskSeverity.HIGH) -> RiskFlag:
        return RiskFlag(
            category=RiskCategory.FLOOD,
            status=status,
            severity=severity,
            evidence="e",
            explanation="Flood exposure",
            recommended_action="Ask the conservation authority",
            source_key="src_trca",
        )

    def test_unknown_reduces_confidence_and_never_the_score(self):
        """The rule that keeps "we could not check" from reading as "it floods"."""
        clean = risk_subscore(())
        unknown = risk_subscore((self._flag(RiskStatus.UNKNOWN),))
        assert unknown.score == clean.score == Decimal("100.00")
        assert unknown.confidence < clean.confidence

    def test_confirmed_costs_more_than_potential(self):
        confirmed = risk_subscore((self._flag(RiskStatus.CONFIRMED),))
        potential = risk_subscore((self._flag(RiskStatus.POTENTIAL),))
        assert confirmed.score is not None and potential.score is not None
        assert confirmed.score < potential.score < Decimal("100")


class TestAiJudgementsReachTheScore:
    def _judgement(self, direction: int) -> Judgement:
        return Judgement(
            judgement_type=JudgementType.CONDITION_SIGNAL,
            items=(
                JudgementItem(
                    key="furnace_original",
                    direction=direction,
                    weight=Decimal("1"),
                    statement="the furnace is described as original",
                    evidence=(Evidence(quote="furnace original to the home", source_ref="s#1"),),
                ),
            ),
            confidence=Decimal("1"),
            model_id="llama3.1:8b-instruct-q4_K_M",
            prompt_hash="a" * 64,
            sampling={"temperature": 0},
        )

    def test_a_judgement_moves_property_quality_within_its_cap(self):
        base = property_quality_subscore(year_built=1960, as_of_year=2026, square_feet=1400)
        worse = property_quality_subscore(
            year_built=1960,
            as_of_year=2026,
            square_feet=1400,
            adjustment=apply_judgement(self._judgement(-1)),
        )
        assert base.score is not None and worse.score is not None
        assert worse.score < base.score
        assert base.score - worse.score <= Decimal("8")
        assert any("AI-inferred" in f.sentence for f in worse.factors)

    def test_a_wrong_judgement_cannot_flip_the_recommendation(self):
        """The point of the cap: a hallucinating model costs a couple of points on
        the composite, not a decision."""
        subscores = full_set("80")
        with_ai = tuple(
            property_quality_subscore(
                year_built=2015,
                as_of_year=2026,
                square_feet=1400,
                adjustment=apply_judgement(self._judgement(-1)),
            )
            if s.component is Component.PROPERTY_QUALITY
            else s
            for s in subscores
        )
        clean = aggregate(subscores=subscores).buy_score
        adjusted = aggregate(subscores=with_ai).buy_score
        assert clean is not None and adjusted is not None
        assert abs(clean - adjusted) <= 3
