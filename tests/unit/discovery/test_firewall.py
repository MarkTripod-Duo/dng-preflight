"""Unit tests for the firewall probe."""

from __future__ import annotations

import pytest

from dng_preflight.discovery import firewall as firewall_probe
from dng_preflight.models.snapshot import FirewallKind


def _fake_run(stdout: str, returncode: int = 0) -> object:
    class _R:
        pass

    r = _R()
    r.stdout = stdout
    r.returncode = returncode
    return r


async def test_probe_detects_firewalld_running(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        firewall_probe.shutil,
        "which",
        lambda name: "/usr/bin/firewall-cmd" if name == "firewall-cmd" else None,
    )
    monkeypatch.setattr(firewall_probe.subprocess, "run", lambda *_a, **_kw: _fake_run("running\n"))
    result = await firewall_probe.probe()
    assert result.kind == FirewallKind.FIREWALLD
    assert result.active is True


async def test_probe_detects_ufw_active(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        firewall_probe.shutil, "which", lambda name: "/usr/sbin/ufw" if name == "ufw" else None
    )
    monkeypatch.setattr(
        firewall_probe.subprocess,
        "run",
        lambda *_a, **_kw: _fake_run(
            "Status: active\nTo                         Action      From\n"
        ),
    )
    result = await firewall_probe.probe()
    assert result.kind == FirewallKind.UFW
    assert result.active is True


async def test_probe_detects_ufw_inactive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        firewall_probe.shutil, "which", lambda name: "/usr/sbin/ufw" if name == "ufw" else None
    )
    monkeypatch.setattr(
        firewall_probe.subprocess, "run", lambda *_a, **_kw: _fake_run("Status: inactive\n")
    )
    result = await firewall_probe.probe()
    assert result.kind == FirewallKind.UFW
    assert result.active is False


async def test_probe_detects_iptables_with_rules(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        firewall_probe.shutil,
        "which",
        lambda name: "/usr/sbin/iptables" if name == "iptables" else None,
    )
    monkeypatch.setattr(
        firewall_probe.subprocess,
        "run",
        lambda *_a, **_kw: _fake_run(
            "-P INPUT ACCEPT\n-P OUTPUT ACCEPT\n-A INPUT -p tcp --dport 22 -j ACCEPT\n"
        ),
    )
    result = await firewall_probe.probe()
    assert result.kind == FirewallKind.IPTABLES
    assert result.active is True


async def test_probe_returns_none_when_no_firewall(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(firewall_probe.shutil, "which", lambda _x: None)
    result = await firewall_probe.probe()
    assert result.kind == FirewallKind.NONE
    assert result.active is False
