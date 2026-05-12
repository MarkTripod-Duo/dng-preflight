"""Unit tests for the DNS probe."""

from __future__ import annotations

import dns.exception
import dns.resolver
import pytest

from dng_preflight.discovery import dns as dns_probe


class _FakeRdata:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text

    def __str__(self) -> str:
        return self._text


class _FakeAnswer(list):
    pass


async def test_query_returns_sorted_records(monkeypatch: pytest.MonkeyPatch):
    class FakeResolver:
        def __init__(self, *_a, **_kw):
            self.nameservers: list[str] = []
            self.timeout = 0.0
            self.lifetime = 0.0

        async def resolve(self, _name, _rdtype):
            return _FakeAnswer([_FakeRdata("198.51.100.20"), _FakeRdata("198.51.100.10")])

    monkeypatch.setattr(dns_probe.dns.asyncresolver, "Resolver", FakeResolver)
    result = await dns_probe._query("dng.example.com", "A", "1.1.1.1")
    assert result == ["198.51.100.10", "198.51.100.20"]


async def test_query_returns_empty_on_nxdomain(monkeypatch: pytest.MonkeyPatch):
    class FakeResolver:
        def __init__(self, *_a, **_kw):
            self.nameservers: list[str] = []
            self.timeout = 0.0
            self.lifetime = 0.0

        async def resolve(self, _name, _rdtype):
            raise dns.resolver.NXDOMAIN

    monkeypatch.setattr(dns_probe.dns.asyncresolver, "Resolver", FakeResolver)
    assert await dns_probe._query("nope.example.com", "A", "1.1.1.1") == []


async def test_query_returns_empty_on_generic_dns_exception(monkeypatch: pytest.MonkeyPatch):
    class FakeResolver:
        def __init__(self, *_a, **_kw):
            self.nameservers: list[str] = []
            self.timeout = 0.0
            self.lifetime = 0.0

        async def resolve(self, _name, _rdtype):
            raise dns.exception.Timeout

    monkeypatch.setattr(dns_probe.dns.asyncresolver, "Resolver", FakeResolver)
    assert await dns_probe._query("dng.example.com", "A", "1.1.1.1") == []


async def test_probe_assembles_dns_resolution(monkeypatch: pytest.MonkeyPatch):
    async def fake_query(_h, rdtype, _ip):
        return ["198.51.100.10"] if rdtype == "A" else []

    async def fake_reverse(_ip):
        return "dng.example.com"

    monkeypatch.setattr(dns_probe, "_query", fake_query)
    monkeypatch.setattr(dns_probe, "_reverse_ptr", fake_reverse)
    monkeypatch.setattr(dns_probe, "_local_resolvers", lambda: ["127.0.0.53"])
    result = await dns_probe.probe("dng.example.com")
    assert result.hostname == "dng.example.com"
    assert all(v == ["198.51.100.10"] for v in result.a_records.values())
    assert all(v == [] for v in result.aaaa_records.values())
    assert result.reverse_ptr == "dng.example.com"
    assert result.local_resolvers == ["127.0.0.53"]
