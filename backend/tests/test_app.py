from fastapi.testclient import TestClient

from app.engines.scoring.contracts import SCORING_MODEL_VERSION
from app.main import create_app


def test_health_reports_the_pilot_jurisdiction_and_model_version():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["pilot_jurisdiction"] == "ON/Toronto"
    assert body["scoring_model_version"] == SCORING_MODEL_VERSION


def test_openapi_is_served_under_the_versioned_prefix():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
