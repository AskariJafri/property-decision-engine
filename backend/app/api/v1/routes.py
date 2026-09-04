"""API routes. Thin: validate, call a service, serialize.

``/reference/rules`` exists because the product's promise is auditability — a user
can read the exact bracket table that produced their land transfer tax, with the
source URL and the date it took effect.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.engines.financial.rules_seed import default_rule_set
from app.engines.scoring.contracts import SCORING_MODEL_VERSION
from app.provenance.policy import REGISTRY
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/v1")

JURISDICTION = Query(default="ON/Toronto")
AS_OF = Query(default=None)
RULES = default_rule_set()
SERVICE = AnalysisService(RULES)


@router.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "pilot_jurisdiction": settings.pilot_jurisdiction,
        "scoring_model_version": SCORING_MODEL_VERSION,
        "rule_set": RULES.label,
    }


@router.post("/properties/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run one complete analysis.

    Input errors that the engines refuse — a down payment below the statutory
    minimum, for instance — come back as 422 with the engine's own sentence, which
    is more useful to a buyer than a generic validation message.
    """
    try:
        return SERVICE.analyze(request, as_of=datetime.now(UTC).date())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reference/rules")
async def reference_rules(
    jurisdiction: str = JURISDICTION,
    as_of: date | None = AS_OF,
) -> dict[str, Any]:
    """Every rule in force for a jurisdiction on a date, with its source."""
    when = as_of or datetime.now(UTC).date()
    resolved = []
    for name in sorted({rule.name for rule in RULES.rules}):
        rule = RULES.find(jurisdiction, name, as_of=when)
        if rule is None:
            continue
        resolved.append(
            {
                "jurisdiction": rule.jurisdiction,
                "name": rule.name,
                "value": rule.value,
                "effective_from": rule.effective_from.isoformat(),
                "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
                "source_url": rule.source_url,
                "verification": rule.verification.value,
                "version": rule.version,
                "note": rule.note,
            }
        )
    inactive = [
        {
            "jurisdiction": rule.jurisdiction,
            "name": rule.name,
            "reason": rule.note,
            "verification": rule.verification.value,
        }
        for rule in RULES.rules
        if not rule.active
    ]
    return {
        "rule_set": RULES.label,
        "jurisdiction": jurisdiction,
        "as_of": when.isoformat(),
        "rules": resolved,
        "excluded_unverified": inactive,
    }


@router.get("/reference/sources")
async def reference_sources() -> dict[str, Any]:
    """The licence register, for the UI's attribution block."""
    return {
        "sources": [
            {
                "key": policy.key,
                "name": policy.name,
                "licence_class": policy.licence_class.value,
                "may_store_values": policy.may_store_values,
                "max_retention_days": policy.max_retention_days,
                "attribution": policy.attribution,
                "source_url": policy.source_url,
                "notes": policy.notes,
            }
            for policy in REGISTRY.values()
        ]
    }
