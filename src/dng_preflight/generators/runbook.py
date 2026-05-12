"""Render `RUNBOOK.md` from a `DngConfig`.

Step ordering is the build plan's "break the SAML circular dependency" recipe:
bring DNG up with placeholder primary_auth, export SP metadata, configure
IdP, import IdP metadata, restart, first-login password reset.
"""

from __future__ import annotations

from dng_preflight import __version__
from dng_preflight.models.config import DngConfig
from dng_preflight.templates import env


def generate(config: DngConfig) -> str:
    """Render the markdown runbook and return it as a string."""
    template = env().get_template("runbook.md.j2")
    dns = config.snapshot.dns
    resolved = any(dns.a_records.values()) or any(dns.aaaa_records.values())
    lb = config.answers.load_balancer
    return template.render(
        config=config,
        tool_version=__version__,
        tls_kind=config.answers.tls_strategy.kind,
        needs_dns_step_zero=not resolved,
        hostname_resolves_status="✓" if resolved else "override applied",
        lb_cidrs=", ".join(str(c) for c in lb.trusted_proxies) if lb else "",
    )
