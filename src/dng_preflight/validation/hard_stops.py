"""Hard-stop validation rules from the build plan §9.

Each rule inspects a `DngConfig` and returns either `None` (rule passes) or a
`HardStop` describing the violation. `validate_plan()` runs every rule and
returns the surviving violations after applying user-supplied overrides.

Rules are intentionally pure functions over `DngConfig`. They never touch the
filesystem or network — discovery already did that, and the snapshot embedded
in the config is the source of truth.
"""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dng_preflight.models.config import DngConfig
from dng_preflight.models.snapshot import FirewallKind, NotDetected


class Severity(StrEnum):
    """Whether a violation can be skipped via override flag."""

    BLOCK = "block"
    """Cannot be overridden — generator must refuse."""

    OVERRIDABLE = "overridable"
    """May be skipped via the named override flag."""


class HardStop(BaseModel):
    """One violation, with a stable rule id for override-flag matching."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    message: str
    severity: Severity
    override_flag: str | None = None


_ADMIN_PORT_RULE = "admin_port_must_be_private"
_DOMAIN_JOINED_RULE = "host_must_not_be_domain_joined"
_WILDCARD_RDP_SMB_RULE = "wildcard_required_for_rdp_smb"
_TIME_OFFSET_RULE = "time_offset_within_30s"
_DNG_VERSION_RULE = "dng_version_minimum"
_LB_TRUSTED_PROXIES_RULE = "lb_requires_trusted_proxies"
_HOSTNAME_RESOLVES_RULE = "public_hostname_must_resolve"


def _check_admin_port(config: DngConfig) -> HardStop | None:
    """Rule 1: 8443 must not be reachable from the public Internet.

    Heuristic for MVP: if the host's egress public IP is also bound to one of
    its interfaces (i.e. the host has a directly-routable public address) AND
    no host firewall is active, treat 8443 as exposed.
    """
    snapshot = config.snapshot
    egress = snapshot.network.egress_public_ip
    if egress is None:
        return None
    interface_ips = {ip for ips in snapshot.network.interfaces.values() for ip in ips}
    if egress not in interface_ips:
        return None
    firewall = snapshot.firewall
    firewall_blocks = (
        not isinstance(firewall, NotDetected)
        and firewall.active
        and firewall.kind is not FirewallKind.NONE
    )
    if firewall_blocks:
        return None
    return HardStop(
        rule=_ADMIN_PORT_RULE,
        message=(
            "Host has a publicly-routable interface and no active firewall; "
            "DNG admin console on 8443 would be Internet-facing."
        ),
        severity=Severity.OVERRIDABLE,
        override_flag="--allow-public-admin",
    )


def _check_domain_joined(config: DngConfig) -> HardStop | None:
    """Rule 2: host must not be domain-joined."""
    if not config.snapshot.system.domain_joined:
        return None
    return HardStop(
        rule=_DOMAIN_JOINED_RULE,
        message=(
            "Host appears to be domain-joined (realm list or /etc/krb5.conf "
            "indicates a Kerberos realm). DNG must run on a non-domain-joined host."
        ),
        severity=Severity.OVERRIDABLE,
        override_flag="--allow-domain-joined",
    )


def _check_wildcard_for_rdp_smb(config: DngConfig) -> HardStop | None:
    """Rule 3: scope including RDP/SMB requires a wildcard cert."""
    answers = config.answers
    if answers.deployment_scope != "web_ssh_rdp_smb":
        return None
    if answers.wildcard_cert:
        return None
    return HardStop(
        rule=_WILDCARD_RDP_SMB_RULE,
        message=(
            "Deployment scope includes RDP/SMB but wildcard_cert is False. "
            "Resolve by enabling wildcard_cert or narrowing the scope."
        ),
        severity=Severity.BLOCK,
    )


def _check_time_offset(config: DngConfig) -> HardStop | None:
    """Rule 4: time offset from NTP must be ≤ 30 seconds (SAML signature window)."""
    ts = config.snapshot.time_sync
    if isinstance(ts, NotDetected):
        return None
    if ts.offset_seconds is None:
        return None
    if abs(ts.offset_seconds) <= 30.0:
        return None
    return HardStop(
        rule=_TIME_OFFSET_RULE,
        message=(
            f"Host clock is {ts.offset_seconds:+.1f}s off from {ts.sync_source!r}; "
            f"SAML signatures will fail outside ±30s."
        ),
        severity=Severity.OVERRIDABLE,
        override_flag="--skip-time-check",
    )


def _check_dng_version(config: DngConfig) -> HardStop | None:
    """Rule 5: DNG version floor is non-negotiable for MVP."""
    floor = tuple(int(p) for p in config.dng_version_minimum.split("."))
    if floor >= (3, 3, 0):
        return None
    return HardStop(
        rule=_DNG_VERSION_RULE,
        message=(
            f"dng_version_minimum {config.dng_version_minimum!r} is below the "
            f"3.3.0 floor required for the April 15, 2026 CA bundle cutoff."
        ),
        severity=Severity.BLOCK,
    )


def _check_lb_trusted_proxies(config: DngConfig) -> HardStop | None:
    """Rule 6: load_balancer set ⇒ trusted_proxies non-empty.

    The `LoadBalancerConfig` model already enforces `min_length=1`, so this
    rule mostly exists for plans hand-edited after `plan --save`.
    """
    lb = config.answers.load_balancer
    if lb is None:
        return None
    if lb.trusted_proxies:
        return None
    return HardStop(
        rule=_LB_TRUSTED_PROXIES_RULE,
        message="load_balancer is configured but trusted_proxies is empty.",
        severity=Severity.BLOCK,
    )


def _check_public_hostname_resolves(config: DngConfig) -> HardStop | None:
    """Rule 7: at least one authoritative resolver must return A or AAAA records."""
    dns = config.snapshot.dns
    if any(dns.a_records.values()) or any(dns.aaaa_records.values()):
        return None
    return HardStop(
        rule=_HOSTNAME_RESOLVES_RULE,
        message=(
            f"No authoritative resolver returned A or AAAA records for "
            f"{config.answers.public_hostname!r}. Runbook must include DNS "
            f"setup as Step 0."
        ),
        severity=Severity.BLOCK,
    )


_ALL_CHECKS: tuple[Callable[[DngConfig], HardStop | None], ...] = (
    _check_admin_port,
    _check_domain_joined,
    _check_wildcard_for_rdp_smb,
    _check_time_offset,
    _check_dng_version,
    _check_lb_trusted_proxies,
    _check_public_hostname_resolves,
)


def validate_plan(config: DngConfig, *, overrides: frozenset[str] = frozenset()) -> list[HardStop]:
    """Run every hard-stop rule and return surviving violations.

    `overrides` is a set of override flag strings (e.g. `{"--skip-time-check"}`).
    Violations whose `override_flag` is in `overrides` are dropped from the
    result. Non-overridable violations (severity `BLOCK`) cannot be dropped.
    """
    out: list[HardStop] = []
    for check in _ALL_CHECKS:
        result = check(config)
        if result is None:
            continue
        if (
            result.severity is Severity.OVERRIDABLE
            and result.override_flag is not None
            and result.override_flag in overrides
        ):
            continue
        out.append(result)
    return out
