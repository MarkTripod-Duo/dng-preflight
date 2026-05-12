"""scripted-config generator: YAML schema-shape, scope variance, snapshot lock."""

import yaml

from dng_preflight.generators.scripted_config import generate
from dng_preflight.models.config import build_config
from tests.factories import lb, make_answers, make_snapshot, stub_apps

# Top-level keys per DNG scripted-config docs (duo.com/docs/dng-scripted-config).
# Required: network_gateway. Variant adds: application_relays + subdomains for RDP/SMB.
_BASE_TOP_LEVEL_KEYS = {
    "network_gateway",
    "primary_auth",
    "web_applications",
    "ssh_servers",
}
_RDP_SMB_EXTRAS = {"application_relays", "subdomains"}


def _generate_and_parse(*, scope: str = "web_ssh", **answer_overrides):
    answers = make_answers(deployment_scope=scope, **answer_overrides)
    config = build_config(make_snapshot(), answers)
    text = generate(config)
    parsed = yaml.safe_load(text)
    return text, parsed


def test_scripted_config_reparses_with_pyyaml_web_ssh():
    _, parsed = _generate_and_parse(scope="web_ssh")
    assert isinstance(parsed, dict)


def test_scripted_config_contains_required_top_level_keys_for_web_ssh():
    _, parsed = _generate_and_parse(scope="web_ssh")
    keys = set(parsed.keys())
    assert _BASE_TOP_LEVEL_KEYS.issubset(keys)
    assert _RDP_SMB_EXTRAS.isdisjoint(keys)


def test_scripted_config_contains_extras_for_web_ssh_rdp_smb():
    _, parsed = _generate_and_parse(scope="web_ssh_rdp_smb")
    keys = set(parsed.keys())
    assert (_BASE_TOP_LEVEL_KEYS | _RDP_SMB_EXTRAS).issubset(keys)


def test_scripted_config_network_gateway_has_required_subkeys():
    _, parsed = _generate_and_parse()
    ng = parsed["network_gateway"]
    for required in ("hostname", "enable_ui", "password", "admin_email", "ssl_cert"):
        assert required in ng, f"network_gateway missing {required}"


def test_scripted_config_emits_load_balancer_cidrs_when_lb_set():
    _, parsed = _generate_and_parse(load_balancer=lb("nginx", "10.0.0.0/8"))
    assert parsed["network_gateway"]["load_balancer_cidrs_ips"] == ["10.0.0.0/8"]


def test_scripted_config_omits_load_balancer_cidrs_when_no_lb():
    _, parsed = _generate_and_parse(load_balancer=None)
    assert "load_balancer_cidrs_ips" not in parsed["network_gateway"]


def test_scripted_config_ssl_cert_source_letsencrypt_for_letsencrypt_strategy():
    from dng_preflight.models.answers import LetsEncryptDns01

    answers = make_answers()
    answers = answers.model_copy(
        update={
            "tls_strategy": LetsEncryptDns01(
                contact_email="ops@example.com", dns_provider="cloudflare"
            )
        }
    )
    config = build_config(make_snapshot(), answers)
    parsed = yaml.safe_load(generate(config))
    assert parsed["network_gateway"]["ssl_cert"]["source"] == "letsencrypt"
    # No inline cert/key paste markers when LE handles issuance
    assert "cert" not in parsed["network_gateway"]["ssl_cert"]


def test_scripted_config_ssl_cert_source_own_for_existing_bundle():
    _, parsed = _generate_and_parse()
    assert parsed["network_gateway"]["ssl_cert"]["source"] == "own"
    # cert/key are emitted as paste-placeholders
    assert "<<paste contents of" in parsed["network_gateway"]["ssl_cert"]["cert"]


def test_scripted_config_seeds_application_relays_for_rdp_smb_scope():
    _, parsed = _generate_and_parse(
        scope="web_ssh_rdp_smb",
        seed_apps=stub_apps(web=1, ssh=1, rdp=2),
    )
    relays = parsed["application_relays"]
    assert set(relays.keys()) == {"rdp-1", "rdp-2"}
    for entry in relays.values():
        assert entry["application_type"] == "rdp"


def test_scripted_config_is_deterministic_for_same_input():
    """Two renders of the same DngConfig must be byte-identical."""
    answers = make_answers()
    config = build_config(make_snapshot(), answers)
    first = generate(config)
    second = generate(config)
    assert first == second


def test_scripted_config_snapshot(snapshot):
    """syrupy lock: same fixture-shaped input always produces the same output."""
    answers = make_answers(
        deployment_scope="web_ssh_rdp_smb",
        idp="okta",
        load_balancer=lb("nginx", "10.0.0.0/8"),
        internal_dns="split_horizon",
        seed_apps=stub_apps(web=2, ssh=1, rdp=1),
    )
    config = build_config(make_snapshot(), answers)
    assert generate(config) == snapshot
