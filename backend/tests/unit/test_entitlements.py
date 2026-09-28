"""Who may do what. Pure, so every tier and edge is checked without a database."""

import pytest
from pydantic import ValidationError

from app.billing.config import AdsConfig, PricingConfig, ProjectionConfig, PromotionsConfig
from app.billing.entitlements import AccountState, entitlements

PRICING = PricingConfig()
ADS = AdsConfig()


def ent(**state):
    return entitlements(AccountState(**{"role": "user", **state}), PRICING, ADS)


class TestFreeAllowance:
    def test_a_new_user_has_five(self):
        e = ent()
        assert (e.free_total, e.free_remaining, e.tier) == (5, 5, "free")
        assert e.next_credit_source == "free"

    def test_the_fifth_is_the_last(self):
        assert ent(free_used=4).free_remaining == 1
        e = ent(free_used=5)
        assert e.free_remaining == 0
        assert not e.can_analyze

    def test_promo_analyses_extend_the_allowance(self):
        e = ent(free_used=5, promo_analyses=3)
        assert (e.free_total, e.free_remaining, e.can_analyze) == (8, 3, True)

    def test_free_users_see_ads_and_have_no_watches_or_deep_dive(self):
        e = ent()
        assert e.show_ads and e.watch_limit == 0 and not e.deep_dive_included


class TestPlans:
    def test_a_watch_subscriber_draws_on_the_plan_first(self):
        e = ent(active_subscriptions=("property_watch",), plan_used_this_month=3)
        assert e.tier == "paid"
        assert e.next_credit_source == "plan"
        assert e.plan_remaining == 27
        assert e.watch_limit == 10
        assert not e.show_ads

    def test_an_exhausted_plan_falls_back_to_free_credits(self):
        e = ent(active_subscriptions=("property_watch",), plan_used_this_month=30, free_used=2)
        assert e.next_credit_source == "free"

    def test_an_exhausted_plan_and_free_allowance_stops(self):
        e = ent(active_subscriptions=("property_watch",), plan_used_this_month=30, free_used=5)
        assert not e.can_analyze

    def test_professional_wins_over_watch_and_includes_deep_dive(self):
        e = ent(active_subscriptions=("property_watch", "professional"))
        assert e.tier == "professional" and e.plan_key == "professional"
        assert e.deep_dive_included and e.watch_limit == 50

    def test_the_professional_role_is_a_complimentary_plan(self):
        assert ent(role="professional").tier == "professional"

    def test_a_one_time_buyer_is_paid_but_keeps_free_credits(self):
        e = ent(has_purchase=True, free_used=1)
        assert e.tier == "paid" and e.next_credit_source == "free"
        assert not e.show_ads


class TestAdmin:
    def test_admins_are_unlimited_and_never_see_ads(self):
        e = ent(role="admin", free_used=500)
        assert e.unlimited and e.can_analyze and e.next_credit_source == "unlimited"
        assert e.watch_limit is None and e.deep_dive_included and not e.show_ads


class TestAds:
    def test_disabled_ads_are_shown_to_nobody(self):
        e = entitlements(AccountState(role="user"), PRICING, AdsConfig(enabled=False))
        assert not e.show_ads

    def test_audiences_are_configurable(self):
        ads = AdsConfig(show_to_paid=True)
        e = entitlements(AccountState(role="user", has_purchase=True), PRICING, ads)
        assert e.show_ads

    def test_unknown_slots_are_refused(self):
        with pytest.raises(ValidationError):
            AdsConfig(slots={"AD_SLOT_INSIDE_THE_MORTGAGE_FIGURE": True})


class TestConfigValidation:
    def test_defaults_are_the_launch_prices_in_cad(self):
        assert PRICING.currency == "CAD"
        assert PRICING.product("deep_dive").price_cents == 999
        assert PRICING.product("property_watch").price_cents == 2900
        assert PRICING.product("professional").price_cents == 4900

    def test_a_subscription_needs_an_interval(self):
        data = PRICING.model_dump(mode="json")
        data["products"][1]["interval"] = None
        with pytest.raises(ValidationError):
            PricingConfig.model_validate(data)

    def test_negative_prices_are_refused(self):
        data = PRICING.model_dump(mode="json")
        data["products"][0]["price_cents"] = -1
        with pytest.raises(ValidationError):
            PricingConfig.model_validate(data)

    def test_the_no_appreciation_scenario_cannot_be_removed(self):
        with pytest.raises(ValidationError):
            ProjectionConfig(appreciation_rates=["0.03", "0.05"])

    def test_expired_promotions_do_not_apply(self):
        from datetime import date

        promos = PromotionsConfig.model_validate(
            {
                "promotions": [
                    {
                        "code": "LAUNCH",
                        "kind": "extra_analyses",
                        "value": 3,
                        "expires_on": "2026-01-01",
                    }
                ]
            }
        )
        assert promos.find("launch", date(2025, 12, 31)) is not None
        assert promos.find("LAUNCH", date(2026, 1, 2)) is None
