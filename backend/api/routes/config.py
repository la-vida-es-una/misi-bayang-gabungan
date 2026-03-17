"""
Configuration REST endpoint.

Exposes read-only application settings to the frontend so it can display
the current simulation parameters.  Sensitive fields (MODEL_KEY) are
omitted from the response.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from config.settings import get_settings

router = APIRouter(prefix="/config", tags=["config"])

_REDACTED_FIELDS = {"MODEL_KEY"}
logger = logging.getLogger(__name__)


@router.get("")
async def get_config() -> dict:
    """Return current application settings (sensitive fields omitted)."""
    logger.debug("Configuration requested")
    settings = get_settings()
    return {
        key: value
        for key, value in settings.model_dump().items()
        if key not in _REDACTED_FIELDS
    }
