"""
Cafe Companion API (Cloud Run: cafe-api).

Every route except /health needs a Firebase ID token; staff routes also need the `role`
claim, and /internal/* only accepts Cloud Scheduler's OIDC token. All Firestore writes
happen here; the browser only holds read-only realtime listeners (see firestore.rules).
"""

import logging

import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import ALLOWED_ORIGINS
from app.routers import connect, customer, dinein, internal, staff

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Cafe Companion API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/", include_in_schema=False)
async def root():
    """This is the API; send anyone who opens it in a browser to the app."""
    web = os.getenv("WEB_URL")
    return RedirectResponse(web) if web else {"service": "cafe-api", "health": "/health"}


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(customer.router)
app.include_router(dinein.router)
app.include_router(staff.router)
app.include_router(connect.router)
app.include_router(internal.router)
