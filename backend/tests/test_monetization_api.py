"""The monetisation layer through the real API: credits, roles, payments, derived views.

The promises checked here are the ones a user or an attacker would test first:
the fifth free analysis is the last, logging out does not reset anything, a
browser cannot make itself an admin, and nothing is unlocked without a signed
event from the payment provider.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import time
from typing import Any

import pytest

from app.core.config import Settings

from .test_app import REQUEST

WEBHOOK_SECRET = "whsec_test_secret"


def request_at(price_dollars: int) -> dict[str, Any]:
    body = copy.deepcopy(REQUEST)
    body["property"]["purchase_price_cents"] = price_dollars * 100
    return body


def analyze(api, body: dict[str, Any] | None = None):
    return api.post("/api/v1/properties/analyze", json=body or REQUEST)


def usage(api) -> dict[str, Any]:
    return api.get("/api/v1/me").json()["usage"]


@pytest.fixture
def stripe_webhooks(monkeypatch: pytest.MonkeyPatch):
    settings = Settings(stripe_webhook_secret=WEBHOOK_SECRET)
    monkeypatch.setattr("app.billing.provider.get_settings", lambda: settings)
    return settings


def send_webhook(api, event: dict[str, Any], *, secret: str = WEBHOOK_SECRET):
    payload = json.dumps(event).encode()
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return api.post(
        "/api/v1/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"},
    )


def me_id(api) -> str:
    return api.get("/api/v1/me").json()["user"]["id"]


class TestAuth:
    def test_analysis_requires_an_account(self, api):
        assert analyze(api).status_code == 401

    def test_a_signed_in_post_without_the_csrf_header_is_refused(self, client):
        client.headers.pop("X-CSRF-Token")
        assert analyze(client).status_code == 403

    def test_signup_cannot_choose_a_role(self, api):
        response = api.post(
            "/api/v1/auth/signup",
            json={"email": "sneaky@example.com", "password": "long enough pw", "role": "admin"},
        )
        assert response.status_code == 422

    def test_wrong_password_and_unknown_email_look_the_same(self, api):
        api.signup("real@example.com")
        api.logout()
        wrong = api.login("real@example.com", "not the password")
        unknown = api.login("nobody@example.com", "not the password")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_repeated_failures_are_throttled(self, api):
        api.signup("target@example.com")
        api.logout()
        codes = [api.login("target@example.com", "guess").status_code for _ in range(12)]
        assert 429 in codes

    def test_duplicate_signup_is_refused(self, api):
        api.signup("twice@example.com")
        api.logout()
        response = api.post(
            "/api/v1/auth/signup", json={"email": "twice@example.com", "password": "another pw!!"}
        )
        assert response.status_code == 409


class TestFreeCredits:
    def test_five_free_analyses_then_a_clear_stop(self, client):
        assert usage(client)["free_remaining"] == 5
        for i in range(5):
            response = analyze(client, request_at(800_000 + i * 10_000))
            assert response.status_code == 200, response.text
            assert response.json()["usage"]["free_remaining"] == 4 - i
            assert response.json()["analysis_id"]

        blocked = analyze(client, request_at(900_000))
        assert blocked.status_code == 402
        detail = blocked.json()["detail"]
        assert detail["code"] == "limit_reached"
        assert detail["message"] == "You've used your 5 free property analyses."

    def test_credits_survive_logging_out_and_back_in(self, api):
        api.signup("keeper@example.com")
        for i in range(3):
            assert analyze(api, request_at(700_000 + i * 1000)).status_code == 200
        api.logout()
        assert api.login("keeper@example.com").status_code == 200
        assert usage(api)["free_remaining"] == 2

    def test_the_same_inputs_again_cost_nothing(self, client):
        first = analyze(client).json()
        second = analyze(client).json()
        assert second["duplicate"] is True
        assert second["analysis_id"] == first["analysis_id"]
        assert usage(client)["free_used"] == 1

    def test_a_refused_analysis_consumes_nothing(self, client):
        bad = copy.deepcopy(REQUEST)
        bad["buyer"]["down_payment_cents"] = 1_000_000
        assert analyze(client, bad).status_code == 422
        assert usage(client)["free_used"] == 0

    def test_viewing_listing_and_comparing_are_free(self, client):
        a = analyze(client, request_at(800_000)).json()["analysis_id"]
        b = analyze(client, request_at(850_000)).json()["analysis_id"]
        client.get("/api/v1/analyses")
        client.get(f"/api/v1/analyses/{a}")
        client.post("/api/v1/comparisons", json={"analysis_ids": [a, b]})
        client.post(f"/api/v1/analyses/{a}/offers", json={"prices_cents": [80_000_000]})
        assert usage(client)["free_used"] == 2

    def test_someone_elses_analysis_is_not_found(self, api):
        api.signup()
        mine = analyze(api).json()["analysis_id"]
        api.logout()
        api.signup()
        assert api.get(f"/api/v1/analyses/{mine}").status_code == 404


class TestAdmin:
    ADMIN_GETS = (
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/settings",
        "/api/v1/admin/errors",
        "/api/v1/admin/api-usage",
        "/api/v1/admin/funnel",
        "/api/v1/admin/audit",
    )

    def test_every_admin_route_refuses_an_ordinary_user(self, client):
        for path in self.ADMIN_GETS:
            assert client.get(path).status_code == 403, path
        assert client.put("/api/v1/admin/settings/ads", json={}).status_code == 403

    def test_a_forged_header_does_not_help(self, client):
        response = client.get(
            "/api/v1/admin/overview", headers={"X-Is-Admin": "true", "X-Role": "admin"}
        )
        assert response.status_code == 403

    def test_admin_routes_answer_an_admin(self, admin):
        for path in self.ADMIN_GETS:
            assert admin.get(path).status_code == 200, path

    def test_admins_are_unlimited_and_see_no_ads(self, admin):
        for i in range(7):
            assert analyze(admin, request_at(600_000 + i * 5000)).status_code == 200
        u = usage(admin)
        assert u["unlimited"] and u["tier"] == "admin" and not u["show_ads"]

    def test_the_overview_counts_real_rows_and_admits_what_it_cannot_know(self, admin):
        analyze(admin)
        body = admin.get("/api/v1/admin/overview").json()
        assert body["users"]["total"] == 1
        assert body["usage"]["analyses_today"] == 1
        assert body["revenue"]["all_time_cents"] == 0
        assert body["ads"]["impressions"] is None
        assert "contribution_margin_cents" in body["unit_economics"]

    def test_pricing_is_configurable_and_validated(self, api):
        api.signup("boss@example.com")
        api.set_role("boss@example.com", "admin")
        settings = api.get("/api/v1/admin/settings").json()
        pricing = settings["pricing"]
        pricing["free_analyses"] = 7
        pricing["products"][0]["price_cents"] = 1299
        assert api.put("/api/v1/admin/settings/pricing", json=pricing).status_code == 200
        public = api.get("/api/v1/config/public").json()
        assert public["free_analyses"] == 7
        assert public["products"][0]["price_cents"] == 1299

        pricing["products"][0]["price_cents"] = -5
        assert api.put("/api/v1/admin/settings/pricing", json=pricing).status_code == 422

    def test_ads_can_be_switched_off_for_everyone(self, api):
        api.signup("boss@example.com")
        api.set_role("boss@example.com", "admin")
        ads = api.get("/api/v1/admin/settings").json()["ads"]
        ads["enabled"] = False
        api.put("/api/v1/admin/settings/ads", json=ads)
        api.logout()
        api.signup()
        assert usage(api)["show_ads"] is False

    def test_an_admin_can_change_a_role_but_not_demote_themselves(self, api):
        api.signup("boss@example.com")
        api.set_role("boss@example.com", "admin")
        me = me_id(api)
        assert api.patch(f"/api/v1/admin/users/{me}", json={"role": "user"}).status_code == 409


class TestAds:
    def test_free_users_are_shown_ads(self, client):
        assert usage(client)["show_ads"] is True


class TestPayments:
    def test_checkout_without_keys_says_so_and_charges_nothing(self, client):
        analysis = analyze(client).json()["analysis_id"]
        response = client.post(
            "/api/v1/billing/checkout",
            json={"product_key": "deep_dive", "analysis_id": analysis},
        )
        assert response.status_code == 503
        assert "not set up" in response.json()["detail"]

    def test_deep_dive_is_locked_until_a_signed_payment_arrives(self, client, stripe_webhooks):
        analysis = analyze(client).json()["analysis_id"]
        locked = client.get(f"/api/v1/analyses/{analysis}/deep-dive")
        assert locked.status_code == 402
        assert locked.json()["detail"]["price_cents"] == 999

        event = {
            "id": "evt_deep_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_1",
                    "mode": "payment",
                    "payment_status": "paid",
                    "amount_total": 999,
                    "currency": "cad",
                    "metadata": {
                        "user_id": me_id(client),
                        "product_key": "deep_dive",
                        "analysis_id": analysis,
                    },
                }
            },
        }
        forged = send_webhook(client, event, secret="whsec_wrong")
        assert forged.status_code == 400
        assert client.get(f"/api/v1/analyses/{analysis}/deep-dive").status_code == 402

        assert send_webhook(client, event).json()["status"] == "payment recorded"
        assert send_webhook(client, event).json()["status"] == "duplicate"

        report = client.get(f"/api/v1/analyses/{analysis}/deep-dive")
        assert report.status_code == 200
        body = report.json()
        assert [h["years"] for h in body["projection"]["horizons"]] == [5, 10]
        assert any(float(o["rate"]) == 0 for o in body["projection"]["horizons"][1]["outcomes"])
        assert body["assumptions"] and body["questions"] and body["missing_info"]
        assert usage(client)["tier"] == "paid"

    def test_a_subscription_unlocks_watches_and_removes_ads(self, client, stripe_webhooks):
        analysis = analyze(client).json()["analysis_id"]
        refused = client.post("/api/v1/watches", json={"analysis_id": analysis})
        assert refused.status_code == 402

        event = {
            "id": "evt_sub_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_sub",
                    "mode": "subscription",
                    "subscription": "sub_123",
                    "customer": "cus_123",
                    "amount_total": 2900,
                    "currency": "cad",
                    "metadata": {"user_id": me_id(client), "product_key": "property_watch"},
                }
            },
        }
        assert send_webhook(client, event).json()["status"] == "subscription started"
        u = usage(client)
        assert u["plan_key"] == "property_watch" and not u["show_ads"]
        assert client.post("/api/v1/watches", json={"analysis_id": analysis}).status_code == 201

        cancelled = {
            "id": "evt_sub_2",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_123", "status": "canceled"}},
        }
        send_webhook(client, cancelled)
        assert usage(client)["plan_key"] is None

    def test_extra_analysis_promotions(self, api):
        api.signup("boss@example.com")
        api.set_role("boss@example.com", "admin")
        api.put(
            "/api/v1/admin/settings/promotions",
            json={"promotions": [{"code": "WELCOME3", "kind": "extra_analyses", "value": 3}]},
        )
        api.logout()
        api.signup()
        response = api.post("/api/v1/promo/redeem", json={"code": "welcome3"})
        assert response.status_code == 200
        assert response.json()["usage"]["free_total"] == 8
        assert api.post("/api/v1/promo/redeem", json={"code": "WELCOME3"}).status_code == 409


class TestDerivedViews:
    def test_offer_scenarios_are_full_recalculations(self, client):
        analysis = analyze(client).json()["analysis_id"]
        body = client.post(
            f"/api/v1/analyses/{analysis}/offers",
            json={"prices_cents": [82_500_000, 85_000_000, 87_500_000]},
        ).json()
        rows = body["scenarios"]
        assert [r["price_cents"] for r in rows] == [82_500_000, 85_000_000, 87_500_000]
        monthly = [r["monthly_carrying_cost_cents"] for r in rows]
        assert monthly == sorted(monthly)
        assert all(len(r["rate_sensitivity"]) == 2 for r in rows)
        assert "not a recommendation" in body["note"]

    def test_an_offer_below_the_minimum_down_payment_says_so(self, client):
        analysis = analyze(client).json()["analysis_id"]
        rows = client.post(
            f"/api/v1/analyses/{analysis}/offers", json={"prices_cents": [250_000_000]}
        ).json()["scenarios"]
        assert "below" in rows[0]["error"]

    def test_comparison_describes_without_ranking(self, client):
        a = analyze(client, request_at(800_000)).json()["analysis_id"]
        b = analyze(client, request_at(950_000)).json()["analysis_id"]
        body = client.post("/api/v1/comparisons", json={"analysis_ids": [a, b]}).json()
        assert len(body["columns"]) == 2
        assert body["differences"]
        verdicts = json.dumps([body["differences"], body["trade_offs"]]).lower()
        assert "best" not in verdicts and "recommend" not in verdicts

    def test_the_free_analysis_carries_its_plain_language_layer(self, client):
        body = analyze(client).json()
        keys = {line["key"] for line in body["monthly_breakdown"]}
        assert {"mortgage_payment", "property_tax", "insurance", "maintenance"} <= keys
        assert body["missing_info"] and body["personal"]["lines"]
        assert [round(s["rate"], 4) for s in body["rate_scenarios"]] == [0.0409, 0.0509, 0.0609]
        assert "not financial" in body["disclaimer"]


class TestWatch:
    def test_a_price_change_recalculates_without_a_credit(self, admin):
        analysis = analyze(admin).json()["analysis_id"]
        watch = admin.post("/api/v1/watches", json={"analysis_id": analysis}).json()
        response = admin.post(
            f"/api/v1/watches/{watch['id']}/updates",
            json={"price_cents": 82_000_000, "listing_status": "for_sale"},
        ).json()
        impact = {row["key"]: row for row in response["impact"]}
        assert impact["purchase_price_cents"]["change"] == -3_000_000
        assert impact["monthly_ownership_cost_cents"]["change"] < 0
        assert response["new_analysis_id"] != analysis
        events = response["watch"]["events"]
        assert events[0]["field"] == "price" and events[0]["new_value"] == "82000000"

    def test_the_watch_says_monitoring_is_manual(self, admin):
        body = admin.get("/api/v1/watches").json()
        assert body["automatic_monitoring"] is False
        assert body["providers"][0]["key"] == "manual"

    def test_the_scheduled_refresh_needs_the_secret(self, api):
        assert api.post("/api/v1/internal/watch/refresh").status_code == 401


class TestLimits:
    def test_an_oversized_body_is_refused_before_it_is_read(self, client):
        response = client.post(
            "/api/v1/listings/parse",
            content=b"{}",
            headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "application/json"},
        )
        assert response.status_code == 413

    def test_client_events_are_whitelisted(self, client):
        ok = client.post("/api/v1/events", json={"name": "upgrade_clicked"}).json()
        dropped = client.post("/api/v1/events", json={"name": "income_entered"}).json()
        assert ok["accepted"] and not dropped["accepted"]
