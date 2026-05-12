"""Probe: HTTPS reachability of Duo Security's public service endpoints.

The customer's deployment-specific `api-XXXXXXXX.duosecurity.com` endpoint is
not known until the interview phase. Until then we probe Duo's documented
public reachability targets to confirm the host has outbound HTTPS to Duo.
"""

from __future__ import annotations

import httpx

from dng_preflight.models.snapshot import DuoReachability

_ENDPOINTS = (
    "https://duo.com",
    "https://api.duosecurity.com",
    "https://admin-d1.duosecurity.com",
)
_TIMEOUT_S = 4.0


async def _probe_one(client: httpx.AsyncClient, url: str) -> int | str:
    try:
        resp = await client.head(url, timeout=_TIMEOUT_S, follow_redirects=False)
    except httpx.ConnectTimeout:
        return "connect_timeout"
    except httpx.ReadTimeout:
        return "read_timeout"
    except httpx.ConnectError:
        return "connect_error"
    except httpx.HTTPError as exc:
        return f"http_error:{type(exc).__name__}"
    return resp.status_code


async def probe() -> DuoReachability:
    """HEAD each Duo service endpoint and record status or error string."""
    async with httpx.AsyncClient() as client:
        results: dict[str, int | str] = {}
        for url in _ENDPOINTS:
            results[url] = await _probe_one(client, url)
    return DuoReachability(endpoints=results)
