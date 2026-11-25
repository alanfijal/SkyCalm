"""Ground passenger briefings in the categories present along the computed route."""

import hashlib
import json

from services.forecast.schema import CATEGORIES


def variants(points):
    valid = [p for p in points if p["category"] in CATEGORIES]
    if not valid:
        return [
            ["There is too little forecast coverage to describe this route."],
            ["The timeline marks the sections with missing data."],
        ]
    peak = max(valid, key=lambda p: CATEGORIES.index(p["category"]))
    category, phase = peak["category"], peak["phase"]
    first = [
        f"The highest forecast category is {category} during {phase}.",
        f"The route reaches its highest forecast category, {category}, during {phase}.",
    ]
    if any(p["category"] == "unavailable" for p in points):
        second = [
            "Some sections have no forecast coverage.",
            "Weather data cover only part of this route.",
        ]
    elif all(p["category"] == valid[0]["category"] for p in valid):
        second = [
            "The forecast category stays the same along the sampled route.",
            "All sampled sections have the same forecast category.",
        ]
    else:
        second = [
            "The forecast category varies along the route.",
            "The timeline shows where the category changes.",
        ]
    return [first, second]


def cache_key(run, origin, destination, departure, choices):
    raw = json.dumps(
        [1, run, origin, destination, departure, choices], separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def select(choices, indices):
    if (
        not isinstance(indices, list)
        or len(indices) != len(choices)
        or any(
            type(i) is not int or not 0 <= i < len(options)
            for i, options in zip(indices, choices, strict=True)
        )
    ):
        raise ValueError("Unknown briefing sentence selection")
    return " ".join(options[i] for options, i in zip(choices, indices, strict=True))


def choose_with_bedrock(client, model_id, choices):
    response = client.converse(
        modelId=model_id,
        system=[
            {
                "text": "Choose one calm formulation per supplied sentence group. Return only a JSON array of zero-based indices. Do not add text."
            }
        ],
        messages=[{"role": "user", "content": [{"text": json.dumps(choices)}]}],
        inferenceConfig={"maxTokens": 24, "temperature": 0},
    )
    if response.get("stopReason") != "end_turn":
        raise ValueError("Incomplete briefing")
    indices = json.loads(response["output"]["message"]["content"][0]["text"])
    select(choices, indices)
    return indices
