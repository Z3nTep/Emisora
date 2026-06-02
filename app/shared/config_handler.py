import json
import os
import random

def load_config(config_path: str) -> dict:
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_config(config_path: str, settings: dict) -> None:
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, ensure_ascii=False)

def get_weighted_category(categories: dict, settings: dict) -> str | None:
    weights = []
    cat_names = []
    total_weight = 0
    for cat in categories:
        val = settings.get(cat, 100)
        if val > 0:
            weights.append(val)
            cat_names.append(cat)
            total_weight += val
    if total_weight == 0:
        return None
    rand = random.random() * total_weight
    for i, w in enumerate(weights):
        rand -= w
        if rand <= 0:
            return cat_names[i]
    return cat_names[-1]
