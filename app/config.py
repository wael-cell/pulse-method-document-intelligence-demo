"""
Application configuration.

Settings are plain defaults that can be overridden with environment variables.
No external credentials are required to run the demo: the "LLM" extraction step
is a deterministic local simulation, so every default below is safe and offline.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings(BaseModel):
    """Runtime configuration for the pipeline service."""

    app_name: str = Field(
        default="Technical Document Intelligence Pipeline",
        description="Human-readable service name.",
    )
    environment: str = Field(
        default=os.getenv("APP_ENV", "local-demo"),
        description="Deployment environment label (local-demo by default).",
    )
    log_level: str = Field(
        default=os.getenv("LOG_LEVEL", "INFO"),
        description="Root log level for the application logger.",
    )

    # Validation / review thresholds -------------------------------------------------
    min_field_confidence: float = Field(
        default=_env_float("MIN_FIELD_CONFIDENCE", 0.75),
        ge=0.0,
        le=1.0,
        description="Per-field confidence below this value is flagged for review.",
    )
    review_block_threshold: float = Field(
        default=_env_float("REVIEW_BLOCK_THRESHOLD", 0.60),
        ge=0.0,
        le=1.0,
        description="Document confidence below this routes the whole job to human review.",
    )
    max_simulated_latency_ms: int = Field(
        default=_env_int("MAX_SIMULATED_LATENCY_MS", 0),
        ge=0,
        description="Optional artificial delay (ms) to mimic async LLM/OCR latency in demos.",
    )

    # Ingestion limits ---------------------------------------------------------------
    max_document_bytes: int = Field(
        default=_env_int("MAX_DOCUMENT_BYTES", 2_000_000),
        gt=0,
        description="Reject uploads larger than this (raw text demo cap).",
    )
    supported_content_types: tuple[str, ...] = Field(
        default=("text/plain", "application/octet-stream", "text/markdown"),
        description="Accepted upload content types for the simulated OCR/text layer.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (FastAPI dependency-friendly)."""
    return Settings()
