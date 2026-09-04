"""The rule registry: mortgage, tax and program rules as dated data.

Toronto raised its municipal land transfer tax on high-value homes to 8.60% on
1 April 2026. Any product that hardcoded those brackets in 2025 is now quietly
wrong above $3M and nobody will notice until a buyer's lawyer does. That is the
failure mode this module exists to prevent.

Rules are resolved ``as_of`` a date and scoped by jurisdiction, so an analysis
run today picks up today's brackets, and an analysis replayed from March 2026
reproduces March's — which is what makes ``property_analyses.inputs_hash``
meaningful.

Two invariants, both enforced here and again as database CHECK constraints:

* a rule marked ``UNVERIFIED`` can never be active, because a number we could not
  confirm against its issuing authority must not reach a calculation someone
  spends money on;
* every rule carries the URL it came from, so the ``/reference/rules`` endpoint
  can show a user the bracket table that produced their tax and where it lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Protocol


class Verification(StrEnum):
    PRIMARY = "primary"
    """Verified against the issuing authority's own page."""

    SECONDARY = "secondary"
    """From a reputable industry source. Usable, flagged, re-verify on review."""

    UNVERIFIED = "unverified"
    """Encountered but unconfirmed. May never be active."""


@dataclass(frozen=True, slots=True)
class Rule:
    jurisdiction: str
    """``CA``, ``ON``, ``ON/Toronto``. Resolution walks from most to least specific."""

    name: str
    """``ltt.brackets``, ``mltt.brackets``, ``mqr.floor``, ``insured.max_price_cents``."""

    value: Any
    effective_from: date
    source_url: str
    verification: Verification
    version: int = 1
    effective_to: date | None = None
    active: bool = True
    note: str | None = None

    def __post_init__(self) -> None:
        if self.verification is Verification.UNVERIFIED and self.active:
            raise ValueError(
                f"{self.jurisdiction}/{self.name}: an unverified rule cannot be active"
            )
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError(f"{self.jurisdiction}/{self.name}: effective_to precedes _from")

    def applies_on(self, when: date) -> bool:
        if when < self.effective_from:
            return False
        return self.effective_to is None or when <= self.effective_to


class RuleNotFoundError(LookupError):
    """No active rule for this jurisdiction and date.

    Not always an error: outside Toronto there is no ``mltt.brackets``, and the
    closing-cost engine correctly charges provincial land transfer tax alone.
    Callers distinguish "no such rule here" from "we failed to load the rules".
    """


class RuleResolver(Protocol):
    """How engines read the registry. Pure — an in-memory snapshot, not a query."""

    def get(self, jurisdiction: str, name: str, *, as_of: date) -> Rule: ...

    def find(self, jurisdiction: str, name: str, *, as_of: date) -> Rule | None: ...


@dataclass(frozen=True, slots=True)
class RuleSet:
    """An immutable snapshot of the registry, stamped onto every analysis.

    Jurisdiction resolution is most-specific-first: a Toronto property looks for
    ``ON/Toronto``, then ``ON``, then ``CA``. That is how a single lookup for
    ``ltt.brackets`` finds the provincial table while ``mltt.brackets`` finds
    only the municipal one, with no special-casing in the engine.
    """

    label: str
    rules: tuple[Rule, ...]

    def _candidates(self, jurisdiction: str) -> list[str]:
        parts = jurisdiction.split("/")
        scopes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        return [*reversed(scopes), "CA"]

    def find(self, jurisdiction: str, name: str, *, as_of: date) -> Rule | None:
        for scope in self._candidates(jurisdiction):
            matches = [
                rule
                for rule in self.rules
                if rule.active
                and rule.jurisdiction == scope
                and rule.name == name
                and rule.applies_on(as_of)
            ]
            if matches:
                # Latest effective_from wins, then highest version — a correction
                # published later for the same date supersedes the earlier row.
                return max(matches, key=lambda r: (r.effective_from, r.version))
        return None

    def get(self, jurisdiction: str, name: str, *, as_of: date) -> Rule:
        rule = self.find(jurisdiction, name, as_of=as_of)
        if rule is None:
            raise RuleNotFoundError(f"no active rule {name!r} for {jurisdiction} as of {as_of}")
        return rule
