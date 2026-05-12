"""Unit tests for the time-sync probe."""

from __future__ import annotations

import pytest

from dng_preflight.discovery import time_sync as time_sync_probe
from dng_preflight.models.snapshot import NotDetected


def _fake_run(stdout: str, returncode: int = 0) -> object:
    class _R:
        pass

    r = _R()
    r.stdout = stdout
    r.returncode = returncode
    return r


def test_detect_daemon_finds_chronyd(monkeypatch: pytest.MonkeyPatch):
    def fake_which(name):
        return "/usr/bin/chronyc" if name == "chronyc" else None

    monkeypatch.setattr(time_sync_probe.shutil, "which", fake_which)
    monkeypatch.setattr(
        time_sync_probe.subprocess,
        "run",
        lambda *_a, **_kw: _fake_run("Reference ID    : ABCDEF (time.cloudflare.com)\n"),
    )
    daemon, source = time_sync_probe._detect_daemon()
    assert daemon == "chronyd"
    assert source is not None
    assert "ABCDEF" in source


def test_detect_daemon_falls_back_to_ntpd(monkeypatch: pytest.MonkeyPatch):
    def fake_which(name):
        return "/usr/bin/ntpq" if name == "ntpq" else None

    monkeypatch.setattr(time_sync_probe.shutil, "which", fake_which)
    monkeypatch.setattr(
        time_sync_probe.subprocess,
        "run",
        lambda *_a, **_kw: _fake_run("     remote\n=====\n*time.example  .GPS.   1\n"),
    )
    daemon, source = time_sync_probe._detect_daemon()
    assert daemon == "ntpd"
    assert source == "time.example"


def test_detect_daemon_returns_none_when_nothing_installed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(time_sync_probe.shutil, "which", lambda _x: None)
    daemon, source = time_sync_probe._detect_daemon()
    assert daemon == "none"
    assert source is None


async def test_probe_returns_not_detected_when_no_daemon_and_no_ntp(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(time_sync_probe, "_detect_daemon", lambda: ("none", None))
    monkeypatch.setattr(time_sync_probe, "_query_ntp_offset", lambda: None)
    result = await time_sync_probe.probe()
    assert isinstance(result, NotDetected)


async def test_probe_returns_state_when_offset_available(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        time_sync_probe, "_detect_daemon", lambda: ("chronyd", "time.cloudflare.com")
    )
    monkeypatch.setattr(time_sync_probe, "_query_ntp_offset", lambda: 0.034)
    result = await time_sync_probe.probe()
    assert not isinstance(result, NotDetected)
    assert result.daemon == "chronyd"
    assert result.offset_seconds == pytest.approx(0.034)
