"""What an engine returns, and why it is never just a number.

The brief's rule for the financial engine — "every calculation must have input,
formula, output, source, assumption, timestamp" — is not a documentation
request. It is the product: a user can open any figure and see the working, and
an auditor can check it without reading Python.

So engines return an :class:`EngineResult`, which is a value plus the trace that
produced it. The trace is built as the calculation runs rather than reconstructed
afterwards, because a reconstruction is a second implementation that can disagree
with the first.

Engines are pure. No session, no HTTP, no model call, no clock read that affects
the output. That is enforced by ``tests/unit/test_layering.py``, which fails the
build if anything under ``app/engines`` imports from services, repositories,
providers or ai.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.provenance.types import Fact


@dataclass(frozen=True, slots=True)
class Assumption:
    """A value we chose because the user did not supply one, and nothing verified it.

    Assumptions are surfaced in the UI beside the figure they affect. An
    assumption the user cannot see is indistinguishable, to them, from a fact we
    invented.
    """

    key: str
    value: Any
    rationale: str
    source_key: str | None = None


@dataclass(frozen=True, slots=True)
class CalculationStep:
    """One line of the working."""

    name: str
    formula: str
    """Human-readable, e.g. ``P * (r / (1 - (1 + r) ** -n))``. Printed, not evaluated."""

    inputs: dict[str, Any]
    output: Any
    unit: str | None = None
    rule_keys: tuple[str, ...] = ()
    """Which registry rules this step depended on, so a replay can prove the version."""


@dataclass(frozen=True, slots=True)
class EngineResult[T]:
    """A computed value, its working, and everything it could not determine."""

    value: T
    steps: tuple[CalculationStep, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    unavailable: tuple[Fact[Any], ...] = ()
    """Inputs we wanted and did not get. Each carries its own reason."""

    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    @property
    def is_complete(self) -> bool:
        """True when every input the engine wanted was available."""
        return not self.unavailable

    def explain(self) -> list[str]:
        """The working, as lines a person can read. What the UI's trace panel renders."""
        return [f"{step.name}: {step.formula} = {step.output}" for step in self.steps]


@dataclass(slots=True)
class TraceBuilder:
    """Accumulates the working while a calculation runs.

    Mutable by design and never shared across calls: an engine creates one,
    records as it goes, and freezes it into an :class:`EngineResult`.
    """

    steps: list[CalculationStep] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    unavailable: list[Fact[Any]] = field(default_factory=list)

    def step(
        self,
        name: str,
        formula: str,
        inputs: dict[str, Any],
        output: Any,
        *,
        unit: str | None = None,
        rule_keys: tuple[str, ...] = (),
    ) -> Any:
        """Record a step and return its output, so call sites read as ordinary assignments."""
        self.steps.append(
            CalculationStep(
                name=name,
                formula=formula,
                inputs=inputs,
                output=output,
                unit=unit,
                rule_keys=rule_keys,
            )
        )
        return output

    def assume(self, key: str, value: Any, rationale: str, *, source_key: str | None = None) -> Any:
        self.assumptions.append(
            Assumption(key=key, value=value, rationale=rationale, source_key=source_key)
        )
        return value

    def missing(self, fact: Fact[Any]) -> None:
        self.unavailable.append(fact)

    def finish[T](self, value: T, *, confidence: float = 1.0) -> EngineResult[T]:
        return EngineResult(
            value=value,
            steps=tuple(self.steps),
            assumptions=tuple(self.assumptions),
            unavailable=tuple(self.unavailable),
            confidence=confidence,
        )
