from app.router import route_prompt, score_prompt
from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_easy_prompt_scores_above_hard_prompt():
    assert score_prompt("What is the capital of Australia?") > score_prompt(
        "Derive the gradient step by step and debug this algorithm."
    )


def test_threshold_selects_expected_tier():
    result = route_prompt("What is the capital of Australia?", 0.6)
    assert result["cheap"] is True
    assert result["chosen_model"] == "cheap"


def test_router_costs_are_ordered():
    result = route_prompt("Explain a difficult algorithm step by step.", 0.6)
    assert result["estimated_cost_per_1000"] <= result["strong_cost_per_1000"]


def test_openai_models_discovery():
    response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "routewise"


def test_readiness_does_not_expose_credentials():
    response = client.get("/readyz")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()


def test_status_does_not_expose_connection_values():
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.text.lower()
    assert "groq_api_key" not in body
    assert "postgresql://" not in body
