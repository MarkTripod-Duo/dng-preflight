"""Unit tests for the discovery aggregator."""

from __future__ import annotations

import asyncio

import pytest

from dng_preflight.discovery import aggregator
from dng_preflight.models.snapshot import (
    DnsResolution,
    DockerInfo,
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


def _patch_probes(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    async def _system():
        return overrides.get(
            "system",
            SystemInfo(
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
        )

    async def _docker():
        return overrides.get(
            "docker",
            DockerInfo(
                engine_version="27.0.0",
                compose_version="v2.27.0",
                daemon_reachable=True,
                current_user_in_docker_group=True,
            ),
        )

    async def _network():
        return overrides.get(
            "network",
            NetworkInfo(
                interfaces={"eth0": ["10.0.0.5"]},
                default_route_iface="eth0",
                listening_ports={},
                egress_public_ip="203.0.113.10",
            ),
        )

    async def _dns(_h):
        return overrides.get(
            "dns",
            DnsResolution(
                hostname="dng.example.com",
                a_records={"1.1.1.1": ["203.0.113.10"]},
                aaaa_records={"1.1.1.1": []},
                reverse_ptr=None,
                local_resolvers=[],
            ),
        )

    async def _tls():
        return overrides.get("tls", TlsObservation(answers_on_443=False))

    async def _time_sync():
        return overrides.get(
            "time_sync",
            TimeSyncState(daemon="chronyd", sync_source="time.cloudflare.com", offset_seconds=0.01),
        )

    async def _firewall():
        return overrides.get(
            "firewall",
            FirewallState(kind=FirewallKind.UFW, active=True),
        )

    async def _duo():
        return overrides.get(
            "duo",
            DuoReachability(endpoints={"https://duo.com": 200}),
        )

    monkeypatch.setattr(aggregator.system_probe, "probe", _system)
    monkeypatch.setattr(aggregator.docker_probe, "probe", _docker)
    monkeypatch.setattr(aggregator.network_probe, "probe", _network)
    monkeypatch.setattr(aggregator.dns_probe, "probe", _dns)
    monkeypatch.setattr(aggregator.tls_probe, "probe", _tls)
    monkeypatch.setattr(aggregator.time_sync_probe, "probe", _time_sync)
    monkeypatch.setattr(aggregator.firewall_probe, "probe", _firewall)
    monkeypatch.setattr(aggregator.duo_probe, "probe", _duo)


async def test_collect_assembles_snapshot(monkeypatch: pytest.MonkeyPatch):
    _patch_probes(monkeypatch)
    snap = await aggregator.collect("dng.example.com")
    assert isinstance(snap, EnvironmentSnapshot)
    assert snap.hostname_planned == "dng.example.com"
    assert snap.system.distro == "ubuntu"
    assert isinstance(snap.docker, DockerInfo)
    assert isinstance(snap.firewall, FirewallState)


async def test_optional_probe_timeout_downgrades_to_not_detected(monkeypatch: pytest.MonkeyPatch):
    _patch_probes(monkeypatch)

    async def hanging():
        await asyncio.sleep(30)
        raise AssertionError("should have been cancelled")

    monkeypatch.setattr(aggregator.docker_probe, "probe", hanging)
    monkeypatch.setattr(aggregator, "_PER_PROBE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(aggregator, "_TOTAL_BUDGET_S", 5.0)
    snap = await aggregator.collect("dng.example.com")
    assert isinstance(snap.docker, NotDetected)
    assert "timeout" in snap.docker.reason.lower()


async def test_required_probe_timeout_raises(monkeypatch: pytest.MonkeyPatch):
    _patch_probes(monkeypatch)

    async def hanging():
        await asyncio.sleep(30)
        raise AssertionError("should have been cancelled")

    monkeypatch.setattr(aggregator.tls_probe, "probe", hanging)
    monkeypatch.setattr(aggregator, "_PER_PROBE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(aggregator, "_TOTAL_BUDGET_S", 5.0)
    with pytest.raises((TimeoutError, BaseExceptionGroup)):
        await aggregator.collect("dng.example.com")
