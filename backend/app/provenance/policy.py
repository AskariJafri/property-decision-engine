"""Licence terms, as a code path rather than a paragraph someone has to remember.

``DATA_LICENSING.md`` is the register; this module is its enforcement. Each
provider adapter declares a :class:`ProviderPolicy`, and the provenance
repository asks :meth:`ProviderPolicy.storage_decision` before it writes. A
provider that may not be stored cannot get a durable row, and a provider we are
not permitted to use at all cannot get a row of any kind.

The free stack (ADR 0002) means almost everything here is ``OPEN`` with
permanent storage. The machinery stays anyway, for two reasons. It is what
stops a future paid or retention-capped provider from being wired in casually,
and it is what makes the ``PROHIBITED`` entries — REALTOR.ca and the listing
portals — un-integrable by construction instead of by policy memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class LicenceClass(StrEnum):
    OPEN = "open"
    """Open licence permitting commercial use, modification and redistribution."""

    LICENSED = "licensed"
    """Paid or agreement-based; permitted within the terms of a contract we hold."""

    RESTRICTED = "restricted"
    """Usable, but with hard storage, retention or display limits."""

    PROHIBITED = "prohibited"
    """May not be used by this product. Recorded so the refusal is explicit."""


class ProhibitedSourceError(RuntimeError):
    """Raised when code attempts to record a fact from a prohibited source.

    Reaching this exception means someone wrote an adapter for a source the
    project has decided not to collect from. The fix is to delete the adapter,
    not to relax the policy.
    """


@dataclass(frozen=True, slots=True)
class StorageDecision:
    may_store: bool
    expires_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    """What one external source permits us to do with what it returns."""

    key: str
    name: str
    licence_class: LicenceClass
    may_store_values: bool
    max_retention_days: int | None = None
    attribution: str | None = None
    source_url: str | None = None
    terms_url: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.licence_class is LicenceClass.PROHIBITED and self.may_store_values:
            raise ValueError(f"{self.key}: a prohibited source cannot be storable")
        if self.max_retention_days is not None and self.max_retention_days <= 0:
            raise ValueError(f"{self.key}: max_retention_days must be positive")

    def storage_decision(self, *, now: datetime) -> StorageDecision:
        """Whether a fact from this provider may be persisted, and until when."""
        if self.licence_class is LicenceClass.PROHIBITED:
            raise ProhibitedSourceError(
                f"{self.key} ({self.name}) is a prohibited source; see DATA_LICENSING.md"
            )
        if not self.may_store_values:
            return StorageDecision(
                may_store=False,
                expires_at=None,
                reason=f"{self.key} forbids storing returned values; re-fetch on demand",
            )
        if self.max_retention_days is not None:
            return StorageDecision(
                may_store=True,
                expires_at=now + timedelta(days=self.max_retention_days),
                reason=f"{self.key} permits storage for {self.max_retention_days} days",
            )
        return StorageDecision(
            may_store=True, expires_at=None, reason=f"{self.key} permits storage"
        )


# --- The register, as code. Mirrors DATA_LICENSING.md §2. -------------------------------

OSM_SELF_HOSTED = ProviderPolicy(
    key="src_osm_self_hosted",
    name="OpenStreetMap (self-hosted Nominatim / OSRM / Overpass)",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="© OpenStreetMap contributors",
    source_url="https://www.openstreetmap.org/copyright",
    notes="ODbL. Self-hosting is the path OSMF policy directs geocoding applications to.",
)

BANK_OF_CANADA = ProviderPolicy(
    key="src_boc_valet",
    name="Bank of Canada Valet API",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="Bank of Canada",
    source_url="https://www.bankofcanada.ca/valet/docs",
)

STATISTICS_CANADA = ProviderPolicy(
    key="src_statcan",
    name="Statistics Canada Web Data Service",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="Adapted from Statistics Canada, 2021 Census",
    source_url="https://www.statcan.gc.ca/en/developers",
)

CMHC = ProviderPolicy(
    key="src_cmhc_hmip",
    name="CMHC Housing Market Information Portal",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="Source: CMHC",
    source_url="https://www.cmhc-schl.gc.ca/hmiportal",
)

TORONTO_OPEN_DATA = ProviderPolicy(
    key="src_toronto_open_data",
    name="City of Toronto Open Data",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="Contains information licensed under the Open Government Licence – Toronto",
    source_url="https://open.toronto.ca/",
)

TRCA = ProviderPolicy(
    key="src_trca",
    name="Toronto and Region Conservation Authority Open Data",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="Toronto and Region Conservation Authority",
    source_url="https://trca-camaps.opendata.arcgis.com/",
    notes="Floodline polygons carry FloodPlainSource; mapped vs estimated drives CONFIRMED "
    "vs POTENTIAL and must not be flattened.",
)

OPENROUTESERVICE = ProviderPolicy(
    key="src_openrouteservice",
    name="OpenRouteService (HeiGIT)",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    attribution="© openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors",
    source_url="https://openrouteservice.org/",
    terms_url="https://openrouteservice.org/terms-of-service/",
    notes="Free tier: 2,500 requests/day. The development stopgap named in ADR 0002; "
    "the self-hosted OSM stack remains the production answer. Results derive from "
    "OpenStreetMap under ODbL, so they are storable with attribution.",
)

USER_SUPPLIED = ProviderPolicy(
    key="src_user",
    name="User-supplied",
    licence_class=LicenceClass.OPEN,
    may_store_values=True,
    notes="Scoped to the supplying user. Never pooled across users (DATA_LICENSING.md §3.6).",
)

GOOGLE_MAPS = ProviderPolicy(
    key="src_google_maps",
    name="Google Maps Platform",
    licence_class=LicenceClass.RESTRICTED,
    may_store_values=False,
    max_retention_days=30,
    attribution="Map data ©2026 Google",
    terms_url="https://cloud.google.com/maps-platform/terms/maps-service-terms",
    notes="Not used (ADR 0002). Retained so a future adoption inherits the 30-day "
    "coordinate limit rather than rediscovering it.",
)

MLS_PORTALS = ProviderPolicy(
    key="src_mls_portals",
    name="REALTOR.ca and MLS-derived listing portals",
    licence_class=LicenceClass.PROHIBITED,
    may_store_values=False,
    terms_url="https://www.realtor.ca/terms-of-use",
    notes="Century 21 Canada LP v. Rogers Communications Inc., 2011 BCSC 1196. See ADR 0002 §2.",
)

REGISTRY: dict[str, ProviderPolicy] = {
    policy.key: policy
    for policy in (
        OSM_SELF_HOSTED,
        BANK_OF_CANADA,
        STATISTICS_CANADA,
        CMHC,
        TORONTO_OPEN_DATA,
        TRCA,
        OPENROUTESERVICE,
        USER_SUPPLIED,
        GOOGLE_MAPS,
        MLS_PORTALS,
    )
}


def policy_for(key: str) -> ProviderPolicy:
    try:
        return REGISTRY[key]
    except KeyError:
        raise LookupError(
            f"no licence policy registered for {key!r}; add a row to DATA_LICENSING.md first"
        ) from None
