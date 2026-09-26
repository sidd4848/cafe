"""
Seed the demo cafe: cafe doc, menu (with embeddings), busyness prior, live stats and the
QR secret. Safe to re-run: it upserts, and keeps learned prep times and availability on
items that already exist.

    cd backend && .venv/Scripts/python -m scripts.seed
"""

import secrets
import sys

from app.db import db, now
from app.menu_data import CAFE, MENU, NUTRITION, TABLES
from app.services import busyness, llm


def main() -> None:
    cafe_id = CAFE["id"]
    cafe_ref = db().collection("cafes").document(cafe_id)
    cafe_ref.set({k: v for k, v in CAFE.items() if k != "id"}, merge=True)
    print(f"cafe {cafe_id}")

    menu_ref = cafe_ref.collection("menu")
    for item in MENU:
        ref = menu_ref.document(item["id"])
        existing = ref.get().to_dict() or {}
        text = f"{item['name']}. {item['description']} Tags: {', '.join(item['tags'])}."
        doc = {k: v for k, v in item.items() if k != "id"}
        doc["embedding"] = llm.embed(text)
        doc.setdefault("available", existing.get("available", True))
        doc["prepSecEwma"] = existing.get("prepSecEwma", float(item["prepSecBase"]))
        doc["prepSecVar"] = existing.get("prepSecVar", (0.25 * item["prepSecBase"]) ** 2)
        doc["popularity7d"] = existing.get("popularity7d", 0)
        kcal, protein, sugar, sodium = NUTRITION[item["id"]]
        doc["nutrition"] = {"kcal": kcal, "proteinG": protein, "sugarG": sugar, "sodiumMg": sodium}
        ref.set(doc)
        sys.stdout.write(".")
        sys.stdout.flush()
    print(f"\n{len(MENU)} menu items")

    tables = cafe_ref.collection("tables")
    for tid, (label, seats, zone) in TABLES.items():
        ref = tables.document(tid)
        if not ref.get().exists:
            ref.set({"label": label, "seats": seats, "zone": zone, "status": "free"})
    print(f"{len(TABLES)} tables")
    cafe_ref.collection("stats").document("floor").set(
        {"dwellSec": {"small": 45 * 60, "medium": 60 * 60, "large": 75 * 60}, "turnoverSec": 180}, merge=True)

    busyness.seed_prior(cafe_id)
    cafe_ref.collection("stats").document("live").set(
        {"activeOrders": 0, "queuedItems": 0, "scheduledOrders": 0, "currentWaitSec": 185,
         "baristasOnShift": CAFE["baristasOnShift"], "etaAbsErrorEwmaSec": 60, "updatedAt": now()},
        merge=True)
    priv = db().collection("cafePrivate").document(cafe_id)
    if not (priv.get().to_dict() or {}).get("qrSecret"):
        priv.set({"qrSecret": secrets.token_hex(32)}, merge=True)
    print("busyness prior, live stats, qr secret: done")


if __name__ == "__main__":
    main()
