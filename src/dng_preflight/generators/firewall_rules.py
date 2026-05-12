"""Render `firewall.sh` from a `DngConfig`.

Template selection is driven by the detected host firewall: `ufw` and
`firewalld` are the two MVP-supported kinds (build plan §4). Anything else
(iptables raw, none, NotDetected) gets a stub script that prints manual
guidance — generation never silently emits the wrong commands.
"""

from __future__ import annotations

from dng_preflight.models.config import DngConfig
from dng_preflight.models.snapshot import FirewallKind, NotDetected
from dng_preflight.templates import env


def _detected_kind(config: DngConfig) -> str:
    fw = config.snapshot.firewall
    if isinstance(fw, NotDetected):
        return "not_detected"
    return fw.kind.value


def _template_name(detected: str) -> str:
    if detected == FirewallKind.UFW.value:
        return "firewall-ufw.sh.j2"
    if detected == FirewallKind.FIREWALLD.value:
        return "firewall-firewalld.sh.j2"
    return "firewall-unsupported.sh.j2"


def generate(config: DngConfig) -> str:
    """Pick the right firewall template and render it."""
    detected = _detected_kind(config)
    template = env().get_template(_template_name(detected))
    admin_cidrs: list[str] = []
    if config.answers.load_balancer is not None:
        admin_cidrs = [str(c) for c in config.answers.load_balancer.trusted_proxies]
    return template.render(
        config=config,
        detected_firewall=detected,
        admin_cidrs=admin_cidrs,
    )
