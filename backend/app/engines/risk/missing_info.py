"""Things to investigate before making an offer.

Every item here is derived from what the analysis was *not* given, or could only
assume. Nothing is invented: an item never says the roof is old, only that its age
is unknown and why that matters for a house built when this one was. The output
is a checklist of questions, which is the honest thing to do with an absence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["high", "medium", "low"]

_CONDOS = frozenset({"condo_apartment", "condo_town"})
_FREEHOLD = frozenset({"detached", "semi", "townhouse", "duplex"})


@dataclass(frozen=True, slots=True)
class MissingInfoInput:
    property_kind: str
    annual_property_tax_supplied: bool
    property_tax_estimated: bool
    """True when the tax was estimated from a municipal rate rather than supplied."""

    monthly_condo_fee_supplied: bool
    year_built: int | None
    as_of_year: int
    square_feet: int | None
    bedrooms: int | None
    address_supplied: bool
    comparables_included: int
    is_new_build: bool = False


@dataclass(frozen=True, slots=True)
class MissingItem:
    key: str
    title: str
    why_it_matters: str
    what_to_ask_for: str
    severity: Severity
    category: str


def missing_information(facts: MissingInfoInput) -> list[MissingItem]:
    items: list[MissingItem] = []
    is_condo = facts.property_kind in _CONDOS
    age = facts.as_of_year - facts.year_built if facts.year_built else None

    if not facts.annual_property_tax_supplied:
        items.append(
            MissingItem(
                key="property_tax",
                title="Property taxes not confirmed"
                if facts.property_tax_estimated
                else "Property taxes unavailable",
                why_it_matters=(
                    "Property tax is part of your monthly cost and part of the debt-service "
                    "ratios a lender checks. "
                    + (
                        "The figure used here is estimated from the municipal rate applied "
                        "to the price, which can differ from the real bill by thousands."
                        if facts.property_tax_estimated
                        else "No rate is published for this municipality, so the monthly "
                        "cost shown excludes it."
                    )
                ),
                what_to_ask_for="The most recent final property tax bill and the MPAC "
                "assessed value.",
                severity="high" if not facts.property_tax_estimated else "medium",
                category="costs",
            )
        )

    if is_condo:
        if not facts.monthly_condo_fee_supplied:
            items.append(
                MissingItem(
                    key="condo_fee",
                    title="Condo fees unavailable",
                    why_it_matters="Condo fees depend on the building, not the price, and are "
                    "often several hundred dollars a month. The monthly cost shown excludes them.",
                    what_to_ask_for="The current monthly fee, what it includes (heat, hydro, "
                    "water, parking, locker) and the history of increases.",
                    severity="high",
                    category="costs",
                )
            )
        items.append(
            MissingItem(
                key="status_certificate",
                title="Status certificate not reviewed",
                why_it_matters="In Ontario the status certificate discloses the reserve fund, "
                "any special assessments, planned fee increases and legal actions against the "
                "corporation — the things most likely to change what the unit really costs.",
                what_to_ask_for="The status certificate, reviewed by your lawyer before your "
                "offer becomes firm (commonly a condition of the offer).",
                severity="high",
                category="condo",
            )
        )
        items.append(
            MissingItem(
                key="reserve_fund",
                title="Condo reserve fund information unavailable",
                why_it_matters="An underfunded reserve fund is how owners end up paying a "
                "special assessment for a roof, garage or elevator replacement.",
                what_to_ask_for="The latest reserve fund study and the current balance "
                "against its recommended level.",
                severity="medium",
                category="condo",
            )
        )

    if facts.property_kind in _FREEHOLD and not facts.is_new_build:
        roof_severity: Severity = "medium" if age is None or age >= 15 else "low"
        items.append(
            MissingItem(
                key="roof_age",
                title="Roof age unknown",
                why_it_matters="Asphalt shingles typically last 15–25 years; a replacement is "
                "a five-figure cost that is not in the monthly figures above."
                + (f" This house is about {age} years old." if age else ""),
                what_to_ask_for="The year the roof was last replaced, with an invoice if "
                "available.",
                severity=roof_severity,
                category="condition",
            )
        )
        items.append(
            MissingItem(
                key="hvac_age",
                title="Age of furnace and air conditioning unknown",
                why_it_matters="Furnaces and air conditioners commonly last 15–20 years, and "
                "some are rented rather than owned — a rental contract transfers to you.",
                what_to_ask_for="Install dates for the furnace, AC and water heater, and "
                "whether any are rented.",
                severity="medium",
                category="condition",
            )
        )

    if age is not None and age >= 50:
        items.append(
            MissingItem(
                key="electrical_plumbing",
                title="Electrical and plumbing updates unknown",
                why_it_matters="Houses of this age can have knob-and-tube wiring, aluminum "
                "wiring or galvanized pipes, which some insurers decline or surcharge.",
                what_to_ask_for="Whether the wiring and supply pipes have been updated, and "
                "an insurance quote before the offer is firm.",
                severity="medium",
                category="condition",
            )
        )

    if not facts.is_new_build:
        items.append(
            MissingItem(
                key="renovations",
                title="Recent renovations unclear",
                why_it_matters="Unpermitted work can be a safety issue, can affect insurance, "
                "and may need to be corrected at your cost.",
                what_to_ask_for="A list of renovations with dates, and whether permits were "
                "pulled and closed (the municipality can confirm open permits).",
                severity="low",
                category="condition",
            )
        )

    if facts.year_built is None:
        items.append(
            MissingItem(
                key="year_built",
                title="Year built not provided",
                why_it_matters="Age drives the likely condition of the roof, mechanicals and "
                "wiring, and it feeds the property-quality score.",
                what_to_ask_for="The year built from the listing or the seller.",
                severity="low",
                category="listing",
            )
        )
    if facts.square_feet is None or facts.bedrooms is None:
        items.append(
            MissingItem(
                key="listing_incomplete",
                title="Listing information incomplete",
                why_it_matters="Size and bedroom count are what comparable sales are adjusted "
                "on; without them the value range is wider and less useful.",
                what_to_ask_for="Finished square footage (and how it was measured) and the "
                "bedroom count.",
                severity="low",
                category="listing",
            )
        )

    if facts.comparables_included < 3:
        items.append(
            MissingItem(
                key="comparables",
                title="Comparable sales insufficient",
                why_it_matters="With fewer than three recent similar sales the value range "
                "falls back toward the asking price and says little about whether it is fair.",
                what_to_ask_for="Recent sold prices for similar homes nearby — your agent can "
                "pull these from the MLS.",
                severity="medium",
                category="value",
            )
        )

    items.append(
        MissingItem(
            key="utilities",
            title="Utility costs unavailable",
            why_it_matters="Utilities are included at a planning default, not this home's "
            "actual usage, which varies with size, insulation and heating type.",
            what_to_ask_for="Twelve months of hydro, gas and water bills.",
            severity="low",
            category="costs",
        )
    )
    items.append(
        MissingItem(
            key="insurance",
            title="Home insurance not quoted",
            why_it_matters="Insurance is included at a planning default. Age, wiring, "
            "flood history and claims can change the premium or availability.",
            what_to_ask_for="A quote for this specific address before your offer is firm.",
            severity="low",
            category="costs",
        )
    )

    if not facts.address_supplied:
        items.append(
            MissingItem(
                key="address",
                title="Address not provided",
                why_it_matters="Without the address, commute and location could not be checked.",
                what_to_ask_for="Enter the property address to measure the commute.",
                severity="low",
                category="listing",
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda item: order[item.severity])
