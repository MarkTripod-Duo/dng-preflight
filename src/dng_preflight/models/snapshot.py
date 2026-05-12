"""EnvironmentSnapshot and its sub-models.

The snapshot is the output of the discovery phase. Each probe contributes one
sub-model. Probes that depend on missing tooling (e.g. Docker not installed)
emit a `NotDetected` sentinel rather than `None`, so callers can distinguish
"the tool isn't here" from "the tool reported a zero / empty value".

YAML round-trip is supported: `EnvironmentSnapshot.model_dump(mode="json")`
followed by `yaml.safe_dump` produces input that `yaml.safe_load` +
`EnvironmentSnapshot.model_validate` rehydrates to an equal instance.
Discriminated unions (`detected: Literal[True] | Literal[False]`) keep the
round-trip deterministic.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class FirewallKind(StrEnum):
    """Recognised host firewall implementations."""

    FIREWALLD = "firewalld"
    UFW = "ufw"
    IPTABLES = "iptables"
    NONE = "none"


class NotDetected(BaseModel):
    """Sentinel returned by a probe when its required tooling is absent.

    Always carries a short human-readable `reason` so the runbook can explain
    why a sub-model is empty (e.g. "docker CLI not found in PATH").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[False] = False
    reason: str


class SystemInfo(BaseModel):
    """Host OS, hardware, and security-mode facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    platform: str
    distro: str
    distro_version: str
    kernel: str
    arch: str
    ram_mb: int
    cpu_count: int
    selinux_mode: str | None = None
    apparmor_active: bool | None = None
    domain_joined: bool = False


class DockerInfo(BaseModel):
    """Docker Engine and Compose plugin presence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    engine_version: str
    compose_version: str | None
    daemon_reachable: bool
    current_user_in_docker_group: bool


class NetworkInfo(BaseModel):
    """Local network: interfaces, listening ports, egress IP."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    interfaces: dict[str, list[str]]
    default_route_iface: str | None
    listening_ports: dict[int, str]
    egress_public_ip: str | None


class DnsResolution(BaseModel):
    """Authoritative DNS lookup results for the planned hostname."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    hostname: str
    a_records: dict[str, list[str]]
    aaaa_records: dict[str, list[str]]
    reverse_ptr: str | None
    local_resolvers: list[str]


class TlsObservation(BaseModel):
    """TLS certificate observed on the host's port 443, if anything answers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    answers_on_443: bool
    cn: str | None = None
    sans: list[str] = Field(default_factory=list)
    not_before: str | None = None
    not_after: str | None = None
    issuer: str | None = None
    key_algorithm: str | None = None


class TimeSyncState(BaseModel):
    """Time-sync daemon state and offset from pool.ntp.org."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    daemon: str
    sync_source: str | None
    offset_seconds: float | None


class FirewallState(BaseModel):
    """Active host firewall and its enabled/disabled status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    kind: FirewallKind
    active: bool


class DuoReachability(BaseModel):
    """HTTP HEAD probe results against api-*.duosecurity.com endpoints.

    `endpoints` maps URL → HTTP status code (int) on success, or a short error
    string (e.g. "timeout", "dns_failure") on failure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    detected: Literal[True] = True
    endpoints: dict[str, int | str]


DockerInfoOrMissing = Annotated[DockerInfo | NotDetected, Field(discriminator="detected")]
FirewallStateOrMissing = Annotated[FirewallState | NotDetected, Field(discriminator="detected")]
TimeSyncStateOrMissing = Annotated[TimeSyncState | NotDetected, Field(discriminator="detected")]


class EnvironmentSnapshot(BaseModel):
    """Full output of the discovery phase. Round-trips through YAML losslessly."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    captured_at: str
    hostname_planned: str
    system: SystemInfo
    docker: DockerInfoOrMissing
    network: NetworkInfo
    dns: DnsResolution
    tls: TlsObservation
    time_sync: TimeSyncStateOrMissing
    firewall: FirewallStateOrMissing
    duo_reachability: DuoReachability
