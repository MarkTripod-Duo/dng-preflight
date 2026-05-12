"""InterviewAnswers and supporting types — output of the interview phase.

Each field captures one decision the interview engine collected. The schema is
strict (`extra="forbid"`) and frozen so callers can hash and safely share
instances across generators.

The `tls_strategy` field is a discriminated union with three concrete
implementations — `ExistingBundle`, `LetsEncryptDns01`, `InternalCa` — keyed
on `kind`. This is the same pattern Phase 1 uses for "detected vs. missing"
sub-models in `EnvironmentSnapshot`, so YAML round-trip is deterministic.
"""

from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

DeploymentScope = Literal["web_ssh", "web_ssh_rdp_smb"]
"""Which DNG compose variant the user wants to deploy."""

IdpKind = Literal["duo_sso", "okta", "entra_id", "adfs", "generic_saml"]
"""SAML 2.0 IdP options supported by MVP."""

InternalDnsTopology = Literal["split_horizon", "internal_only", "none"]
"""How the host's internal DNS view relates to public DNS."""


class ExistingBundle(BaseModel):
    """User supplies a pre-issued cert/key bundle on the local filesystem."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["existing_bundle"] = "existing_bundle"
    cert_path: str
    key_path: str
    chain_path: str | None = None


class LetsEncryptDns01(BaseModel):
    """Let's Encrypt with the DNS-01 challenge (MVP does not support HTTP-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["lets_encrypt_dns01"] = "lets_encrypt_dns01"
    contact_email: str
    dns_provider: str


class InternalCa(BaseModel):
    """Cert signed by the org's internal CA. Chain is mandatory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["internal_ca"] = "internal_ca"
    cert_path: str
    key_path: str
    chain_path: str


TlsStrategy = Annotated[
    ExistingBundle | LetsEncryptDns01 | InternalCa,
    Field(discriminator="kind"),
]


class LoadBalancerConfig(BaseModel):
    """Front-fronting load balancer config.

    `trusted_proxies` is mandatory and must be non-empty (hard validation rule
    6 in the build plan). Networks may be IPv4 or IPv6 CIDRs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    trusted_proxies: list[IPv4Network | IPv6Network] = Field(min_length=1)


class AppStub(BaseModel):
    """Placeholder for one seed application entry.

    Phase 2 only collects a name; generators (Phase 3) fill in protocol-specific
    target details from the runbook or a follow-up prompt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str


class SeedApps(BaseModel):
    """Counts and stubs across the three seed-app categories.

    `rdp_relays` must be empty unless `deployment_scope == "web_ssh_rdp_smb"`,
    enforced at the question layer rather than via cross-field model validation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    web_apps: list[AppStub] = Field(default_factory=list)
    ssh_relays: list[AppStub] = Field(default_factory=list)
    rdp_relays: list[AppStub] = Field(default_factory=list)


class InterviewAnswers(BaseModel):
    """All decisions captured by the interview phase.

    Pairs with an `EnvironmentSnapshot` (via `build_config()`) to produce the
    `DngConfig` that generators consume.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_scope: DeploymentScope
    idp: IdpKind
    public_hostname: str
    tls_strategy: TlsStrategy
    wildcard_cert: bool
    load_balancer: LoadBalancerConfig | None = None
    internal_dns: InternalDnsTopology
    seed_apps: SeedApps
