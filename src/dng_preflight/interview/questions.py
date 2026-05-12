"""Question framework and the eight concrete questions, in canonical order.

The order in `ORDERED_QUESTIONS` is fixed by the build plan §8 Phase 2: each
later question may consult earlier answers via `prior`, but never the reverse.

A question is a frozen pydantic model whose subclass overrides three policy
methods:

- `applies_when(snapshot, prior)` — if False, the engine skips the prompt and
  takes `default_from` as the answer (used to *force* wildcard_cert=True when
  scope includes RDP/SMB, for example).
- `default_from(snapshot, prior)` — pre-filled value shown to the user; also
  the forced value when `applies_when` is False.
- `validate_answer(answer, snapshot, prior)` — raises `ValueError` on invalid
  input. Cross-field rules belong here; intra-field shape validation belongs
  on the answer's pydantic model.

The engine assembles answers into an `InterviewAnswers` at the end via
`model_validate`, so the discriminated unions (`tls_strategy`,
`load_balancer`) get validated by pydantic in one place.
"""

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from dng_preflight.models.answers import (
    ExistingBundle,
    InternalCa,
    LetsEncryptDns01,
    LoadBalancerConfig,
    SeedApps,
)
from dng_preflight.models.snapshot import EnvironmentSnapshot

QuestionKind = Literal["select", "text", "confirm", "multi"]

Prior = Mapping[str, object]
"""Accumulated answers from earlier questions, keyed by question id.

Values are heterogeneous (strings, bools, pydantic models); use `object` so
type checkers force narrowing at use-sites rather than silently accepting any
shape.
"""


class Choice(BaseModel):
    """One selectable option for a `select` or `multi` question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    label: str


class Question(BaseModel):
    """Abstract question. Subclasses override the three policy methods."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    prompt: str
    kind: QuestionKind
    choices: list[Choice] | None = None

    def default_from(self, snapshot: EnvironmentSnapshot, prior: Prior) -> object | None:
        """Return a pre-filled default for the prompt. None means no default."""
        return None

    def applies_when(self, snapshot: EnvironmentSnapshot, prior: Prior) -> bool:
        """Return False to skip the prompt; engine then takes `default_from` as the answer."""
        return True

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        """Raise ValueError if the answer is invalid in context."""


def _require_one_of(answer: object, allowed: tuple[str, ...], field: str) -> None:
    if answer not in allowed:
        raise ValueError(f"{field} must be one of {allowed!r}, got {answer!r}")


class DeploymentScopeQuestion(Question):
    """Q1 — gates the YAML compose file choice (web+ssh vs +rdp/smb)."""

    id: Literal["deployment_scope"] = "deployment_scope"
    prompt: str = "Which deployment scope do you want?"
    kind: QuestionKind = "select"
    choices: list[Choice] = [
        Choice(value="web_ssh", label="Web + SSH only"),
        Choice(value="web_ssh_rdp_smb", label="Web + SSH + RDP/SMB"),
    ]

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        _require_one_of(answer, ("web_ssh", "web_ssh_rdp_smb"), "deployment_scope")


class IdpQuestion(Question):
    """Q2 — which SAML 2.0 IdP fronts authentication."""

    id: Literal["idp"] = "idp"
    prompt: str = "Which IdP will DNG use?"
    kind: QuestionKind = "select"
    choices: list[Choice] = [
        Choice(value="duo_sso", label="Duo SSO"),
        Choice(value="okta", label="Okta"),
        Choice(value="entra_id", label="Microsoft Entra ID"),
        Choice(value="adfs", label="AD FS"),
        Choice(value="generic_saml", label="Generic SAML 2.0"),
    ]

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        _require_one_of(
            answer,
            ("duo_sso", "okta", "entra_id", "adfs", "generic_saml"),
            "idp",
        )


class PublicHostnameQuestion(Question):
    """Q3 — public hostname for DNG. Default echoes the inspected hostname."""

    id: Literal["public_hostname"] = "public_hostname"
    prompt: str = "What is the public hostname for DNG?"
    kind: QuestionKind = "text"

    def default_from(self, snapshot: EnvironmentSnapshot, prior: Prior) -> str:
        return snapshot.hostname_planned

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("public_hostname must be a non-empty string")
        if "." not in answer:
            raise ValueError("public_hostname must be a fully-qualified domain name")


class TlsStrategyQuestion(Question):
    """Q4 — TLS strategy as a discriminated union object.

    The answers_provider is expected to return a concrete `ExistingBundle`,
    `LetsEncryptDns01`, or `InternalCa` instance (the prompt adapter walks the
    user through the per-strategy sub-prompts). The engine validates the
    union here; pydantic re-validates at the final `InterviewAnswers`
    assembly.
    """

    id: Literal["tls_strategy"] = "tls_strategy"
    prompt: str = "How will TLS certificates be sourced?"
    kind: QuestionKind = "select"
    choices: list[Choice] = [
        Choice(value="existing_bundle", label="Existing cert + key on disk"),
        Choice(value="lets_encrypt_dns01", label="Let's Encrypt (DNS-01 challenge)"),
        Choice(value="internal_ca", label="Internal CA-signed cert"),
    ]

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        if not isinstance(answer, ExistingBundle | LetsEncryptDns01 | InternalCa):
            raise ValueError(
                "tls_strategy must be an ExistingBundle, LetsEncryptDns01, or InternalCa"
            )


