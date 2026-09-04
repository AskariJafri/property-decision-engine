from datetime import UTC, datetime

import pytest

from app.provenance.policy import (
    GOOGLE_MAPS,
    MLS_PORTALS,
    OSM_SELF_HOSTED,
    LicenceClass,
    ProhibitedSourceError,
    ProviderPolicy,
    policy_for,
)
from app.provenance.types import Fact, Provenance, SourceClass

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


class TestFact:
    def test_unavailable_requires_a_reason(self):
        # The product's central promise, as a constructor guard.
        with pytest.raises(ValueError, match="reason"):
            Provenance(
                source_key="src_trca",
                source_class=SourceClass.UNAVAILABLE,
                retrieved_at=NOW,
            )

    def test_unavailable_is_a_value_not_an_error(self):
        fact: Fact[int] = Fact.unavailable("outside TRCA mapped coverage")
        assert fact.is_available is False
        assert fact.value is None
        assert fact.to_envelope()["reason"] == "outside TRCA mapped coverage"

    def test_require_raises_with_the_reason(self):
        fact: Fact[int] = Fact.unavailable("no square footage supplied")
        with pytest.raises(ValueError, match="no square footage supplied"):
            fact.require()

    def test_or_else_falls_back_without_pretending(self):
        fact: Fact[int] = Fact.unavailable("no condo fee supplied")
        assert fact.or_else(0) == 0

    def test_quality_discounts_by_source_class(self):
        user = Fact(
            value=1450,
            provenance=Provenance("src_user", SourceClass.USER_ASSERTED, NOW, confidence=1.0),
        )
        verified = Fact(
            value=1380,
            provenance=Provenance(
                "src_toronto_open_data", SourceClass.VERIFIED, NOW, confidence=1.0
            ),
        )
        assert user.quality < verified.quality

    def test_naive_timestamps_are_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            Provenance("src_user", SourceClass.USER_ASSERTED, datetime(2026, 9, 4))

    def test_confidence_is_bounded(self):
        with pytest.raises(ValueError, match="confidence"):
            Provenance("src_user", SourceClass.USER_ASSERTED, NOW, confidence=1.4)


class TestProviderPolicy:
    def test_prohibited_source_raises_before_anything_is_stored(self):
        # An adapter for a prohibited source cannot be written usefully. That is the point.
        with pytest.raises(ProhibitedSourceError, match="prohibited"):
            MLS_PORTALS.storage_decision(now=NOW)

    def test_open_source_stores_permanently(self):
        decision = OSM_SELF_HOSTED.storage_decision(now=NOW)
        assert decision.may_store is True
        assert decision.expires_at is None

    def test_restricted_source_gets_an_expiry(self):
        # Google is not used, but the policy is retained so a future adoption
        # inherits the 30-day coordinate limit rather than rediscovering it.
        restricted = ProviderPolicy(
            key="src_hypothetical",
            name="Hypothetical restricted provider",
            licence_class=LicenceClass.RESTRICTED,
            may_store_values=True,
            max_retention_days=30,
        )
        decision = restricted.storage_decision(now=NOW)
        assert decision.may_store is True
        assert decision.expires_at == datetime(2026, 10, 4, 12, 0, tzinfo=UTC)

    def test_non_storable_source_is_refused_storage(self):
        decision = GOOGLE_MAPS.storage_decision(now=NOW)
        assert decision.may_store is False

    def test_prohibited_cannot_be_declared_storable(self):
        with pytest.raises(ValueError, match="prohibited"):
            ProviderPolicy(
                key="src_bad",
                name="bad",
                licence_class=LicenceClass.PROHIBITED,
                may_store_values=True,
            )

    def test_unregistered_source_points_at_the_licensing_document(self):
        with pytest.raises(LookupError, match="DATA_LICENSING"):
            policy_for("src_something_nobody_reviewed")
