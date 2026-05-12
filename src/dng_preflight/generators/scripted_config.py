"""Render `scripted-config.yaml` from a `DngConfig`.

Output conforms to the DNG 3.3.0+ scripted-config schema documented at
https://duo.com/docs/dng-scripted-config. Cert/key bodies are emitted as
`<<paste contents of …>>` placeholders so the operator can paste the real PEM
bodies before bring-up (DNG embeds PEM inline; we only ever held the paths).
"""

from __future__ import annotations

from dng_preflight.models.config import DngConfig
from dng_preflight.templates import env


def _domain_from_fqdn(fqdn: str) -> str:
    """Strip the leftmost label off `foo.bar.example.com` → `bar.example.com`."""
    parts = fqdn.split(".", 1)
    return parts[1] if len(parts) == 2 else fqdn


def generate(config: DngConfig) -> str:
    """Render the scripted-config YAML and return it as a string."""
    template = env().get_template("scripted-config.yaml.j2")
    return template.render(
        config=config,
        admin_email=f"admin@{_domain_from_fqdn(config.answers.public_hostname)}",
        public_hostname_domain=_domain_from_fqdn(config.answers.public_hostname),
        tls_kind=config.answers.tls_strategy.kind,
    )
