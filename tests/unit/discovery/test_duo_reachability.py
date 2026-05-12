"""Unit tests for the Duo reachability probe."""

from __future__ import annotations

import httpx
import pytest

from dng_preflight.discovery import duo_reachability as duo_probe


async def test_probe_records_status_codes_and_errors(monkeypatch: pytest.MonkeyPatch):
    async def fake_head(self, url, **_kw):
        if "duo.com" in url:
            return httpx.Response(200)
        if "admin-d1" in url:
            raise httpx.ConnectError("dns failure")
        return httpx.Response(301)

    monkeypatch.setattr(httpx.AsyncClient, "head", fake_head)
    result = await duo_probe.probe()
    assert result.endpoints["https://duo.com"] == 200
    assert result.endpoints["https://api.duosecurity.com"] == 301
    assert result.endpoints["https://admin-d1.duosecurity.com"] == "connect_error"


async def test_probe_records_timeout_distinctly(monkeypatch: pytest.MonkeyPatch):
    async def fake_head(self, url, **_kw):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(httpx.AsyncClient, "head", fake_head)
    result = await duo_probe.probe()
    assert all(v == "connect_timeout" for v in result.endpoints.values())
