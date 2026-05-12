"""Per-question behaviour: default_from, applies_when, validate_answer."""

import pytest

from dng_preflight.interview.questions import (
    DEPLOYMENT_SCOPE,
    IDP,
    INTERNAL_DNS,
    LOAD_BALANCER,
    ORDERED_QUESTIONS,
    PUBLIC_HOSTNAME,
    SEED_APPS,
    TLS_STRATEGY,
    WILDCARD_CERT,
)
from dng_preflight.models.answers import (
    AppStub,
    ExistingBundle,
    LetsEncryptDns01,
    SeedApps,
)
from tests.factories import lb, make_snapshot


def test_ordered_questions_contains_all_eight_ids_in_canonical_order():
    expected_ids = (
        "deployment_scope",
        "idp",
        "public_hostname",
        "tls_strategy",
        "wildcard_cert",
        "load_balancer",
        "internal_dns",
        "seed_apps",
    )
    assert tuple(q.id for q in ORDERED_QUESTIONS) == expected_ids


def test_deployment_scope_rejects_unknown_value():
    with pytest.raises(ValueError, match="deployment_scope"):
        DEPLOYMENT_SCOPE.validate_answer("on_prem", make_snapshot(), {})


@pytest.mark.parametrize("value", ["web_ssh", "web_ssh_rdp_smb"])
def test_deployment_scope_accepts_valid_values(value: str):
    DEPLOYMENT_SCOPE.validate_answer(value, make_snapshot(), {})


@pytest.mark.parametrize("value", ["duo_sso", "okta", "entra_id", "adfs", "generic_saml"])
def test_idp_accepts_valid_values(value: str):
    IDP.validate_answer(value, make_snapshot(), {})


def test_idp_rejects_unknown_value():
    with pytest.raises(ValueError, match="idp"):
        IDP.validate_answer("onelogin", make_snapshot(), {})


def test_public_hostname_defaults_to_snapshot_hostname_planned():
    snap = make_snapshot(hostname="custom.host.example")
    assert PUBLIC_HOSTNAME.default_from(snap, {}) == "custom.host.example"


@pytest.mark.parametrize("bad", ["", "  ", "no-tld-here"])
def test_public_hostname_rejects_malformed_strings(bad: str):
    with pytest.raises(ValueError, match="public_hostname"):
        PUBLIC_HOSTNAME.validate_answer(bad, make_snapshot(), {})


def test_public_hostname_accepts_fqdn():
    PUBLIC_HOSTNAME.validate_answer("dng.example.com", make_snapshot(), {})


def test_tls_strategy_accepts_concrete_union_member():
    TLS_STRATEGY.validate_answer(ExistingBundle(cert_path="/c", key_path="/k"), make_snapshot(), {})
    TLS_STRATEGY.validate_answer(
        LetsEncryptDns01(contact_email="x@y.z", dns_provider="cloudflare"),
        make_snapshot(),
        {},
    )


def test_tls_strategy_rejects_plain_string():
    with pytest.raises(ValueError, match="tls_strategy"):
        TLS_STRATEGY.validate_answer("existing_bundle", make_snapshot(), {})


def test_wildcard_cert_applies_when_scope_is_web_ssh():
    assert WILDCARD_CERT.applies_when(make_snapshot(), {"deployment_scope": "web_ssh"}) is True


def test_wildcard_cert_skipped_when_scope_includes_rdp_smb():
    prior = {"deployment_scope": "web_ssh_rdp_smb"}
    assert WILDCARD_CERT.applies_when(make_snapshot(), prior) is False
    assert WILDCARD_CERT.default_from(make_snapshot(), prior) is True


def test_wildcard_cert_validate_blocks_false_when_scope_is_rdp_smb():
    with pytest.raises(ValueError, match="wildcard_cert"):
        WILDCARD_CERT.validate_answer(
            False, make_snapshot(), {"deployment_scope": "web_ssh_rdp_smb"}
        )


def test_wildcard_cert_rejects_non_bool():
    with pytest.raises(ValueError, match="wildcard_cert"):
        WILDCARD_CERT.validate_answer("yes", make_snapshot(), {"deployment_scope": "web_ssh"})


def test_load_balancer_accepts_none():
    LOAD_BALANCER.validate_answer(None, make_snapshot(), {})


def test_load_balancer_accepts_config():
    LOAD_BALANCER.validate_answer(lb(), make_snapshot(), {})


def test_load_balancer_rejects_string():
    with pytest.raises(ValueError, match="load_balancer"):
        LOAD_BALANCER.validate_answer("yes", make_snapshot(), {})


@pytest.mark.parametrize("value", ["split_horizon", "internal_only", "none"])
def test_internal_dns_accepts_valid_values(value: str):
    INTERNAL_DNS.validate_answer(value, make_snapshot(), {})


def test_internal_dns_rejects_unknown_value():
    with pytest.raises(ValueError, match="internal_dns"):
        INTERNAL_DNS.validate_answer("public", make_snapshot(), {})


def test_seed_apps_rejects_rdp_relays_when_scope_excludes_rdp():
    apps = SeedApps(rdp_relays=[AppStub(name="rdp-1")])
    with pytest.raises(ValueError, match="rdp_relays"):
        SEED_APPS.validate_answer(apps, make_snapshot(), {"deployment_scope": "web_ssh"})


def test_seed_apps_accepts_rdp_relays_when_scope_includes_rdp():
    apps = SeedApps(rdp_relays=[AppStub(name="rdp-1")])
    SEED_APPS.validate_answer(apps, make_snapshot(), {"deployment_scope": "web_ssh_rdp_smb"})


def test_seed_apps_rejects_non_seedapps_value():
    with pytest.raises(ValueError, match="seed_apps"):
        SEED_APPS.validate_answer({"web_apps": []}, make_snapshot(), {})
