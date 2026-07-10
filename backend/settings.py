"""Klarify runtime settings."""

from __future__ import annotations

import os


def zero_retention_enabled() -> bool:
    return os.getenv("KLARIFY_ZERO_RETENTION", "true").lower() in ("1", "true", "yes")
