"""Saved analyses and everything derived from them: Deep Dive, offers, comparison.

None of these consume an analysis credit. They re-run the deterministic engines
over a request the user already paid for (in credits or money), which costs a few
milliseconds and no external calls — so they are rate-limited, not metered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, DbSession
from app.billing.config import FeatureFlags, PricingConfig, ProjectionConfig
from app.core.crypto import decrypt_json
from app.engines.scenarios.comparison import ComparisonInput, compare
from app.models.account import PropertyWatch, Report, UsageEvent
from app.models.analysis import PropertyAnalysis, PropertyComparison
from app.models.user import User
from app.schemas.analysis import AnalyzeRequest
from app.services import accounts, settings_store
from app.services.scenario_service import ScenarioService

router = APIRouter(prefix="/api/v1")

DERIVED_PER_HOUR = 120


def _scenarios() -> ScenarioService:
    # Imported lazily: routes.py owns the shared service and its rule set.
    from app.api.v1.routes import SERVICE

    return ScenarioService(SERVICE)


async def load_analysis(db: AsyncSession, user: User, analysis_id: str) -> PropertyAnalysis:
    """The caller's own analysis, or an admin's view of anyone's. 404 otherwise."""
    try:
        key = uuid.UUID(analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Analysis not found.") from exc
    row = await db.get(PropertyAnalysis, key)
    if row is None or (row.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Analysis not found.")
    if row.request_encrypted is None or row.result_encrypted is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return row


def stored_request(row: PropertyAnalysis) -> AnalyzeRequest:
    assert row.request_encrypted is not None
    return AnalyzeRequest.model_validate(decrypt_json(row.request_encrypted))


def stored_result(row: PropertyAnalysis) -> dict[str, Any]:
    assert row.result_encrypted is not None
    result: dict[str, Any] = decrypt_json(row.result_encrypted)
    return result


async def _derived_allowance(db: AsyncSession, user: User, kind: str) -> None:
    if user.role == "admin":
        return
    used = await db.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.user_id == user.id,
            UsageEvent.kind == kind,
            UsageEvent.at >= datetime.now(UTC) - timedelta(hours=1),
        )
    )
    if (used or 0) >= DERIVED_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")


async def _deep_dive_unlocked(db: AsyncSession, user: User, row: PropertyAnalysis) -> bool:
    if user.role == "admin":
        return True
    existing = await db.scalar(
        select(Report.id).where(
            Report.user_id == user.id,
            Report.analysis_id == row.id,
            Report.kind == "deep_dive",
        )
    )
    return existing is not None


@router.get("/analyses")
async def list_analyses(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(PropertyAnalysis)
            .where(PropertyAnalysis.user_id == user.id)
            .order_by(PropertyAnalysis.created_at.desc())
            .limit(200)
        )
    ).all()
    unlocked = set(
        (
            await db.scalars(
                select(Report.analysis_id).where(
                    Report.user_id == user.id, Report.kind == "deep_dive"
                )
            )
        ).all()
    )
    watched = set(
        (
            await db.scalars(
                select(PropertyWatch.current_analysis_id).where(PropertyWatch.user_id == user.id)
            )
        ).all()
    )
    ent = await accounts.entitlements_for(db, user)
    return {
        "analyses": [
            {
                "id": str(r.id),
                "title": r.title,
                "created_at": r.created_at.isoformat(),
                "buy_score": r.buy_score,
                "purchase_price_cents": r.purchase_price_cents,
                "monthly_ownership_cost_cents": r.monthly_ownership_cost_cents,
                "cash_required_cents": r.cash_required_cents,
                "closing_costs_cents": r.closing_costs_cents,
                "credit_source": r.credit_source,
                "derived_from_id": str(r.derived_from_id) if r.derived_from_id else None,
                "deep_dive_unlocked": r.id in unlocked or ent.deep_dive_included,
                "watched": r.id in watched,
            }
            for r in rows
        ],
        "usage": accounts.usage_summary(ent),
    }


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    row = await load_analysis(db, user, analysis_id)
    ent = await accounts.entitlements_for(db, user)
    result = stored_result(row)
    result.update(
        {
            "analysis_id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "duplicate": False,
            "usage": accounts.usage_summary(ent),
            "title": row.title,
            "deep_dive_unlocked": ent.deep_dive_included
            or await _deep_dive_unlocked(db, user, row),
            "request": stored_request(row).model_dump(mode="json"),
        }
    )
    return result


