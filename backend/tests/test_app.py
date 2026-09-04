from fastapi.testclient import TestClient

from app.engines.scoring.contracts import SCORING_MODEL_VERSION
from app.main import create_app

client = TestClient(create_app())

REQUEST = {
    "property": {
        "purchase_price_cents": 85_000_000,
        "jurisdiction": "ON/Toronto",
        "property_kind": "detached",
        "square_feet": 1450,
        "year_built": 1998,
        "bedrooms": 3,
        "bathrooms": "2.5",
        "has_parking": True,
    },
    "buyer": {
        "gross_annual_income_cents": 19_000_000,
        "household_income_cents": 19_000_000,
        "monthly_debt_payments_cents": 45_000,
        "down_payment_cents": 12_000_000,
        "available_savings_cents": 16_000_000,
        "emergency_fund_cents": 1_500_000,
        "desired_max_monthly_cents": 600_000,
        "first_time_buyer": True,
        "residency_status": "citizen_or_pr",
    },
    "terms": {"contract_rate": "0.0409", "amortization_years": 25},
    "preferences": {
        "min_bedrooms": 3,
        "requires_parking": True,
        "max_commute_minutes": 45,
        "commute_minutes": 38,
        "goal": "primary_residence",
        "time_horizon": "5_to_10",
        "risk_posture": "balanced",
    },
    "comparables": [
        {
            "address": "12 Elm St",
            "sale_price_cents": 83_000_000,
            "sale_date": "2026-07-14",
            "square_feet": 1420,
            "bedrooms": 3,
            "distance_m": 400,
        },
        {
            "address": "44 Oak Ave",
            "sale_price_cents": 87_500_000,
            "sale_date": "2026-06-02",
            "square_feet": 1530,
            "bedrooms": 3,
            "distance_m": 900,
        },
        {
            "address": "9 Pine Cr",
            "sale_price_cents": 81_000_000,
            "sale_date": "2026-08-20",
            "square_feet": 1380,
            "bedrooms": 3,
            "distance_m": 650,
        },
    ],
}


def test_health():
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["pilot_jurisdiction"] == "ON/Toronto"
    assert body["scoring_model_version"] == SCORING_MODEL_VERSION


def test_openapi_is_served_under_the_versioned_prefix():
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/properties/analyze" in paths


def test_analyze_returns_a_complete_analysis():
    response = client.post("/api/v1/properties/analyze", json=REQUEST)
    assert response.status_code == 200, response.text
    body = response.json()

    assert 0 <= body["buy_score"] <= 100
    assert body["score_withheld_reason"] is None
    assert body["money"]["monthly_ownership_cost_cents"] > 0
    assert body["qualification"]["may_qualify"] in (True, False)
    assert "lender" in body["qualification"]["disclaimer"].lower()
    assert body["fair_value"]["low_cents"] < body["fair_value"]["high_cents"]
    assert body["traces"], "every figure must carry its working"
    assert body["assumptions"], "defaults must surface as assumptions"
    assert "not financial" in body["disclaimer"]


def test_the_same_request_produces_the_same_score_and_hash():
    first = client.post("/api/v1/properties/analyze", json=REQUEST).json()
    second = client.post("/api/v1/properties/analyze", json=REQUEST).json()
    assert first["inputs_hash"] == second["inputs_hash"]
    assert first["buy_score"] == second["buy_score"]
    assert first["scores"] == second["scores"]


def test_comparables_narrow_the_range_and_raise_confidence():
    without = client.post("/api/v1/properties/analyze", json={**REQUEST, "comparables": []}).json()
    with_comps = client.post("/api/v1/properties/analyze", json=REQUEST).json()

    def spread(body):
        return body["fair_value"]["high_cents"] - body["fair_value"]["low_cents"]

    assert spread(with_comps) < spread(without)
    assert with_comps["fair_value"]["confidence"] > without["fair_value"]["confidence"]
    assert "No comparable sales supplied" in without["fair_value"]["note"]


def test_unavailable_components_are_named_not_hidden():
    body = client.post("/api/v1/properties/analyze", json=REQUEST).json()
    unavailable = {u.get("component") for u in body["unavailable"]}
    assert "location" in unavailable
    for entry in body["unavailable"]:
        assert entry["reason"], "a missing value must state why"


def test_an_impossible_file_is_refused_with_the_engines_own_words():
    bad = {**REQUEST, "buyer": {**REQUEST["buyer"], "down_payment_cents": 1_000_000}}
    response = client.post("/api/v1/properties/analyze", json=bad)
    assert response.status_code == 422
    assert "minimum" in response.json()["detail"]


def test_reference_rules_shows_the_brackets_and_their_sources():
    body = client.get("/api/v1/reference/rules?jurisdiction=ON/Toronto").json()
    names = {rule["name"] for rule in body["rules"]}
    assert "ltt.brackets.sfr" in names and "mltt.brackets.sfr" in names
    for rule in body["rules"]:
        assert rule["source_url"].startswith("http")
        assert rule["verification"] in {"primary", "secondary"}
    # The unverified rules are disclosed as excluded, not silently absent.
    assert body["excluded_unverified"]


def test_reference_rules_respects_the_as_of_date():
    before = client.get("/api/v1/reference/rules?jurisdiction=ON/Toronto&as_of=2026-03-31").json()
    after = client.get("/api/v1/reference/rules?jurisdiction=ON/Toronto&as_of=2026-04-01").json()

    def mltt(body):
        return next(r for r in body["rules"] if r["name"] == "mltt.brackets.sfr")["value"]

    assert len(mltt(after)["brackets"]) > len(mltt(before)["brackets"])


def test_reference_sources_lists_the_prohibited_ones_too():
    sources = client.get("/api/v1/reference/sources").json()["sources"]
    prohibited = [s for s in sources if s["licence_class"] == "prohibited"]
    assert prohibited, "the refusal is part of the record"
    assert all(s["may_store_values"] is False for s in prohibited)


def test_the_browser_preflight_is_answered():
    """Found by driving the real page: without CORS the browser never gets past
    the preflight, and the API looks fine to every test that is not a browser."""
    response = client.options(
        "/api/v1/properties/analyze",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_an_unknown_origin_is_not_allowed():
    response = client.options(
        "/api/v1/properties/analyze",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_health_answers_head_as_well_as_get():
    """Monitors and load balancers probe with HEAD. A health endpoint that
    returns 405 to them reports itself unhealthy while being perfectly fine —
    which is exactly what happened in CI, twice."""
    assert client.head("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
