"""Gemini API client backed by google.genai."""

import asyncio
import os

from google import genai
from google.genai import types
from dotenv import load_dotenv

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_TIMEOUT_SECONDS = 30.0
PDF_TIMEOUT_SECONDS = 60.0


def get_api_key() -> str | None:
    load_dotenv(override=True)
    return os.getenv("GEMINI_API_KEY")


def get_client():
    api_key = get_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


async def generate_text(prompt: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    client = get_client()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not set")

    def _call() -> str:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        return response.text.strip()

    return await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)


async def generate_text_from_pdf(
    pdf_bytes: bytes,
    prompt: str,
    *,
    timeout: float = PDF_TIMEOUT_SECONDS,
) -> str:
    """Multimodal call: PDF bytes + text prompt (used by Resume Import)."""
    client = get_client()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not set")

    def _call() -> str:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt,
            ],
        )
        return response.text.strip()

    return await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)
