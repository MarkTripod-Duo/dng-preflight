"""Unit tests for the network probe."""

from __future__ import annotations

import socket
from collections import namedtuple
from unittest.mock import AsyncMock

import httpx
import pytest

from dng_preflight.discovery import network as network_probe

_FakeAddr = namedtuple("_FakeAddr", "family address")
_FakeConn = namedtuple("_FakeConn", "laddr status pid")


def test_interfaces_filters_to_inet_addresses(monkeypatch: pytest.MonkeyPatch):
    fake_family = type("F", (), {"name": "AF_INET"})()
    fake_link = type("F", (), {"name": "AF_LINK"})()
    monkeypatch.setattr(
        network_probe.psutil,
        "net_if_addrs",
        lambda: {
            "eth0": [_FakeAddr(fake_family, "10.0.0.5"), _FakeAddr(fake_link, "aa:bb:cc:dd:ee:ff")],
            "lo": [_FakeAddr(fake_family, "127.0.0.1")],
        },
    )
    result = network_probe._interfaces()
    assert result == {"eth0": ["10.0.0.5"], "lo": ["127.0.0.1"]}


def test_listening_ports_filters_to_relevant_set(monkeypatch: pytest.MonkeyPatch):
    laddr80 = type("L", (), {"port": 80})()
    laddr8443 = type("L", (), {"port": 8443})()
    laddr22 = type("L", (), {"port": 22})()
    monkeypatch.setattr(network_probe.psutil, "CONN_LISTEN", "LISTEN")
    monkeypatch.setattr(
        network_probe.psutil,
        "net_connections",
        lambda kind: [
            _FakeConn(laddr80, "LISTEN", None),
            _FakeConn(laddr22, "LISTEN", None),
            _FakeConn(laddr8443, "LISTEN", 12345),
        ],
    )

    class FakeProc:
        def name(self):
            return "nginx"

    monkeypatch.setattr(network_probe.psutil, "Process", lambda _pid: FakeProc())
    result = network_probe._listening_ports()
    assert 22 not in result
    assert result[80] == "unknown"
    assert result[8443] == "nginx"


async def test_egress_public_ip_uses_first_successful(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def fake_get(self, url, **_kw):
        calls.append(url)
        if "ipify" in url:
            raise httpx.ConnectError("nope")
        return httpx.Response(200, text="203.0.113.10\n")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    async with httpx.AsyncClient() as client:
        ip = await network_probe._egress_public_ip(client)
    assert ip == "203.0.113.10"
    # ipify tried first, then ifconfig.me succeeded
    assert "ipify" in calls[0]
    assert len(calls) >= 2


async def test_egress_public_ip_returns_none_when_all_fail(monkeypatch: pytest.MonkeyPatch):
    async def always_fail(self, url, **_kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx.AsyncClient, "get", always_fail)
    async with httpx.AsyncClient() as client:
        ip = await network_probe._egress_public_ip(client)
    assert ip is None


async def test_probe_assembles_network_info(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(network_probe, "_interfaces", lambda: {"eth0": ["10.0.0.5"]})
    monkeypatch.setattr(network_probe, "_default_route_iface", lambda: "eth0")
    monkeypatch.setattr(network_probe, "_listening_ports", lambda: {443: "nginx"})
    monkeypatch.setattr(network_probe, "_egress_public_ip", AsyncMock(return_value="203.0.113.10"))
    info = await network_probe.probe()
    assert info.interfaces == {"eth0": ["10.0.0.5"]}
    assert info.default_route_iface == "eth0"
    assert info.listening_ports == {443: "nginx"}
    assert info.egress_public_ip == "203.0.113.10"


# socket is imported only to keep `from __future__` happy when running under ty
_ = socket  # noqa: B018 - intentional import-only side effect
