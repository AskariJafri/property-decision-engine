"""API routes. Thin: validate, call a service, serialize.

``/reference/rules`` exists because the product's promise is auditability — a user
can read the exact bracket table that produced their land transfer tax, with the
source URL and the date it took effect.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.core.config import get_settings
from app.engines.financial.rules_seed import default_rule_set
from app.engines.scoring.contracts import SCORING_MODEL_VERSION
from app.ingestion.deterministic import parse as parse_listing_text
from app.ingestion.documents import UnsupportedDocumentError, extract_text
from app.provenance.policy import REGISTRY
from app.providers.openrouteservice import OpenRouteServiceProvider
from app.providers.osm import NominatimGeocoder, OsrmRouter
from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    ParseListingRequest,
    ParseListingResponse,
)
from app.services.analysis_service import AnalysisService, LocationFacts

router = APIRouter(prefix="/api/v1")

JURISDICTION = Query(default="ON/Toronto")
UPLOADED_FILE = File(...)
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
            "local_model": bool(settings.llm_base_url),
        },
    }


@router.post("/properties/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run one complete analysis.

    Input errors that the engines refuse — a down payment below the statutory
    minimum, for instance — come back as 422 with the engine's own sentence, which
    is more useful to a buyer than a generic validation message.
    """
    location = await _resolve_location(request)
    try:
        return SERVICE.analyze(request, as_of=datetime.now(UTC).date(), location=location)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.post("/listings/parse", response_model=ParseListingResponse)
async def parse_listing(request: ParseListingRequest) -> ParseListingResponse:
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
async def parse_listing_document(file: UploadFile = UPLOADED_FILE) -> ParseListingResponse:
    """Read a listing from a document the user saved.

    The intended flow is: open the listing in your own browser, print it to PDF,
    upload the file. You viewed a page you were entitled to view and saved what
    you saw — no automated retrieval, and the text layer a browser writes is
    exact rather than inferred.
    """
    content = await file.read()
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
