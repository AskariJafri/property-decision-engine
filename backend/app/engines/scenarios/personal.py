"""How the property fits the situation the buyer described.

Arithmetic over the buyer's own figures and the computed costs — nothing more.
It says what is left, not whether that is enough: "based on the information you
provided" is the whole claim, and the labels say which inputs were theirs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Basis = Literal["user_provided", "known", "estimated", "assumption", "unavailable"]


@dataclass(frozen=True, slots=True)
class PersonalInput:
    gross_annual_income_cents: int
    monthly_net_income_cents: int | None
    monthly_debt_payments_cents: int
    other_monthly_expenses_cents: int | None
    monthly_housing_cost_cents: int
    cash_required_cents: int
    available_savings_cents: int
    emergency_fund_cents: int


@dataclass(frozen=True, slots=True)
class PersonalLine:
    key: str
    label: str
    amount_cents: int | None
    basis: Basis
    note: str


@dataclass(frozen=True, slots=True)
class PersonalFit:
    lines: tuple[PersonalLine, ...]
    housing_share_of_gross: Decimal
    emergency_months: Decimal | None
    """Months the emergency fund covers housing plus debts, if both are known."""


def personal_fit(facts: PersonalInput) -> PersonalFit:
    gross_monthly = facts.gross_annual_income_cents // 12
    committed = facts.monthly_housing_cost_cents + facts.monthly_debt_payments_cents

    lines = [
        PersonalLine(
            "gross_monthly_income",
            "Gross monthly income",
            gross_monthly,
            "user_provided",
            "Your annual household income divided by 12, before tax.",
        ),
        PersonalLine(
            "monthly_housing_cost",
            "Monthly housing cost",
            facts.monthly_housing_cost_cents,
            "estimated",
            "Mortgage, property tax, insurance, condo fee, utilities and maintenance, "
            "as computed above — some parts are planning assumptions.",
        ),
        PersonalLine(
            "existing_debt",
            "Existing debt payments",
            facts.monthly_debt_payments_cents,
            "user_provided",
            "The monthly debt payments you entered.",
        ),
    ]
    if facts.other_monthly_expenses_cents is not None:
        lines.append(
            PersonalLine(
                "other_expenses",
                "Other monthly expenses",
                facts.other_monthly_expenses_cents,
                "user_provided",
                "Childcare, transport, groceries and the like, as you entered them.",
            )
        )
        committed += facts.other_monthly_expenses_cents

    if facts.monthly_net_income_cents is not None:
        lines.append(
            PersonalLine(
                "remaining_income",
                "Estimated remaining income (after tax)",
                facts.monthly_net_income_cents - committed,
                "user_provided",
                "Your take-home pay minus the costs above. Based on the information you provided.",
            )
        )
    else:
        lines.append(
            PersonalLine(
                "remaining_income",
                "Estimated remaining income (before tax)",
                gross_monthly - committed,
                "estimated",
                "Gross income minus the costs above. Income tax is not deducted here, so "
                "your real remaining income is lower — enter your monthly take-home pay "
                "for a closer figure.",
            )
        )

    lines.append(
        PersonalLine(
            "cash_required",
            "Cash required upfront",
            facts.cash_required_cents,
            "estimated",
            "Down payment plus estimated closing costs.",
        )
    )
    lines.append(
        PersonalLine(
            "remaining_savings",
            "Estimated remaining savings after closing",
            facts.available_savings_cents - facts.cash_required_cents,
            "estimated",
            "Savings you entered minus the cash required. Negative means a shortfall.",
        )
    )

    share = (
        (Decimal(facts.monthly_housing_cost_cents) / Decimal(gross_monthly)).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        if gross_monthly
        else Decimal(0)
    )
    monthly_obligations = facts.monthly_housing_cost_cents + facts.monthly_debt_payments_cents
    months = (
        (Decimal(facts.emergency_fund_cents) / Decimal(monthly_obligations)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        if monthly_obligations > 0
        else None
    )
    return PersonalFit(lines=tuple(lines), housing_share_of_gross=share, emergency_months=months)