@router.get("/analyses/{analysis_id}/deep-dive")
async def deep_dive(analysis_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    features = await settings_store.load(db, "features", FeatureFlags)
    if not features.deep_dive:
        raise HTTPException(status_code=403, detail="Deep Dive reports are not available.")
    row = await load_analysis(db, user, analysis_id)
    ent = await accounts.entitlements_for(db, user)

    if not await _deep_dive_unlocked(db, user, row):
        if ent.deep_dive_included:
            # Included in the plan: record the unlock so it survives a later downgrade.
            db.add(Report(user_id=user.id, analysis_id=row.id, source="plan"))
            await db.commit()
        else:
            pricing = await settings_store.load(db, "pricing", PricingConfig)
            product = pricing.product("deep_dive")
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "deep_dive_locked",
                    "message": "The Deep Dive for this property is not unlocked yet.",
                    "price_cents": product.price_cents if product else None,
                    "currency": pricing.currency,
                },
            )

    config = await settings_store.load(db, "projection", ProjectionConfig)
    report = _scenarios().deep_dive(
        stored_request(row), stored_result(row), config, as_of=row.created_at.date()
    )
    report["analysis_id"] = str(row.id)
    return report


class OffersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prices_cents: list[int] = Field(min_length=1, max_length=6)
    down_payment_mode: Literal["same_amount", "same_percent"] = "same_amount"


