from app.router import route_prompt, score_prompt


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
