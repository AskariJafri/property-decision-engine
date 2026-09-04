"""The financial engine's contract: what goes in, what comes out, what it promises.

Phase D implements these. They are defined now because everything downstream —
the scoring engine, the API payloads, the fixture matrix — is shaped by them, and
because two distinctions have to be structural rather than remembered.

**"Can afford" is not "may qualify."** :class:`AffordabilityResult` answers the
first: what this costs against what this household earns and already owes.
:class:`QualificationEstimate` answers the second: what published lending rules
produce. They are separate types so that no call site can accidentally merge
them into one reassuring number, and the qualification type carries its own
disclaimer field because ``COMPLIANCE.md`` §1 requires the caveat to travel with
the value rather than live in a UI footer.

**Nothing here is a float.** Money is ``Cents``; rates and ratios are ``Decimal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from app.core.money import ZERO, Cents
from app.engines.base import EngineResult
from app.engines.rules import RuleSet


class PropertyKind(StrEnum):
    DETACHED = "detached"
    SEMI = "semi"
    TOWNHOUSE = "townhouse"
    CONDO_APARTMENT = "condo_apartment"
    CONDO_TOWNHOUSE = "condo_town"
    DUPLEX = "duplex"
    OTHER = "other"


class ResidencyStatus(StrEnum):
    CITIZEN_OR_PR = "citizen_or_pr"
    FOREIGN_NATIONAL = "foreign_national"
    """Drives NRST at 25% province-wide, plus Toronto's 10% MNRST. Never assumed."""

    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BuyerFinancials:
    gross_annual_income_cents: Cents
    household_income_cents: Cents
    monthly_debt_payments_cents: Cents
    down_payment_cents: Cents
    available_savings_cents: Cents
    emergency_fund_cents: Cents
    desired_max_monthly_cents: Cents | None
    first_time_buyer: bool
    residency_status: ResidencyStatus
    fhsa_balance_cents: Cents = ZERO
    rrsp_hbp_available_cents: Cents = ZERO


@dataclass(frozen=True, slots=True)
class PropertyFinancials:
    purchase_price_cents: Cents
    jurisdiction: str
    """``ON/Toronto`` decides whether municipal land transfer tax resolves at all."""

    property_kind: PropertyKind
    annual_property_tax_cents: Cents | None = None
    monthly_condo_fee_cents: Cents | None = None
    square_feet: int | None = None
    is_new_build: bool = False
    """With first-time-buyer status, one of the two routes to a 30-year insured amortization."""


@dataclass(frozen=True, slots=True)
class MortgageTerms:
    contract_rate: Decimal
    """Annual nominal rate as a decimal, e.g. ``Decimal("0.0409")``."""

    amortization_years: int
    term_years: int = 5
    payment_frequency: str = "monthly"
    compounding_per_year: int = 2
    """Canadian fixed mortgages compound semi-annually, not monthly. Getting this
    wrong overstates the payment by roughly 1%, every time, on every file."""


@dataclass(frozen=True, slots=True)
class MortgageResult:
    principal_cents: Cents
    insurance_premium_cents: Cents
    insured: bool
    payment_cents: Cents
    effective_rate: Decimal
    amortization_years: int
    first_year_interest_cents: Cents
    first_year_principal_cents: Cents


@dataclass(frozen=True, slots=True)
class ClosingCostLine:
    key: str
    label: str
    amount_cents: Cents
    rule_keys: tuple[str, ...] = ()
    is_estimate: bool = False
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ClosingCostResult:
    lines: tuple[ClosingCostLine, ...]
    total_cents: Cents
    rebates_cents: Cents
    """Ontario's up-to-$4,000 first-time refund and Toronto's up-to-$4,475, as negatives."""


@dataclass(frozen=True, slots=True)
class OwnershipCostResult:
    mortgage_payment_cents: Cents
    property_tax_cents: Cents
    insurance_cents: Cents
    condo_fee_cents: Cents
    utilities_cents: Cents
    maintenance_reserve_cents: Cents
    total_monthly_cents: Cents


@dataclass(frozen=True, slots=True)
class QualificationEstimate:
    """What published rules produce. Not an approval, and the type says so."""

    may_qualify: bool
    stressed_rate: Decimal
    """The greater of the MQR floor and contract + 2%, per OSFI."""

    gds: Decimal
    tds: Decimal
    gds_limit: Decimal
    tds_limit: Decimal
    insured_eligible: bool
    max_purchase_price_cents: Cents | None
    blocking_reasons: tuple[str, ...] = ()
    disclaimer: str = (
        "This is an estimate produced from published rules. "
        "Only a lender or licensed mortgage broker can confirm what you qualify for."
    )


@dataclass(frozen=True, slots=True)
class AffordabilityResult:
    """What it costs against what this household has. A different question."""

    housing_ratio: Decimal
    total_debt_ratio: Decimal
    budget_ratio: Decimal | None
    reserve_months: Decimal
    cash_required_cents: Cents
    cash_shortfall_cents: Cents


class FinancialEngine(Protocol):
    """Pure. Given inputs and a dated rule set, produces money plus its working.

    Every method returns an :class:`EngineResult`, so the trace that produced a
    figure is inseparable from the figure.
    """

    def mortgage(
        self,
        *,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        terms: MortgageTerms,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[MortgageResult]: ...

    def closing_costs(
        self,
        *,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        mortgage: MortgageResult,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[ClosingCostResult]: ...

    def ownership_cost(
        self,
        *,
        property_: PropertyFinancials,
        mortgage: MortgageResult,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[OwnershipCostResult]: ...

    def qualification(
        self,
        *,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        terms: MortgageTerms,
        ownership: OwnershipCostResult,
        rules: RuleSet,
        as_of: date,
    ) -> EngineResult[QualificationEstimate]: ...

    def affordability(
        self,
        *,
        buyer: BuyerFinancials,
        ownership: OwnershipCostResult,
        closing: ClosingCostResult,
        mortgage: MortgageResult,
    ) -> EngineResult[AffordabilityResult]: ...
