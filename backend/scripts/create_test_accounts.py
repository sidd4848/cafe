"""
Create (or reset) demo accounts for trying the app, and write their credentials to
backend/scripts/test_accounts.local.json (gitignored). Passwords are random per run.

    cd backend && PYTHONPATH=. .venv/Scripts/python -m scripts.create_test_accounts

Uses the reserved .test domain, so no real inbox exists for these addresses.
"""

import json
import secrets
from pathlib import Path

from firebase_admin import auth

from app.auth import set_role  # noqa: F401  (initialises firebase_admin)
from app.db import db, now

ACCOUNTS = [
    {"email": "customer1@cafecompanion.test", "name": "Aarav", "role": "customer"},
    {"email": "customer2@cafecompanion.test", "name": "Diya", "role": "customer"},
    {"email": "barista@cafecompanion.test", "name": "Kabir (Barista)", "role": "staff"},
    {"email": "manager@cafecompanion.test", "name": "Meera (Manager)", "role": "manager"},
]
OUT = Path(__file__).with_name("test_accounts.local.json")


def main() -> None:
    out = []
    for a in ACCOUNTS:
        password = secrets.token_urlsafe(9)
        try:
            user = auth.get_user_by_email(a["email"])
            auth.update_user(user.uid, password=password, display_name=a["name"], email_verified=True)
        except auth.UserNotFoundError:
            user = auth.create_user(email=a["email"], password=password, display_name=a["name"], email_verified=True)
        auth.set_custom_user_claims(user.uid, {"role": a["role"]} if a["role"] != "customer" else {})
        db().collection("users").document(user.uid).set(
            {"email": a["email"], "displayName": a["name"], "role": a["role"], "roleRevoked": False,
             "createdAt": now()}, merge=True)
        out.append({**a, "password": password,
                    "signIn": "/staff/login" if a["role"] != "customer" else "/login"})
        print(f"{a['role']:9} {a['email']}")
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nCredentials written to {OUT}")


if __name__ == "__main__":
    main()
