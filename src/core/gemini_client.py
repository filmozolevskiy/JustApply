"""Gemini API client.

Uses REST transport because the deprecated google-generativeai gRPC client can
hang indefinitely on some environments while the same API key works over REST.
"""

import asyncio
import os

import google.generativeai as genai
from dotenv import load_dotenv

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_TIMEOUT_SECONDS = 30.0


def get_api_key() -> str | None:
    load_dotenv(override=True)
    return os.getenv("GEMINI_API_KEY")


def get_model():
    api_key = get_api_key()
    if not api_key:
        return None
    genai.configure(api_key=api_key, transport="rest")
    return genai.GenerativeModel(MODEL_NAME)


async def generate_text(prompt: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    model = get_model()
    if model is None:
        raise RuntimeError("GEMINI_API_KEY not set")

    def _call() -> str:
        return model.generate_content(prompt).text.strip()

    return await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)