@router.post("/analyses/{analysis_id}/offers")
async def offer_scenarios(
    analysis_id: str, body: OffersIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    features = await settings_store.load(db, "features", FeatureFlags)
    if not features.offer_scenarios:
        raise HTTPException(status_code=403, detail="Offer scenarios are not available.")
    if any(p <= 0 or p > 100_000_000_00 for p in body.prices_cents):
        raise HTTPException(status_code=422, detail="Each price must be positive.")
    row = await load_analysis(db, user, analysis_id)
    await _derived_allowance(db, user, "offer_scenarios")
    request = stored_request(row)
    rows = _scenarios().offers(
        request,
        sorted(set(body.prices_cents)),
        mode=body.down_payment_mode,
        as_of=datetime.now(UTC).date(),
    )
    db.add(UsageEvent(user_id=user.id, analysis_id=row.id, kind="offer_scenarios"))
    accounts.record_event(db, "offer_scenarios_run", user.id, {"count": len(rows)})
    await db.commit()
    return {
        "analysis_id": str(row.id),
        "asking_price_cents": request.property.purchase_price_cents,
        "contract_rate": float(request.terms.contract_rate),
        "down_payment_mode": body.down_payment_mode,
        "scenarios": rows,
        "note": "Each row is a full recalculation at that price. These are the financial "
        "consequences of each offer, not a recommendation of what to offer.",
    }


class ComparisonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_ids: list[str] = Field(min_length=2, max_length=5)


@router.post("/comparisons")
async def create_comparison(body: ComparisonIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    features = await settings_store.load(db, "features", FeatureFlags)
    if not features.comparison:
        raise HTTPException(status_code=403, detail="Comparison is not available.")
    ids = list(dict.fromkeys(body.analysis_ids))
    ent = await accounts.entitlements_for(db, user)
    if len(ids) < 2 or len(ids) > ent.compare_max:
        raise HTTPException(
            status_code=422, detail=f"Choose between 2 and {ent.compare_max} properties."
        )
    await _derived_allowance(db, user, "comparison")
    rows = [await load_analysis(db, user, i) for i in ids]
    config = await settings_store.load(db, "projection", ProjectionConfig)
    scenarios = _scenarios()

    columns: list[dict[str, Any]] = []
    inputs: list[ComparisonInput] = []
    for index, row in enumerate(rows):
        request = stored_request(row)
        result = stored_result(row)
        report = scenarios.deep_dive(request, result, config, as_of=row.created_at.date())
        horizons = {h["years"]: h for h in report["projection"]["horizons"]}
        ten = horizons[10]
        outcomes = ten["outcomes"]
        no_growth = next(o for o in outcomes if float(o["rate"]) == 0)
        mid = outcomes[len(outcomes) // 2]
        label = f"{chr(65 + index)}: {row.title or 'Property'}"[:80]
        missing = result.get("missing_info", [])
        summary = report["summary"]
        column = {
            "analysis_id": str(row.id),
            "label": label,
            "title": row.title,
            "buy_score": row.buy_score,
            "purchase_price_cents": summary["purchase_price_cents"],
            "down_payment_cents": summary["down_payment_cents"],
            "mortgage_principal_cents": summary["mortgage_principal_cents"],
            "monthly_payment_cents": summary["monthly_payment_cents"],
            "monthly_property_tax_cents": report["property_tax"]["monthly_cents"],
            "property_tax_basis": report["property_tax"]["basis"],
            "monthly_condo_fee_cents": report["condo_fee"]["monthly_cents"],
            "condo_fee_basis": report["condo_fee"]["basis"]
            if report["condo_fee"]["applies"]
            else "not_applicable",
            "monthly_insurance_cents": report["insurance"]["monthly_cents"],
            "monthly_maintenance_cents": report["maintenance"]["monthly_cents"],
            "monthly_carrying_cost_cents": summary["monthly_carrying_cost_cents"],
            "closing_costs_cents": summary["closing_costs_cents"],
            "cash_required_cents": summary["cash_required_cents"],
            "five_year_outlay_cents": horizons[5]["total_outlay_cents"],
            "ten_year_outlay_cents": ten["total_outlay_cents"],
            "ten_year_equity": [
                {"rate": float(o["rate"]), "equity_after_sale_cents": o["equity_after_sale_cents"]}
                for o in outcomes
            ],
            "risks": result.get("risks", []),
            "negative_factors": [
                f["sentence"] for f in result.get("factors", {}).get("negative", [])
            ],
            "missing_info": [m["title"] for m in missing],
        }
        columns.append(column)
        inputs.append(
            ComparisonInput(
                label=label,
                purchase_price_cents=column["purchase_price_cents"],
                down_payment_cents=column["down_payment_cents"],
                mortgage_principal_cents=column["mortgage_principal_cents"],
                monthly_payment_cents=column["monthly_payment_cents"],
                monthly_property_tax_cents=column["monthly_property_tax_cents"],
                monthly_condo_fee_cents=column["monthly_condo_fee_cents"],
                monthly_insurance_cents=column["monthly_insurance_cents"],
                monthly_maintenance_cents=column["monthly_maintenance_cents"],
                monthly_carrying_cost_cents=column["monthly_carrying_cost_cents"],
                closing_costs_cents=column["closing_costs_cents"],
                cash_required_cents=column["cash_required_cents"],
                five_year_outlay_cents=column["five_year_outlay_cents"],
                ten_year_outlay_cents=column["ten_year_outlay_cents"],
                ten_year_equity_no_growth_cents=no_growth["equity_after_sale_cents"],
                ten_year_equity_mid_growth_cents=mid["equity_after_sale_cents"],
                risk_count=len(column["risks"]),
                missing_count=len(missing),
                high_priority_missing=sum(1 for m in missing if m["severity"] == "high"),
            )
        )

    outcome = compare(inputs)
    db.add(PropertyComparison(user_id=user.id, analysis_ids=ids))
    db.add(UsageEvent(user_id=user.id, kind="comparison"))
    accounts.record_event(db, "comparison_created", user.id, {"count": len(ids)})
    await db.commit()
    return {
        "columns": columns,
        "appreciation_rates": [float(r) for r in config.appreciation_rates],
        "differences": [
            {
                "metric": d.metric,
                "label": d.label,
                "lowest": d.lowest_label,
                "highest": d.highest_label,
                "spread_cents": d.spread_cents,
                "sentence": d.sentence,
            }
            for d in outcome.differences
        ],
        "trade_offs": list(outcome.trade_offs),
        "notes": list(outcome.notes),
    }
