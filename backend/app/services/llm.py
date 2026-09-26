"""Gemini on Vertex: one shared client, JSON calls, embeddings and moderation."""

import json
import logging
import re

from google import genai
from google.genai import types

from app.config import EMBED_DIM, EMBED_MODEL, GEMINI_LOCATION, GEMINI_MODEL, PROJECT_ID

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

NO_AFC = types.AutomaticFunctionCallingConfig(disable=True)


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT_ID, location=GEMINI_LOCATION)
    return _client


def generate_json(system: str, prompt: str, schema: dict, temperature: float = 0.4) -> dict:
    response = client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
            automatic_function_calling=NO_AFC,
        ),
    )
    return json.loads(response.text or "{}")


def embed(text: str, task: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    result = client().models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM, task_type=task),
    )
    return list(result.embeddings[0].values)


# ---- Moderation ------------------------------------------------------------------------

_BLOCKLIST = re.compile(
    r"\b(nude|nudes|sex|escort|onlyfans|kill yourself|kys)\b|(\+?\d[\d\s-]{9,}\d)",
    re.IGNORECASE,
)

_MOD_SYSTEM = """You moderate short messages between two adults who met through a café app
and may meet in person. Flag content that is sexual or explicit, harassing, hateful,
threatening, soliciting money, pushing to move off-platform with contact details
(phone numbers, social handles, addresses), or otherwise unsafe. Friendly small talk,
flirting that is polite, and proposing to meet at the café are all fine."""

_MOD_SCHEMA = {
    "type": "OBJECT",
    "properties": {"ok": {"type": "BOOLEAN"}, "reason": {"type": "STRING"}},
    "required": ["ok"],
}


def moderate(text: str) -> tuple[bool, str | None]:
    """
    Returns (allowed, reason). A cheap pattern check runs first; the model catches the
    rest. If the model is unreachable the message is allowed: the blocklist still
    applies, and failing closed would take the chat down with every model hiccup.
    """
    if _BLOCKLIST.search(text):
        return False, "Please keep it friendly and don't share contact details yet."
    try:
        verdict = generate_json(_MOD_SYSTEM, text, _MOD_SCHEMA, temperature=0)
    except Exception as e:
        logger.warning(f"Moderation model unavailable, allowing: {e}")
        return True, None
    if verdict.get("ok", True):
        return True, None
    return False, verdict.get("reason") or "That message can't be sent."
