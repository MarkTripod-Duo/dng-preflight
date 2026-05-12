"""questionary-backed answers provider for the CLI.

Translates each question into one or more questionary prompts, including the
per-strategy sub-prompts for `tls_strategy` and the load-balancer follow-ups.
The function lives here so the engine stays UI-agnostic and tests can swap in
a canned provider.
"""

from collections.abc import Mapping
from ipaddress import ip_network

import questionary

from dng_preflight.interview.questions import (
    DEPLOYMENT_SCOPE,
    IDP,
    INTERNAL_DNS,
    LOAD_BALANCER,
    PUBLIC_HOSTNAME,
    SEED_APPS,
    TLS_STRATEGY,
    WILDCARD_CERT,
    Question,
)
from dng_preflight.models.answers import (
    AppStub,
    ExistingBundle,
    InternalCa,
    LetsEncryptDns01,
    LoadBalancerConfig,
    SeedApps,
)
from dng_preflight.models.snapshot import EnvironmentSnapshot


def _ask_tls_strategy() -> ExistingBundle | LetsEncryptDns01 | InternalCa:
    kind = questionary.select(
        "TLS strategy:",
        choices=[
            questionary.Choice("Existing cert + key on disk", value="existing_bundle"),
            questionary.Choice("Let's Encrypt (DNS-01)", value="lets_encrypt_dns01"),
            questionary.Choice("Internal CA-signed cert", value="internal_ca"),
        ],
    ).unsafe_ask()
    if kind == "existing_bundle":
        cert = questionary.path("Cert file path:").unsafe_ask()
        key = questionary.path("Key file path:").unsafe_ask()
        chain = questionary.text("Chain file path (optional):").unsafe_ask() or None
        return ExistingBundle(cert_path=cert, key_path=key, chain_path=chain)
    if kind == "lets_encrypt_dns01":
        email = questionary.text("Contact email for Let's Encrypt:").unsafe_ask()
        provider = questionary.text("DNS provider (e.g. cloudflare, route53):").unsafe_ask()
        return LetsEncryptDns01(contact_email=email, dns_provider=provider)
    cert = questionary.path("Cert file path:").unsafe_ask()
    key = questionary.path("Key file path:").unsafe_ask()
    chain = questionary.path("Chain file path:").unsafe_ask()
    return InternalCa(cert_path=cert, key_path=key, chain_path=chain)


def _ask_load_balancer() -> LoadBalancerConfig | None:
    has_lb = questionary.confirm(
        "Is there a load balancer in front of DNG?", default=False
    ).unsafe_ask()
    if not has_lb:
        return None
    name = questionary.text("Load balancer name (e.g. nginx, haproxy, aws-alb):").unsafe_ask()
    raw = questionary.text(
        "Trusted proxy CIDRs (comma-separated, e.g. 10.0.0.0/8,192.168.1.0/24):",
    ).unsafe_ask()
    cidrs = [ip_network(s.strip(), strict=False) for s in raw.split(",") if s.strip()]
    return LoadBalancerConfig(name=name, trusted_proxies=cidrs)


def _ask_seed_apps(scope_is_rdp_smb: bool) -> SeedApps:
    web = int(questionary.text("How many web apps to stub?", default="0").unsafe_ask())
    ssh = int(questionary.text("How many SSH relay apps to stub?", default="0").unsafe_ask())
    rdp = (
        int(questionary.text("How many RDP relay apps to stub?", default="0").unsafe_ask())
        if scope_is_rdp_smb
        else 0
    )
    return SeedApps(
        web_apps=[AppStub(name=f"web-app-{i + 1}") for i in range(web)],
        ssh_relays=[AppStub(name=f"ssh-relay-{i + 1}") for i in range(ssh)],
        rdp_relays=[AppStub(name=f"rdp-relay-{i + 1}") for i in range(rdp)],
    )


def _select(question: Question) -> object:
    return questionary.select(
        question.prompt,
        choices=[questionary.Choice(c.label, value=c.value) for c in (question.choices or [])],
    ).unsafe_ask()


def questionary_provider(
    question: Question,
    snapshot: EnvironmentSnapshot,
    default: object,
    prior: Mapping[str, object],
) -> object:
    """Translate a question into questionary prompts and return the answer."""
    if question.id in (DEPLOYMENT_SCOPE.id, IDP.id, INTERNAL_DNS.id):
        return _select(question)
    if question.id == PUBLIC_HOSTNAME.id:
        return questionary.text(question.prompt, default=str(default or "")).unsafe_ask()
    if question.id == TLS_STRATEGY.id:
        return _ask_tls_strategy()
    if question.id == WILDCARD_CERT.id:
        return questionary.confirm(question.prompt, default=bool(default)).unsafe_ask()
    if question.id == LOAD_BALANCER.id:
        return _ask_load_balancer()
    if question.id == SEED_APPS.id:
        return _ask_seed_apps(scope_is_rdp_smb=prior.get("deployment_scope") == "web_ssh_rdp_smb")
    raise RuntimeError(f"no prompt handler for question id {question.id!r}")
