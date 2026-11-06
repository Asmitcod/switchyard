from app.router import route_prompt, score_prompt
from app.main import app
from app.providers import ProviderConfig
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


def test_chat_completion_matches_openai_response_shape(monkeypatch):
    config = ProviderConfig("cheap", "https://provider.test", "test-key", "test-model")
    monkeypatch.setattr("app.main.provider_config", lambda tier: config if tier == "cheap" else None)
    monkeypatch.setattr(
        "app.main.complete",
        lambda *_args: {
            "id": "chatcmpl-test",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "test response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
        },
    )
    monkeypatch.setattr("app.main.log_request", lambda *_args, **_kwargs: None)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "routewise", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "test response"
    assert body["model"] == "test-model"


def test_chat_completion_streams_sse_done_marker(monkeypatch):
    config = ProviderConfig("cheap", "https://provider.test", "test-key", "test-model")
    monkeypatch.setattr("app.main.provider_config", lambda tier: config if tier == "cheap" else None)
    monkeypatch.setattr("app.main.stream_complete", lambda *_args: iter(["data: {\"choices\": []}"]))
    monkeypatch.setattr("app.main.log_request", lambda *_args, **_kwargs: None)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "routewise",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: {\"choices\": []}" in response.text
    assert "data: [DONE]" in response.text


def test_status_requires_configured_api_key(monkeypatch):
    monkeypatch.setenv("ROUTEWISE_API_KEYS", "status-test-key")

    unauthorized = client.get("/api/status")
    authorized = client.get(
        "/api/status",
        headers={"Authorization": "Bearer status-test-key"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_playground_endpoints_remain_public_when_api_keys_are_configured(monkeypatch):
    monkeypatch.setenv("ROUTEWISE_API_KEYS", "dashboard-only-key")
    config = ProviderConfig("cheap", "https://provider.test", "test-key", "test-model")
    monkeypatch.setattr("app.main.provider_config", lambda tier: config if tier == "cheap" else None)
    monkeypatch.setattr(
        "app.main.complete",
        lambda *_args: {
            "id": "chatcmpl-playground",
            "created": 1,
            "choices": [{"message": {"role": "assistant", "content": "public answer"}}],
            "usage": {},
        },
    )
    monkeypatch.setattr("app.main.log_request", lambda *_args, **_kwargs: None)

    route_response = client.post("/api/route", json={"prompt": "hello"})
    answer_response = client.post(
        "/api/playground",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert route_response.status_code == 200
    assert answer_response.status_code == 200
