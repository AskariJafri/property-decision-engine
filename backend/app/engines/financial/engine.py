"""The financial engine, assembled.

Implements :class:`~app.engines.financial.contracts.FinancialEngine`. Pure: it takes
value objects and a dated rule set and returns value objects plus their working.
No session, no provider, no model — enforced by ``tests/unit/test_layering.py``.
"""

from __future__ import annotations

from datetime import date

from app.engines.base import EngineResult
from app.engines.financial.closing_costs import compute_closing_costs
from app.engines.financial.contracts import (
    AffordabilityResult,
    BuyerFinancials,
    ClosingCostResult,
    MortgageResult,
    MortgageTerms,
    OwnershipCostResult,
    PropertyFinancials,
    QualificationEstimate,
)
from app.engines.financial.mortgage import compute_mortgage
from app.engines.financial.ownership import compute_affordability, compute_ownership_cost
from app.engines.financial.qualification import compute_qualification
from app.engines.rules import RuleSet


class DeterministicFinancialEngine:
    """The only implementation. Named for the property that matters about it."""

    def mortgage(
        self,
        *,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        terms: MortgageTerms,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[MortgageResult]:
        return compute_mortgage(
            property_=property_, buyer=buyer, terms=terms, rules=rules, as_of=as_of
        )

    def closing_costs(
        self,
        *,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        mortgage: MortgageResult,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[ClosingCostResult]:
        return compute_closing_costs(
            property_=property_, buyer=buyer, mortgage=mortgage, rules=rules, as_of=as_of
        )

    def ownership_cost(
        self,
        *,
        property_: PropertyFinancials,
        mortgage: MortgageResult,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[OwnershipCostResult]:
        return compute_ownership_cost(
            property_=property_, mortgage=mortgage, rules=rules, as_of=as_of
        )

    def qualification(
        self,
        *,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        terms: MortgageTerms,
        ownership: OwnershipCostResult,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[QualificationEstimate]:
        return compute_qualification(
            property_=property_,
            buyer=buyer,
            terms=terms,
            ownership=ownership,
            rules=rules,
            as_of=as_of,
        )

    def affordability(
        self,
        *,
        buyer: BuyerFinancials,
        ownership: OwnershipCostResult,
        closing: ClosingCostResult,
        mortgage: MortgageResult,
    ) -> EngineResult[AffordabilityResult]:
        return compute_affordability(
            buyer=buyer, ownership=ownership, closing=closing, mortgage=mortgage
        )
