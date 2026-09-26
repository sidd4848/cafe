"""
Free-text dietary filter: "low-sodium, gluten-free, high-protein".

Gemini only translates the words into a structured filter; the filtering itself is plain
code over each item's allergen tags and nutrition. So an allergen the guest named can
never slip through on a model's judgement call. When the model is unreachable, a keyword
parser covers the common requests.
"""

import logging
import re

from app.services import llm

logger = logging.getLogger(__name__)

ALLERGENS = ["dairy", "gluten", "nuts", "egg"]
THRESHOLDS = {"low_sodium": 400, "low_sugar": 10, "high_protein": 10, "low_calorie": 200}

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "avoidAllergens": {"type": "ARRAY", "items": {"type": "STRING", "enum": ALLERGENS}},
        "diet": {"type": "STRING", "enum": ["any", "veg", "vegan"]},
        "maxKcal": {"type": "INTEGER"},
        "minProteinG": {"type": "INTEGER"},
        "maxSugarG": {"type": "INTEGER"},
        "maxSodiumMg": {"type": "INTEGER"},
        "caffeine": {"type": "STRING", "enum": ["any", "none", "low"]},
        "temperature": {"type": "STRING", "enum": ["any", "hot", "iced"]},
        "summary": {"type": "STRING"},
    },
    "required": ["avoidAllergens", "diet", "summary"],
}

_SYSTEM = f"""Turn a café guest's dietary request into a structured filter.
Allergens you can express: {', '.join(ALLERGENS)} ("lactose-free"/"dairy-free" = dairy,
"coeliac"/"gluten-free" = gluten, "nut allergy" = nuts, "eggless" = egg).
Use these thresholds when a guest says low/high without numbers:
low sodium -> maxSodiumMg {THRESHOLDS['low_sodium']}; low sugar/diabetic-friendly -> maxSugarG {THRESHOLDS['low_sugar']};
high protein -> minProteinG {THRESHOLDS['high_protein']}; light/low calorie -> maxKcal {THRESHOLDS['low_calorie']}.
"Keto" means low sugar. Leave fields out when not mentioned. summary: a 6-12 word plain restatement."""


def _fallback(query: str) -> dict:
    q = query.lower()
    f: dict = {"avoidAllergens": [], "diet": "any"}
    for word, allergen in [("dairy", "dairy"), ("lactose", "dairy"), ("gluten", "gluten"), ("coeliac", "gluten"),
                           ("celiac", "gluten"), ("nut", "nuts"), ("egg", "egg")]:
        if word in q:
            f["avoidAllergens"].append(allergen)
    if "vegan" in q or "plant" in q:
        f["diet"] = "vegan"
    elif re.search(r"\bveg(etarian)?\b", q):
        f["diet"] = "veg"
    if "sodium" in q or "salt" in q:
        f["maxSodiumMg"] = THRESHOLDS["low_sodium"]
    if "sugar" in q or "keto" in q or "diabet" in q:
        f["maxSugarG"] = THRESHOLDS["low_sugar"]
    if "protein" in q:
        f["minProteinG"] = THRESHOLDS["high_protein"]
    if "calorie" in q or "light" in q:
        f["maxKcal"] = THRESHOLDS["low_calorie"]
    if "decaf" in q or "caffeine" in q:
        f["caffeine"] = "none"
    f["summary"] = query.strip()[:80]
    return f


def parse(query: str) -> dict:
    try:
        f = llm.generate_json(_SYSTEM, query, _SCHEMA, temperature=0)
        f["avoidAllergens"] = sorted(set(f.get("avoidAllergens") or []) | set(_fallback(query)["avoidAllergens"]))
        return f
    except Exception as e:
        logger.warning(f"Filter parse fell back to keywords: {e}")
        return _fallback(query)


def apply(items: list[dict], f: dict) -> tuple[list[str], list[dict]]:
    """Returns (allowed ids, [{id, reason}] excluded). Plant-milk drinks pass a dairy/vegan
    filter only because the guest can switch the milk; the UI suggests that swap."""
    keep, out = [], []
    avoid = set(f.get("avoidAllergens") or [])
    diet = f.get("diet") or "any"
    for item in items:
        dietary = set(item.get("dietary", []))
        tags = set(item.get("tags", []))
        n = item.get("nutrition") or {}
        swappable_dairy = "milk" in item.get("modifiers", [])
        reason = None
        if diet in {"veg", "vegan"} and "non_veg" in dietary:
            reason = "contains meat"
        elif (diet == "vegan" or "dairy" in avoid) and "dairy" in dietary and not swappable_dairy:
            reason = "contains dairy"
        elif diet == "vegan" and "egg" in dietary:
            reason = "contains egg"
        elif hit := (avoid - {"dairy"}) & dietary:
            reason = f"contains {', '.join(sorted(hit))}"
        elif f.get("maxSodiumMg") is not None and n.get("sodiumMg", 0) > f["maxSodiumMg"]:
            reason = f"{n['sodiumMg']} mg sodium"
        elif f.get("maxSugarG") is not None and n.get("sugarG", 0) > f["maxSugarG"]:
            reason = f"{n['sugarG']} g sugar"
        elif f.get("minProteinG") is not None and n.get("proteinG", 0) < f["minProteinG"]:
            reason = f"only {n.get('proteinG', 0)} g protein"
        elif f.get("maxKcal") is not None and n.get("kcal", 0) > f["maxKcal"]:
            reason = f"{n['kcal']} kcal"
        elif f.get("caffeine") == "none" and item["category"] in {"hot_coffee", "cold_coffee", "manual_brew"}:
            reason = "has caffeine"
        elif f.get("caffeine") == "low" and "strong" in tags:
            reason = "strong caffeine"
        elif f.get("temperature") in {"hot", "iced"} and item["category"] not in {"bakery", "savoury", "dessert"} \
                and f["temperature"] not in tags:
            reason = f"not {f['temperature']}"
        if reason:
            out.append({"id": item["id"], "name": item["name"], "reason": reason})
        else:
            keep.append(item["id"])
    return keep, out
