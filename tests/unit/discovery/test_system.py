"""Unit tests for the system probe."""

from __future__ import annotations

from pathlib import Path

import pytest

from dng_preflight.discovery import system as system_probe


def test_read_os_release_parses_quoted_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "os-release"
    fake.write_text("# comment\nID=ubuntu\nVERSION_ID=\"24.04\"\nPRETTY_NAME='Ubuntu 24.04 LTS'\n")
    monkeypatch.setattr(system_probe, "Path", lambda _p: fake)
    result = system_probe._read_os_release()
    assert result == {
        "ID": "ubuntu",
        "VERSION_ID": "24.04",
        "PRETTY_NAME": "Ubuntu 24.04 LTS",
    }


def test_read_os_release_returns_empty_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(system_probe, "Path", lambda _p: tmp_path / "does-not-exist")
    assert system_probe._read_os_release() == {}


def test_detect_domain_joined_false_when_no_realm_and_no_krb5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(system_probe.shutil, "which", lambda _x: None)
    monkeypatch.setattr(system_probe, "Path", lambda _p: tmp_path / "missing")
    assert system_probe._detect_domain_joined() is False


def test_detect_domain_joined_true_when_krb5_has_realm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    krb5 = tmp_path / "krb5.conf"
    krb5.write_text("[libdefaults]\ndefault_realm = EXAMPLE.COM\n[realms]\nEXAMPLE.COM = {\n}\n")
    monkeypatch.setattr(system_probe.shutil, "which", lambda _x: None)
    monkeypatch.setattr(system_probe, "Path", lambda _p: krb5)
    assert system_probe._detect_domain_joined() is True


async def test_probe_returns_system_info():
    """Smoke: the probe runs on the test host and returns a populated SystemInfo."""
    info = await system_probe.probe()
    assert info.detected is True
    assert info.platform != ""
    assert info.cpu_count >= 1
    assert info.ram_mb > 0
