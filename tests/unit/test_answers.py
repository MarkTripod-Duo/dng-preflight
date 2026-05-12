"""Pydantic behaviour of InterviewAnswers, TlsStrategy union, LoadBalancer, DngConfig."""

from ipaddress import IPv4Network

import pytest
import yaml
from pydantic import ValidationError

from dng_preflight.models.answers import (
    AppStub,
    ExistingBundle,
    InternalCa,
    InterviewAnswers,
    LetsEncryptDns01,
    LoadBalancerConfig,
    SeedApps,
)
from dng_preflight.models.config import DNG_MIN_VERSION, DngConfig, build_config
from tests.factories import make_answers, make_snapshot


def test_tls_strategy_discriminator_disambiguates_existing_bundle():
    answers = make_answers()
    dumped = answers.model_dump(mode="json")
    rehydrated = InterviewAnswers.model_validate(dumped)
    assert isinstance(rehydrated.tls_strategy, ExistingBundle)
    assert rehydrated.tls_strategy.cert_path == "/etc/ssl/dng/cert.pem"


def test_tls_strategy_discriminator_disambiguates_lets_encrypt():
    answers = make_answers().model_copy(
        update={"tls_strategy": LetsEncryptDns01(contact_email="x@y.z", dns_provider="cloudflare")}
    )
    rehydrated = InterviewAnswers.model_validate(answers.model_dump(mode="json"))
    assert isinstance(rehydrated.tls_strategy, LetsEncryptDns01)
    assert rehydrated.tls_strategy.dns_provider == "cloudflare"


def test_tls_strategy_discriminator_disambiguates_internal_ca():
    strategy = InternalCa(
        cert_path="/etc/ssl/dng/cert.pem",
        key_path="/etc/ssl/dng/key.pem",
        chain_path="/etc/ssl/dng/chain.pem",
    )
    answers = make_answers().model_copy(update={"tls_strategy": strategy})
    rehydrated = InterviewAnswers.model_validate(answers.model_dump(mode="json"))
    assert isinstance(rehydrated.tls_strategy, InternalCa)


def test_load_balancer_requires_non_empty_trusted_proxies():
    with pytest.raises(ValidationError):
        LoadBalancerConfig(name="nginx", trusted_proxies=[])


def test_load_balancer_accepts_ipv4_and_ipv6_networks():
    lb = LoadBalancerConfig.model_validate(
        {"name": "nginx", "trusted_proxies": ["10.0.0.0/8", "fd00::/8"]}
    )
    assert lb.trusted_proxies[0] == IPv4Network("10.0.0.0/8")


def test_seed_apps_default_is_empty():
    assert SeedApps() == SeedApps(web_apps=[], ssh_relays=[], rdp_relays=[])


def test_interview_answers_rejects_unknown_field():
    snap = make_answers().model_dump(mode="json")
    snap["surprise"] = True
    with pytest.raises(ValidationError):
        InterviewAnswers.model_validate(snap)


def test_interview_answers_roundtrips_through_yaml():
    answers = make_answers(
        deployment_scope="web_ssh_rdp_smb",
        idp="entra_id",
        seed_apps=SeedApps(
            web_apps=[AppStub(name="web-1")],
            ssh_relays=[AppStub(name="ssh-1")],
            rdp_relays=[AppStub(name="rdp-1")],
        ),
    )
    text = yaml.safe_dump(answers.model_dump(mode="json"), sort_keys=False)
    rehydrated = InterviewAnswers.model_validate(yaml.safe_load(text))
    assert rehydrated == answers


def test_build_config_pins_dng_version_minimum():
    config = build_config(make_snapshot(), make_answers())
    assert config.dng_version_minimum == DNG_MIN_VERSION


def test_build_config_flags_extra_dns_container_for_rdp_smb():
    config = build_config(
        make_snapshot(),
        make_answers(deployment_scope="web_ssh_rdp_smb"),
    )
    assert config.requires_extra_dns_container is True


def test_build_config_does_not_flag_extra_dns_for_web_ssh():
    config = build_config(make_snapshot(), make_answers(deployment_scope="web_ssh"))
    assert config.requires_extra_dns_container is False


def test_dng_config_roundtrips_through_yaml():
    config = build_config(make_snapshot(), make_answers())
    text = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    rehydrated = DngConfig.model_validate(yaml.safe_load(text))
    assert rehydrated == config
