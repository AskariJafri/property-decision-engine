"""API routes. Thin: validate, call a service, serialize.

``/reference/rules`` exists because the product's promise is auditability — a user
can read the exact bracket table that produced their land transfer tax, with the
source URL and the date it took effect.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select

from app.ai.contracts import LlmUnavailableError
from app.ai.explainer import NumericGuardError, explain
from app.ai.provider import OpenAICompatibleProvider
from app.auth.deps import CurrentUser, DbSession
from app.billing.config import CostAssumptions, FeatureFlags
from app.core.config import get_settings
from app.core.crypto import decrypt_json, encrypt_json
from app.engines.financial.rules_seed import default_rule_set
from app.engines.scoring.contracts import SCORING_MODEL_VERSION
from app.ingestion.deterministic import parse as parse_listing_text
from app.ingestion.documents import UnsupportedDocumentError, extract_text
from app.models.account import ApiUsage, UsageEvent
from app.models.analysis import PropertyAnalysis
from app.models.user import User
from app.provenance.policy import REGISTRY
from app.providers.openrouteservice import OpenRouteServiceProvider
from app.providers.osm import NominatimGeocoder, OsrmRouter
from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    ExplanationOut,
    ParseListingRequest,
    ParseListingResponse,
)
from app.services import accounts, settings_store
from app.services.analysis_service import AnalysisService, LocationFacts, inputs_hash_for
from app.services.scenario_service import title_for

router = APIRouter(prefix="/api/v1")

JURISDICTION = Query(default="ON/Toronto")
UPLOADED_FILE = File(...)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AS_OF = Query(default=None)
RULES = default_rule_set()
SERVICE = AnalysisService(RULES)


# GET and HEAD both: uptime monitors, load balancers and wait-on probe with
# HEAD, and a health check that answers 405 reads as "unhealthy" to every one
# of them. This cost two CI runs to a service that was up the whole time.
@router.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "pilot_jurisdiction": settings.pilot_jurisdiction,
        "scoring_model_version": SCORING_MODEL_VERSION,
        "rule_set": RULES.label,
        # Configured, which is not the same as reachable: these say a key or URL
        # reached the process, not that the service answers. Reachability is
        # discovered at call time and degrades into the analysis with a reason.
        "providers_configured": {
            "openrouteservice": bool(settings.ors_api_key),
            "nominatim": bool(settings.nominatim_url),
            "routing": bool(settings.routing_url),
            "overpass": bool(settings.overpass_url),
        },
        # Reported separately from the providers above, and deliberately not as
        # a "configured" flag. llm_base_url has a non-empty default, so bool(...)
        # on it was true on every deployment that had never seen a model, and
        # read as "AI is on" while nothing called a model at all.
        #
        # This is the explicit switch instead. Still not a promise of
        # reachability: with it on and the model down, the analysis renders in
        # full and says why the prose is missing. The figures never depend on it.
        "ai_explanations_enabled": settings.llm_explanations_enabled,
    }


#: Metered actions with no credit cost still have a ceiling, so a script cannot
#: turn a free derived view into an unmetered engine.
DUPLICATE_WINDOW = timedelta(hours=24)


@router.post("/properties/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, user: CurrentUser, db: DbSession) -> AnalyzeResponse:
    """Run one complete analysis, and meter it.

    The credit is checked before any work, checked again under a row lock after
    the work, and drawn from the ledger in the same transaction that saves the
    result — so two tabs racing for the last free analysis get one analysis
    between them, and an analysis that fails consumes nothing.

    Input errors that the engines refuse — a down payment below the statutory
    minimum, for instance — come back as 422 with the engine's own sentence, which
    is more useful to a buyer than a generic validation message.
    """
    now = datetime.now(UTC)
    settings = get_settings()
    ent = await accounts.entitlements_for(db, user, now)

    # The same inputs again within a day: hand back what was already computed.
    fingerprint = inputs_hash_for(request, RULES.label, SCORING_MODEL_VERSION)
    previous = await db.scalar(
        select(PropertyAnalysis)
        .where(
            PropertyAnalysis.user_id == user.id,
            PropertyAnalysis.inputs_hash == fingerprint,
            PropertyAnalysis.derived_from_id.is_(None),
            PropertyAnalysis.created_at >= now - DUPLICATE_WINDOW,
        )
        .order_by(PropertyAnalysis.created_at.desc())
        .limit(1)
    )
    if previous is not None and previous.result_encrypted:
        saved = AnalyzeResponse.model_validate(decrypt_json(previous.result_encrypted))
        saved.analysis_id = str(previous.id)
        saved.created_at = previous.created_at.isoformat()
        saved.duplicate = True
        saved.usage = accounts.usage_summary(ent)
        return saved

    if not ent.can_analyze:
        accounts.record_event(db, "free_limit_reached", user.id)
        await db.commit()
        raise HTTPException(status_code=402, detail=_limit_detail(ent))

    if not ent.unlimited:
        recent = await db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.user_id == user.id,
                UsageEvent.kind == "analysis",
                UsageEvent.at >= now - timedelta(hours=1),
            )
        )
        if (recent or 0) >= settings.analysis_rate_limit_per_hour:
            raise HTTPException(
                status_code=429,
                detail="That is a lot of analyses in an hour. Wait a little and try again.",
            )

    location = await _resolve_location(request)
    await _record_location_usage(db, user, location)
    try:
        analysis = SERVICE.analyze(request, as_of=now.date(), location=location)
    except ValueError as exc:
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    analysis.explanation, analysis.explanation_unavailable_reason = await _explain_metered(
        db, user, analysis
    )

    # Re-check under a lock: the credit is spent here, not at the top.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    ent = await accounts.entitlements_for(db, user, now)
    source = ent.next_credit_source
    if source is None:
        await db.commit()
        raise HTTPException(status_code=402, detail=_limit_detail(ent))

    row = _analysis_row(user, request, analysis, fingerprint, now, source)
    db.add(row)
    await db.flush()
    db.add(
        UsageEvent(
            user_id=user.id,
            analysis_id=row.id,
            kind="analysis",
            credit_source=source,
            credits=1 if source in ("free", "plan") else 0,
            at=now,
        )
    )
    accounts.record_event(db, "analysis_completed", user.id, {"credit_source": source})
    if source == "free":
        accounts.record_event(
            db, "free_analysis_used", user.id, {"remaining": max(0, ent.free_remaining - 1)}
        )
    await db.commit()

    analysis.analysis_id = str(row.id)
    analysis.created_at = now.isoformat()
    analysis.usage = accounts.usage_summary(await accounts.entitlements_for(db, user))
    return analysis


def _limit_detail(ent: Any) -> dict[str, Any]:
    exhausted_plan = ent.plan_key is not None
    return {
        "code": "limit_reached",
        "message": (
            "You've used this month's analyses on your plan."
            if exhausted_plan
            else f"You've used your {ent.free_total} free property analyses."
        ),
        "usage": accounts.usage_summary(ent),
    }


def _analysis_row(
    user: User,
    request: AnalyzeRequest,
    analysis: AnalyzeResponse,
    fingerprint: str,
    now: datetime,
    source: str,
    *,
    derived_from: Any = None,
) -> PropertyAnalysis:
    stored = analysis.model_dump(
        mode="json", exclude={"usage", "analysis_id", "duplicate", "created_at"}
    )
    return PropertyAnalysis(
        user_id=user.id,
        scoring_model_version=analysis.scoring_model_version,
        buy_score=analysis.buy_score,
        score_withheld_reason=analysis.score_withheld_reason,
        confidence=Decimal(str(round(analysis.confidence, 3))),
        weights_applied={s.component: s.effective_weight for s in analysis.scores},
        inputs_hash=fingerprint,
        fair_value_low_cents=analysis.fair_value.low_cents,
        fair_value_high_cents=analysis.fair_value.high_cents,
        monthly_ownership_cost_cents=analysis.money.monthly_ownership_cost_cents,
        closing_costs_cents=analysis.money.closing_costs_cents,
        cash_required_cents=analysis.money.cash_required_cents,
        created_at=now,
        rule_set_label=analysis.rule_set,
        title=title_for(request)[:400],
        purchase_price_cents=request.property.purchase_price_cents,
        request_encrypted=encrypt_json(request.model_dump(mode="json")),
        result_encrypted=encrypt_json(stored),
        credit_consumed=source in ("free", "plan"),
        credit_source=source,
        derived_from_id=derived_from,
    )


def _millicents(cents_value: Decimal) -> int:
    return int((cents_value * 1000).to_integral_value())


async def _record_location_usage(db: Any, user: User, location: LocationFacts) -> None:
    settings = get_settings()
    configured = bool(settings.ors_api_key or (settings.nominatim_url and settings.routing_url))
    if not configured:
        return
    costs = await settings_store.load(db, "costs", CostAssumptions)
    db.add(
        ApiUsage(
            user_id=user.id,
            provider="openrouteservice" if settings.ors_api_key else "osm",
            operation="commute",
            ok=location.commute_minutes is not None,
            estimated_cost_millicents=_millicents(costs.location_cost_per_call_cents),
        )
    )


async def _explain_metered(
    db: Any, user: User, analysis: AnalyzeResponse
) -> tuple[ExplanationOut | None, str | None]:
    """The explanation, subject to the admin switch and the daily AI budget."""
    settings = get_settings()
    if not settings.llm_explanations_enabled:
        explanation, reason, _ = await _explain(analysis)
        return explanation, reason

    features = await settings_store.load(db, "features", FeatureFlags)
    if not features.ai_explanations:
        return None, (
            "Explanations are switched off by the administrator. The analysis above is "
            "computed deterministically and is unaffected."
        )
    costs = await settings_store.load(db, "costs", CostAssumptions)
    if settings.ai_daily_budget_cents > 0:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = await db.scalar(
            select(func.coalesce(func.sum(ApiUsage.estimated_cost_millicents), 0)).where(
                ApiUsage.provider == "llm", ApiUsage.at >= start
            )
        )
        if int(spent or 0) >= settings.ai_daily_budget_cents * 1000:
            return None, (
                "Explanations are paused for the rest of today to keep costs in check. The "
                "analysis above is unaffected."
            )

    started = time.monotonic()
    explanation, reason, tokens = await _explain(analysis)
    input_tokens, output_tokens = tokens or (None, None)
    if input_tokens is not None or output_tokens is not None:
        cost = (
            Decimal(input_tokens or 0) * costs.ai_input_cost_per_million_tokens_cents
            + Decimal(output_tokens or 0) * costs.ai_output_cost_per_million_tokens_cents
        ) / Decimal(1_000_000)
    else:
        cost = costs.ai_cost_per_call_cents
    db.add(
        ApiUsage(
            user_id=user.id,
            provider="llm",
            operation="explanation",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_millicents=_millicents(cost),
            ok=explanation is not None,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    )
    return explanation, reason


async def _explain(
    analysis: AnalyzeResponse,
) -> tuple[ExplanationOut | None, str | None, tuple[int | None, int | None] | None]:
    """Narrate a finished analysis, or say why there is no narration.

    Deliberately the last step, over a completed result. The model sees numbers
    that already exist and cannot influence them: it is handed the analysis, not
    consulted during it (ADR 0004). Every failure returns a reason instead of
    raising, because prose is the least important thing on the page and must
    never be able to take the figures down with it.
    """
    settings = get_settings()
    if not settings.llm_explanations_enabled:
        return (
            None,
            (
                "Explanations are turned off for this deployment. The analysis above is "
                "computed deterministically and is unaffected."
            ),
            None,
        )

    provider = OpenAICompatibleProvider(settings)

    def tokens() -> tuple[int | None, int | None] | None:
        usage = getattr(provider, "last_usage", None)
        if not isinstance(usage, dict):
            return None
        return usage.get("prompt_tokens"), usage.get("completion_tokens")

    try:
        explanation = await explain(analysis.model_dump(mode="json"), provider)
    except NumericGuardError as exc:
        # The interesting failure, and the reason the guard exists: the model
        # produced a figure nobody gave it. Discarded whole rather than repaired.
        return None, str(exc), tokens()
    except LlmUnavailableError as exc:
        return None, f"No explanation was produced: {exc}", tokens()
    except Exception as exc:  # prose must never break an analysis
        logging.getLogger(__name__).warning("Explanation failed unexpectedly: %s", exc)
        return None, "No explanation was produced: the model failed unexpectedly.", tokens()

    return (
        ExplanationOut(
            summary=explanation.summary,
            pros=list(explanation.pros),
            cons=list(explanation.cons),
            questions=list(explanation.questions),
            what_would_change_this=list(explanation.what_would_change_this),
            model_id=explanation.model_id,
            numeric_guard_passed=explanation.numeric_guard_passed,
        ),
        None,
        tokens(),
    )


async def _resolve_location(request: AnalyzeRequest) -> LocationFacts:
    """Geocode both addresses and route between them.

    Every failure here is a degradation, never an error: a missing key, an
    unrecognised address or a routing outage produces a stated reason and an
    analysis that carries on without a Location score.
    """
    settings = get_settings()
    address = request.property.address
    work = request.preferences.work_address
    if not address or not work:
        return LocationFacts(
            unavailable_reason="Commute needs both the property address and your work "
            "address; one or both were not supplied."
        )

    # Self-hosted first: it is the production answer (ADR 0002), it has no quota,
    # and its licence lets us store what it returns. OpenRouteService is the
    # stopgap for anyone who has not built the box yet.
    if settings.nominatim_url and settings.routing_url:
        geocoder = NominatimGeocoder(settings.nominatim_url)
        home = await geocoder.geocode(address)
        office = await geocoder.geocode(work)
        if home.is_available and office.is_available:
            home_lat, home_lon = home.require()
            work_lat, work_lon = office.require()
            commute = await OsrmRouter(settings.routing_url).travel_minutes(
                from_lat=home_lat,
                from_lon=home_lon,
                to_lat=work_lat,
                to_lon=work_lon,
                mode=request.preferences.commute_mode,
            )
            if commute.is_available:
                return LocationFacts(commute_minutes=commute.require())
        # Configured but not answering: fall through to ORS rather than give up.

    provider = OpenRouteServiceProvider(settings.ors_api_key, settings.ors_base_url)
    if not provider.configured:
        return LocationFacts(
            unavailable_reason="Commute could not be measured: the self-hosted routing "
            "services are not reachable and no OpenRouteService key is configured. Get "
            "a free key at https://openrouteservice.org/dev/#/signup and set "
            "PDE_ORS_API_KEY in .env."
        )

    home = await provider.geocode(address)
    if not home.is_available:
        return LocationFacts(unavailable_reason=home.provenance.unavailable_reason)
    office = await provider.geocode(work)
    if not office.is_available:
        return LocationFacts(unavailable_reason=office.provenance.unavailable_reason)

    home_lat, home_lon = home.require()
    work_lat, work_lon = office.require()
    mode = request.preferences.commute_mode
    commute = await provider.commute(
        from_lat=home_lat,
        from_lon=home_lon,
        to_lat=work_lat,
        to_lon=work_lon,
        mode=mode,
    )
    if not commute.is_available:
        return LocationFacts(unavailable_reason=commute.provenance.unavailable_reason)

    return LocationFacts(
        commute_minutes=commute.require(),
        commute_is_estimated=mode == "transit",
    )


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


async def _parse_allowance(db: Any, user: User) -> None:
    """Listing reads are cheap today, but they are the path a model will join."""
    if user.role == "admin":
        return
    since = datetime.now(UTC) - timedelta(days=1)
    used = await db.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.user_id == user.id,
            UsageEvent.kind == "listing_parse",
            UsageEvent.at >= since,
        )
    )
    if (used or 0) >= get_settings().listing_parse_rate_limit_per_day:
        raise HTTPException(
            status_code=429,
            detail="You have read a lot of listings today. Enter the details manually, or "
            "try again tomorrow.",
        )
    db.add(UsageEvent(user_id=user.id, kind="listing_parse", credit_source="none", credits=0))
    await db.commit()


@router.post("/listings/parse", response_model=ParseListingResponse)
async def parse_listing(
    request: ParseListingRequest, user: CurrentUser, db: DbSession
) -> ParseListingResponse:
    """Read a listing the user pasted, and hand back a draft for them to confirm.

    There is deliberately no URL to fetch. REALTOR.ca and the consumer portals
    prohibit automated collection, and *Century 21 Canada v. Rogers*, 2011 BCSC
    1196 held those terms enforceable and the copying infringing (ADR 0002 §2). So
    the user pastes what they are already looking at, which produces the same data
    with none of the exposure.

    The deterministic pattern pass runs first and needs no model. Where it cannot
    reach, a local model can be configured to fill the gaps — and nothing from
    either path is stored until the user confirms it.
    """
    await _parse_allowance(db, user)
    result = parse_listing_text(request.text)
    found = len(result.fields)
    note = (
        f"Read {found} field{'s' if found != 1 else ''} from the text you pasted. "
        "Check each one against the source shown beside it before analysing — this "
        "is a draft, not a fact."
        if found
        else "Nothing recognisable was found in that text. Enter the details manually."
    )
    return ParseListingResponse(
        fields=result.fields,
        fields_as_cents=result.as_cents(),
        evidence=result.evidence,
        rejected=result.rejected,
        read_by=result.model_id,
        requires_confirmation=True,
        note=note,
    )


@router.post("/listings/parse-document", response_model=ParseListingResponse)
async def parse_listing_document(
    user: CurrentUser, db: DbSession, file: UploadFile = UPLOADED_FILE
) -> ParseListingResponse:
    """Read a listing from a document the user saved.

    The intended flow is: open the listing in your own browser, print it to PDF,
    upload the file. You viewed a page you were entitled to view and saved what
    you saw — no automated retrieval, and the text layer a browser writes is
    exact rather than inferred.
    """
    await _parse_allowance(db, user)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        text = extract_text(content, file.content_type or "", filename=file.filename or "")
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = parse_listing_text(text)
    found = len(result.fields)
    note = (
        f"Read {found} field{'s' if found != 1 else ''} from {file.filename or 'that file'}. "
        "Check each one against the source shown beside it before analysing — this is a "
        "draft, not a fact."
        if found
        else (
            f"Nothing recognisable was found in {file.filename or 'that file'}. The text "
            "came through, but none of it matched a field we read. Enter the details "
            "manually."
        )
    )
    return ParseListingResponse(
        fields=result.fields,
        fields_as_cents=result.as_cents(),
        evidence=result.evidence,
        rejected=result.rejected,
        read_by=f"{result.model_id} (from document)",
        requires_confirmation=True,
        note=note,
    )