class WildcardCertQuestion(Question):
    """Q5 — wildcard cert. Forced True when scope includes RDP/SMB.

    `applies_when` returns False in the RDP/SMB case so the engine skips the
    prompt and uses `default_from` (True) as the answer — exactly the
    "question skipped, value forced" behaviour the build plan calls for.
    """

    id: Literal["wildcard_cert"] = "wildcard_cert"
    prompt: str = "Use a wildcard certificate?"
    kind: QuestionKind = "confirm"

    def default_from(self, snapshot: EnvironmentSnapshot, prior: Prior) -> bool:
        return prior.get("deployment_scope") == "web_ssh_rdp_smb"

    def applies_when(self, snapshot: EnvironmentSnapshot, prior: Prior) -> bool:
        return prior.get("deployment_scope") != "web_ssh_rdp_smb"

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        if not isinstance(answer, bool):
            raise ValueError("wildcard_cert must be a bool")
        if prior.get("deployment_scope") == "web_ssh_rdp_smb" and not answer:
            raise ValueError("wildcard_cert must be True when deployment_scope includes RDP/SMB")


class LoadBalancerQuestion(Question):
    """Q6 — load balancer in front of DNG, with mandatory `trusted_proxies`.

    The answers_provider returns either a fully-constructed `LoadBalancerConfig`
    or None. The model itself enforces `trusted_proxies` non-empty
    (`Field(min_length=1)`).
    """

    id: Literal["load_balancer"] = "load_balancer"
    prompt: str = "Is there a load balancer in front of DNG?"
    kind: QuestionKind = "confirm"

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        if answer is None:
            return
        if not isinstance(answer, LoadBalancerConfig):
            raise ValueError("load_balancer must be a LoadBalancerConfig or None")


class InternalDnsQuestion(Question):
    """Q7 — internal DNS topology, which shapes the runbook's DNS section."""

    id: Literal["internal_dns"] = "internal_dns"
    prompt: str = "How is internal DNS structured for this host?"
    kind: QuestionKind = "select"
    choices: list[Choice] = [
        Choice(value="split_horizon", label="Split-horizon (internal + public views)"),
        Choice(value="internal_only", label="Internal DNS only"),
        Choice(value="none", label="No internal DNS"),
    ]

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        _require_one_of(answer, ("split_horizon", "internal_only", "none"), "internal_dns")


class SeedAppsQuestion(Question):
    """Q8 — counts and stubs for web / SSH relay / RDP relay seed apps.

    The provider returns a `SeedApps` instance. `rdp_relays` must be empty
    unless scope includes RDP/SMB (cross-field rule enforced here).
    """

    id: Literal["seed_apps"] = "seed_apps"
    prompt: str = "How many seed applications, by category?"
    kind: QuestionKind = "multi"

    def validate_answer(self, answer: object, snapshot: EnvironmentSnapshot, prior: Prior) -> None:
        if not isinstance(answer, SeedApps):
            raise ValueError("seed_apps must be a SeedApps instance")
        if answer.rdp_relays and prior.get("deployment_scope") != "web_ssh_rdp_smb":
            raise ValueError("rdp_relays may only be set when deployment_scope is web_ssh_rdp_smb")


DEPLOYMENT_SCOPE: DeploymentScopeQuestion = DeploymentScopeQuestion()
IDP: IdpQuestion = IdpQuestion()
PUBLIC_HOSTNAME: PublicHostnameQuestion = PublicHostnameQuestion()
TLS_STRATEGY: TlsStrategyQuestion = TlsStrategyQuestion()
WILDCARD_CERT: WildcardCertQuestion = WildcardCertQuestion()
LOAD_BALANCER: LoadBalancerQuestion = LoadBalancerQuestion()
INTERNAL_DNS: InternalDnsQuestion = InternalDnsQuestion()
SEED_APPS: SeedAppsQuestion = SeedAppsQuestion()


ORDERED_QUESTIONS: tuple[Question, ...] = (
    DEPLOYMENT_SCOPE,
    IDP,
    PUBLIC_HOSTNAME,
    TLS_STRATEGY,
    WILDCARD_CERT,
    LOAD_BALANCER,
    INTERNAL_DNS,
    SEED_APPS,
)


__all__ = [
    "DEPLOYMENT_SCOPE",
    "IDP",
    "INTERNAL_DNS",
    "LOAD_BALANCER",
    "ORDERED_QUESTIONS",
    "PUBLIC_HOSTNAME",
    "SEED_APPS",
    "TLS_STRATEGY",
    "WILDCARD_CERT",
    "Choice",
    "DeploymentScopeQuestion",
    "IdpQuestion",
    "InternalDnsQuestion",
    "LoadBalancerQuestion",
    "Prior",
    "PublicHostnameQuestion",
    "Question",
    "QuestionKind",
    "SeedAppsQuestion",
    "TlsStrategyQuestion",
    "WildcardCertQuestion",
]
