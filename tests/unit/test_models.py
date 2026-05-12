"""Pydantic model behaviour, discriminated unions, and YAML round-trip."""

import pytest
import yaml
from pydantic import ValidationError

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


def _minimal_snapshot(*, docker_detected: bool = True) -> EnvironmentSnapshot:
    docker = (
        DockerInfo(
            engine_version="27.0.0",
            compose_version="2.27.0",
            daemon_reachable=True,
            current_user_in_docker_group=True,
        )
        if docker_detected
        else NotDetected(reason="docker CLI not found in PATH")
    )
    return EnvironmentSnapshot(
        captured_at="2026-05-12T12:00:00+00:00",
        hostname_planned="dng.example.com",
        system=SystemInfo(
            platform="linux",
            distro="ubuntu",
            distro_version="24.04",
            kernel="6.8.0-31-generic",
            arch="x86_64",
            ram_mb=8192,
            cpu_count=4,
            selinux_mode=None,
            apparmor_active=True,
            domain_joined=False,
        ),
        docker=docker,
        network=NetworkInfo(
            interfaces={"eth0": ["10.0.0.5"]},
            default_route_iface="eth0",
            listening_ports={22: "sshd"},
            egress_public_ip="203.0.113.10",
        ),
        dns=DnsResolution(
            hostname="dng.example.com",
            a_records={"1.1.1.1": ["203.0.113.10"]},
            aaaa_records={"1.1.1.1": []},
            reverse_ptr=None,
            local_resolvers=["127.0.0.53"],
        ),
        tls=TlsObservation(answers_on_443=False),
        time_sync=TimeSyncState(
            daemon="chronyd", sync_source="time.cloudflare.com", offset_seconds=0.012
        ),
        firewall=FirewallState(kind=FirewallKind.UFW, active=True),
        duo_reachability=DuoReachability(endpoints={"https://duo.com": 200}),
    )


def test_not_detected_is_frozen():
    nd = NotDetected(reason="docker missing")
    with pytest.raises(ValidationError):
        nd.reason = "changed"  # type: ignore[misc]


def test_discriminator_disambiguates_docker_union():
    snap = _minimal_snapshot(docker_detected=False)
    dumped = snap.model_dump(mode="json")
    rehydrated = EnvironmentSnapshot.model_validate(dumped)
    assert isinstance(rehydrated.docker, NotDetected)
    assert rehydrated.docker.reason == "docker CLI not found in PATH"


def test_yaml_roundtrip_preserves_equality():
    snap = _minimal_snapshot()
    text = yaml.safe_dump(snap.model_dump(mode="json"), sort_keys=False)
    loaded = yaml.safe_load(text)
    rehydrated = EnvironmentSnapshot.model_validate(loaded)
    assert rehydrated == snap


def test_yaml_roundtrip_with_not_detected_branches():
    snap = _minimal_snapshot(docker_detected=False)
    text = yaml.safe_dump(snap.model_dump(mode="json"), sort_keys=False)
    rehydrated = EnvironmentSnapshot.model_validate(yaml.safe_load(text))
    assert rehydrated == snap


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        NotDetected(reason="x", surprise=True)  # type: ignore[call-arg]


def test_firewall_kind_enum_roundtrips_as_string():
    fw = FirewallState(kind=FirewallKind.FIREWALLD, active=True)
    dumped = fw.model_dump(mode="json")
    assert dumped["kind"] == "firewalld"
    assert FirewallState.model_validate(dumped) == fw
