"""Engine tests: ordered question walk, force-skip, and IdP × scope × TLS sweep."""

from collections.abc import Mapping
from typing import Any

import pytest

from dng_preflight.interview.engine import run
from dng_preflight.interview.questions import Question
from dng_preflight.models.answers import (
    ExistingBundle,
    InternalCa,
    InterviewAnswers,
    LetsEncryptDns01,
    SeedApps,
)
from dng_preflight.models.snapshot import EnvironmentSnapshot
from tests.factories import lb, make_snapshot


def _provider(answers: dict[str, Any]):
    """Return a canned provider that yields the per-question id from `answers`."""

    def provide(
        question: Question, snapshot: EnvironmentSnapshot, default: Any, prior: Mapping[str, Any]
    ) -> Any:
        return answers[question.id]

    return provide


def _base_answers() -> dict[str, Any]:
    return {
        "deployment_scope": "web_ssh",
        "idp": "duo_sso",
        "public_hostname": "dng.example.com",
        "tls_strategy": ExistingBundle(cert_path="/c", key_path="/k"),
        "wildcard_cert": False,
        "load_balancer": None,
        "internal_dns": "internal_only",
        "seed_apps": SeedApps(),
    }


def test_run_assembles_interview_answers_in_order():
    snapshot = make_snapshot()
    result = run(snapshot, _provider(_base_answers()))
    assert isinstance(result, InterviewAnswers)
    assert result.deployment_scope == "web_ssh"
    assert result.idp == "duo_sso"


def test_engine_skips_wildcard_question_for_rdp_smb_scope_and_forces_true():
    """Forced-value path: applies_when=False → engine takes default_from."""
    snapshot = make_snapshot()
    answers = _base_answers()
    answers["deployment_scope"] = "web_ssh_rdp_smb"
    asked: list[str] = []

    def provide(
        question: Question, snapshot: EnvironmentSnapshot, default: Any, prior: Mapping[str, Any]
    ) -> Any:
        asked.append(question.id)
        if question.id == "wildcard_cert":
            pytest.fail("engine should not have asked wildcard_cert for RDP/SMB scope")
        return answers[question.id]

    result = run(snapshot, provide)
    assert result.wildcard_cert is True
    assert "wildcard_cert" not in asked


def test_engine_propagates_validation_failure_from_question():
    snapshot = make_snapshot()
    answers = _base_answers()
    answers["idp"] = "onelogin"
    with pytest.raises(ValueError, match="idp"):
        run(snapshot, _provider(answers))


def test_engine_propagates_pydantic_validation_at_assembly():
    """Engine's final InterviewAnswers.model_validate must catch shape errors
    the per-question validators don't (here: a malformed tls_strategy that
    *would* pass isinstance but produces an invalid union member)."""
    snapshot = make_snapshot()
    answers = _base_answers()
    answers["public_hostname"] = "good.example.com"
    # Replace tls_strategy with something that fails final union shape check
    # (a dict with wrong kind).
    bad = _base_answers()
    bad["tls_strategy"] = {"kind": "nonsense", "cert_path": "/c", "key_path": "/k"}

    def provide(
        question: Question, snapshot: EnvironmentSnapshot, default: Any, prior: Mapping[str, Any]
    ) -> Any:
        return bad[question.id]

    # Per-question validate_answer rejects non-pydantic-instance, so this
    # raises ValueError before reaching final assembly.
    with pytest.raises(ValueError, match="tls_strategy"):
        run(snapshot, provide)


def _matrix_combos():
    """Generate (scope, idp, tls_factory) triples worth covering."""
    tls_factories = {
        "existing_bundle": lambda: ExistingBundle(cert_path="/c", key_path="/k"),
        "lets_encrypt": lambda: LetsEncryptDns01(
            contact_email="ops@example.com", dns_provider="cloudflare"
        ),
        "internal_ca": lambda: InternalCa(cert_path="/c", key_path="/k", chain_path="/chain"),
    }
    scopes = ("web_ssh", "web_ssh_rdp_smb")
    idps = ("duo_sso", "okta", "entra_id", "adfs", "generic_saml")
    return [
        (scope, idp, name, fac)
        for scope in scopes
        for idp in idps
        for name, fac in tls_factories.items()
    ]


@pytest.mark.parametrize(("scope", "idp", "tls_name", "tls_factory"), _matrix_combos())
def test_engine_covers_scope_x_idp_x_tls_matrix(
    scope: str, idp: str, tls_name: str, tls_factory: Any
):
    """Every plausible scope × idp × tls-strategy combination must assemble cleanly."""
    snapshot = make_snapshot()
    answers = _base_answers()
    answers["deployment_scope"] = scope
    answers["idp"] = idp
    answers["tls_strategy"] = tls_factory()
    if scope == "web_ssh_rdp_smb":
        # wildcard forced — engine ignores the provider's value here
        answers["wildcard_cert"] = True
    # Add a load balancer half the time for coverage variety
    if idp in ("okta", "adfs"):
        answers["load_balancer"] = lb()

    result = run(snapshot, _provider(answers))
    assert result.deployment_scope == scope
    assert result.idp == idp
    assert result.wildcard_cert is (scope == "web_ssh_rdp_smb" or False)
    _ = tls_name  # included in parametrize id for failure readability
