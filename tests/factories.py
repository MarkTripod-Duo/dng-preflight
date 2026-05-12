"""Shared builders for Phase 2 tests.

Centralised so per-test code stays focused on the behaviour under test rather
than on snapshot scaffolding.
"""

from __future__ import annotations

from ipaddress import IPv4Network

from dng_preflight.models.answers import (
    AppStub,
    ExistingBundle,
    InterviewAnswers,
    LoadBalancerConfig,
    SeedApps,
)
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


def make_snapshot(
    *,
    hostname: str = "dng.example.com",
    docker_detected: bool = True,
    domain_joined: bool = False,
    egress_public_ip: str | None = "203.0.113.10",
    interfaces: dict[str, list[str]] | None = None,
    firewall: FirewallState | NotDetected | None = None,
    time_offset_seconds: float | None = 0.012,
    a_records: dict[str, list[str]] | None = None,
) -> EnvironmentSnapshot:
    """Build a healthy Ubuntu-24.04-shaped snapshot. Keyword overrides knobs."""
    return EnvironmentSnapshot(
        captured_at="2026-05-12T12:00:00+00:00",
        hostname_planned=hostname,
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
            domain_joined=domain_joined,
        ),
        docker=(
            DockerInfo(
                engine_version="27.0.0",
                compose_version="2.27.0",
                daemon_reachable=True,
                current_user_in_docker_group=True,
            )
            if docker_detected
            else NotDetected(reason="docker CLI not found in PATH")
        ),
        network=NetworkInfo(
            interfaces=interfaces if interfaces is not None else {"eth0": ["10.0.0.5"]},
            default_route_iface="eth0",
            listening_ports={22: "sshd"},
            egress_public_ip=egress_public_ip,
        ),
        dns=DnsResolution(
            hostname=hostname,
            a_records=a_records if a_records is not None else {"1.1.1.1": ["203.0.113.10"]},
            aaaa_records={"1.1.1.1": []},
            reverse_ptr=None,
            local_resolvers=["127.0.0.53"],
        ),
        tls=TlsObservation(answers_on_443=False),
        time_sync=(
            TimeSyncState(
                daemon="chronyd",
                sync_source="time.cloudflare.com",
                offset_seconds=time_offset_seconds,
            )
            if time_offset_seconds is not None
            else NotDetected(reason="no time daemon")
        ),
        firewall=firewall
        if firewall is not None
        else FirewallState(kind=FirewallKind.UFW, active=True),
        duo_reachability=DuoReachability(endpoints={"https://duo.com": 200}),
    )


def make_answers(
    *,
    deployment_scope: str = "web_ssh",
    idp: str = "duo_sso",
    public_hostname: str = "dng.example.com",
    wildcard_cert: bool | None = None,
    load_balancer: LoadBalancerConfig | None = None,
    internal_dns: str = "internal_only",
    seed_apps: SeedApps | None = None,
) -> InterviewAnswers:
    """Build a valid `InterviewAnswers`. `wildcard_cert` auto-forced for RDP/SMB."""
    if wildcard_cert is None:
        wildcard_cert = deployment_scope == "web_ssh_rdp_smb"
    return InterviewAnswers.model_validate(
        {
            "deployment_scope": deployment_scope,
            "idp": idp,
            "public_hostname": public_hostname,
            "tls_strategy": ExistingBundle(
                cert_path="/etc/ssl/dng/cert.pem",
                key_path="/etc/ssl/dng/key.pem",
            ),
            "wildcard_cert": wildcard_cert,
            "load_balancer": load_balancer,
            "internal_dns": internal_dns,
            "seed_apps": seed_apps if seed_apps is not None else SeedApps(),
        }
    )


def lb(name: str = "nginx", cidr: str = "10.0.0.0/8") -> LoadBalancerConfig:
    """Convenience: a one-line LoadBalancerConfig for tests."""
    return LoadBalancerConfig(name=name, trusted_proxies=[IPv4Network(cidr)])


def stub_apps(*, web: int = 0, ssh: int = 0, rdp: int = 0) -> SeedApps:
    """Convenience: SeedApps with simple numbered stubs."""
    return SeedApps(
        web_apps=[AppStub(name=f"web-{i + 1}") for i in range(web)],
        ssh_relays=[AppStub(name=f"ssh-{i + 1}") for i in range(ssh)],
        rdp_relays=[AppStub(name=f"rdp-{i + 1}") for i in range(rdp)],
    )
