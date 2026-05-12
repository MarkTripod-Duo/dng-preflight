"""Unit tests for the dng-preflight CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from dng_preflight import cli as cli_module
from dng_preflight.models.snapshot import (
    DnsResolution,
    DuoReachability,
    EnvironmentSnapshot,
    FirewallKind,
    FirewallState,
    NetworkInfo,
    NotDetected,
    SystemInfo,
    TimeSyncState,
    TlsObservation,
)


def _stub_snapshot() -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        captured_at="2026-05-12T12:00:00+00:00",
        hostname_planned="dng.example.com",
        system=SystemInfo(
            platform="linux",
            distro="ubuntu",
            distro_version="24.04",
            kernel="6.8.0",
            arch="x86_64",
            ram_mb=4096,
            cpu_count=2,
            selinux_mode=None,
            apparmor_active=True,
            domain_joined=False,
        ),
        docker=NotDetected(reason="docker CLI not found in PATH"),
        network=NetworkInfo(
            interfaces={"eth0": ["10.0.0.5"]},
            default_route_iface="eth0",
            listening_ports={},
            egress_public_ip="203.0.113.10",
        ),
        dns=DnsResolution(
            hostname="dng.example.com",
            a_records={"1.1.1.1": []},
            aaaa_records={"1.1.1.1": []},
            reverse_ptr=None,
            local_resolvers=[],
        ),
        tls=TlsObservation(answers_on_443=False),
        time_sync=TimeSyncState(daemon="chronyd", sync_source="x", offset_seconds=0.0),
        firewall=FirewallState(kind=FirewallKind.UFW, active=True),
        duo_reachability=DuoReachability(endpoints={"https://duo.com": 200}),
    )


@pytest.fixture
def patched_collect(monkeypatch: pytest.MonkeyPatch):
    async def _fake_collect(_hostname: str) -> EnvironmentSnapshot:
        return _stub_snapshot()

    monkeypatch.setattr(cli_module, "collect", _fake_collect)


def test_inspect_emits_yaml_by_default(patched_collect):
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["inspect", "--hostname", "dng.example.com"])
    assert result.exit_code == 0, result.output
    parsed = yaml.safe_load(result.output)
    assert parsed["hostname_planned"] == "dng.example.com"
    assert parsed["docker"]["detected"] is False


def test_inspect_emits_json_when_requested(patched_collect):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["inspect", "--hostname", "dng.example.com", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["docker"]["detected"] is False


def test_inspect_writes_to_output_file(patched_collect, tmp_path: Path):
    target = tmp_path / "snap.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["inspect", "--hostname", "dng.example.com", "--output", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert target.exists()
    parsed = yaml.safe_load(target.read_text())
    assert parsed["hostname_planned"] == "dng.example.com"


def test_inspect_requires_hostname():
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["inspect"])
    assert result.exit_code != 0
    assert "hostname" in result.output.lower() or "missing" in result.output.lower()
