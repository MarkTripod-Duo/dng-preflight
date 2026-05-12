"""Probe: detect the active host firewall (firewalld, ufw, iptables, or none)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

from dng_preflight.models.snapshot import FirewallKind, FirewallState, NotDetected

_TIMEOUT_S = 3


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(  # noqa: S603 - cmd[0] resolved via shutil.which upstream
            cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except (subprocess.SubprocessError, OSError):
        return -1, ""
    return result.returncode, result.stdout.strip()


def _probe_firewalld() -> FirewallState | None:
    bin_path = shutil.which("firewall-cmd")
    if bin_path is None:
        return None
    code, out = _run([bin_path, "--state"])
    active = code == 0 and out.lower().startswith("running")
    return FirewallState(kind=FirewallKind.FIREWALLD, active=active)


def _probe_ufw() -> FirewallState | None:
    bin_path = shutil.which("ufw")
    if bin_path is None:
        return None
    code, out = _run([bin_path, "status"])
    if code != 0:
        return None
    active = "Status: active" in out
    return FirewallState(kind=FirewallKind.UFW, active=active)


_IPTABLES_DEFAULT_ACCEPT = (
    "-P INPUT ACCEPT",
    "-P OUTPUT ACCEPT",
    "-P FORWARD ACCEPT",
)


def _probe_iptables() -> FirewallState | None:
    bin_path = shutil.which("iptables")
    if bin_path is None:
        return None
    code, out = _run([bin_path, "-S"])
    if code != 0:
        return None
    rules = [
        line
        for line in out.splitlines()
        if line.strip() and not line.startswith(_IPTABLES_DEFAULT_ACCEPT)
    ]
    return FirewallState(kind=FirewallKind.IPTABLES, active=bool(rules))


def _collect_sync() -> FirewallState | NotDetected:
    for probe_fn in (_probe_firewalld, _probe_ufw, _probe_iptables):
        result = probe_fn()
        if result is not None:
            return result
    return FirewallState(kind=FirewallKind.NONE, active=False)


async def probe() -> FirewallState | NotDetected:
    """Identify the active host firewall, falling back to NONE when none is found."""
    return await asyncio.to_thread(_collect_sync)
