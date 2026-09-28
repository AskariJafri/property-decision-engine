"""Admin-editable configuration, read through its schema with a default behind it.

A key that has never been saved returns its model's defaults, so a fresh database
behaves exactly like the launch configuration and nothing needs seeding.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.config import SETTINGS_MODELS
from app.models.account import SystemSetting


async def load[M: BaseModel](session: AsyncSession, key: str, model: type[M]) -> M:
    row = await session.get(SystemSetting, key)
    if row is None:
        return model()
    return model.model_validate(row.value)


async def load_raw(session: AsyncSession, key: str) -> dict[str, Any]:
    model = SETTINGS_MODELS[key]
    return (await load(session, key, model)).model_dump(mode="json")


async def save(
    session: AsyncSession, key: str, value: dict[str, Any], *, actor: uuid.UUID | None
) -> dict[str, Any]:
    """Validate, then store the normalised form. Raises ``ValidationError`` on bad input."""
    model = SETTINGS_MODELS[key]
    normalised = model.model_validate(value).model_dump(mode="json")
    row = await session.get(SystemSetting, key)
    if row is None:
        session.add(SystemSetting(key=key, value=normalised, updated_by=actor))
    else:
        row.value = normalised
        row.updated_by = actor
    return normalised
