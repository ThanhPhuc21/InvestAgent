"""Configuration and environment helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("STOCK_AGENT_MODEL", "gpt-4.1")
TEMPERATURE = float(os.getenv("STOCK_AGENT_TEMPERATURE", "0.2"))
DEFAULT_HISTORY_DAYS = 365
DEFAULT_SOURCE = "VCI"
FALLBACK_SOURCES = ["KBS"]
API_RETRIES = 3
REQUEST_DELAY_SEC = 0.8
OUTPUT_DIR = Path(os.getenv("STOCK_AGENT_OUTPUT_DIR", "outputs"))
FORECAST_SESSIONS = 30

OPENAI_API_KEY = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")


def ensure_api_key() -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "Chưa có OPEN_AI_KEY hoặc OPENAI_API_KEY trong .env"
        )
    return OPENAI_API_KEY
