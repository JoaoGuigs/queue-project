"""Shared async HTTP client for optional outbound calls (httpx).

Use this pattern for external services so the event loop is not blocked.
"""

from __future__ import annotations

import httpx


def create_async_client() -> httpx.AsyncClient:
    """Factory for a configured ``httpx.AsyncClient`` (timeouts, HTTP/2 optional)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))  # Timeout curto para não travar o loop
