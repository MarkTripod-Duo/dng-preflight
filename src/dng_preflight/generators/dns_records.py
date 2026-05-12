"""Render `dns-records.md` and `dns-records.json` from a `DngConfig`.

Both files describe the same record set; the markdown form is for humans
(TTL guidance, verification commands) and the JSON form is for downstream
automation. Includes `_acme-challenge` TXT placeholders when the TLS strategy
is Let's Encrypt DNS-01.
"""

from __future__ import annotations

import json
from typing import Any

from dng_preflight.models.config import DngConfig
from dng_preflight.templates import env


def _domain_from_fqdn(fqdn: str) -> str:
    parts = fqdn.split(".", 1)
    return parts[1] if len(parts) == 2 else fqdn


def _resolved_ips(config: DngConfig) -> list[str]:
    """Collect IPs from snapshot.dns that any resolver returned."""
    ips: list[str] = []
    for records in config.snapshot.dns.a_records.values():
        for ip in records:
            if ip not in ips:
                ips.append(ip)
    return ips


def _seed_app_hostnames(config: DngConfig) -> list[str]:
    """Concatenate web + ssh + rdp stub names for the DNS table."""
    apps = config.answers.seed_apps
    return [a.name for a in (*apps.web_apps, *apps.ssh_relays, *apps.rdp_relays)]


def generate_md(config: DngConfig) -> str:
    """Render the human-readable DNS records markdown."""
    template = env().get_template("dns-records.md.j2")
    return template.render(
        config=config,
        public_hostname_domain=_domain_from_fqdn(config.answers.public_hostname),
        tls_kind=config.answers.tls_strategy.kind,
        base_ips=_resolved_ips(config),
        seed_app_hostnames=_seed_app_hostnames(config),
    )


def generate_json(config: DngConfig) -> str:
    """Render the machine-readable DNS records as a JSON document."""
    domain = _domain_from_fqdn(config.answers.public_hostname)
    base_ips = _resolved_ips(config)
    target_value = base_ips[0] if base_ips else "<set to DNG host public IP>"

    records: list[dict[str, Any]] = [
        {"type": "A", "name": config.answers.public_hostname, "value": target_value, "ttl": 300},
    ]
    if config.answers.wildcard_cert:
        records.append({"type": "A", "name": f"*.{domain}", "value": target_value, "ttl": 300})
    if config.answers.tls_strategy.kind == "lets_encrypt_dns01":
        records.append(
            {
                "type": "TXT",
                "name": f"_acme-challenge.{config.answers.public_hostname}",
                "value": "<set by ACME client>",
                "ttl": 60,
            }
        )
        if config.answers.wildcard_cert:
            records.append(
                {
                    "type": "TXT",
                    "name": f"_acme-challenge.{domain}",
                    "value": "<set by ACME client for wildcard>",
                    "ttl": 60,
                }
            )
    for hostname in _seed_app_hostnames(config):
        records.append(
            {
                "type": "A",
                "name": f"{hostname}.{domain}",
                "value": target_value,
                "ttl": 300,
            }
        )
    payload = {
        "hostname": config.answers.public_hostname,
        "wildcard": config.answers.wildcard_cert,
        "tls_strategy": config.answers.tls_strategy.kind,
        "records": records,
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"
