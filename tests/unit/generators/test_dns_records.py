"""dns-records.md / dns-records.json generator: record set composition."""

import json

from dng_preflight.generators.dns_records import generate_json, generate_md
from dng_preflight.models.answers import LetsEncryptDns01
from dng_preflight.models.config import build_config
from tests.factories import lb, make_answers, make_snapshot, stub_apps


def _config(**answer_overrides):
    return build_config(make_snapshot(), make_answers(**answer_overrides))


def test_json_includes_a_record_for_public_hostname():
    payload = json.loads(generate_json(_config()))
    types_names = [(r["type"], r["name"]) for r in payload["records"]]
    assert ("A", "dng.example.com") in types_names


def test_json_adds_wildcard_a_when_wildcard_cert():
    payload = json.loads(generate_json(_config(deployment_scope="web_ssh_rdp_smb")))
    types_names = [(r["type"], r["name"]) for r in payload["records"]]
    assert ("A", "*.example.com") in types_names


def test_json_omits_wildcard_when_not_wildcard():
    payload = json.loads(generate_json(_config()))
    names = [r["name"] for r in payload["records"]]
    assert all(not n.startswith("*.") for n in names)


def test_json_includes_acme_challenge_for_letsencrypt():
    answers = make_answers().model_copy(
        update={"tls_strategy": LetsEncryptDns01(contact_email="x@y.z", dns_provider="cloudflare")}
    )
    payload = json.loads(generate_json(build_config(make_snapshot(), answers)))
    txt = [r for r in payload["records"] if r["type"] == "TXT"]
    assert any("_acme-challenge" in r["name"] for r in txt)


def test_json_does_not_include_acme_challenge_for_non_letsencrypt():
    payload = json.loads(generate_json(_config()))
    assert all(r["type"] != "TXT" for r in payload["records"])


def test_json_includes_seed_app_hostnames():
    payload = json.loads(generate_json(_config(seed_apps=stub_apps(web=2, ssh=1, rdp=0))))
    names = {r["name"] for r in payload["records"]}
    assert "web-1.example.com" in names
    assert "web-2.example.com" in names
    assert "ssh-1.example.com" in names


def test_json_target_value_is_first_resolved_ip_when_present():
    snapshot = make_snapshot(a_records={"1.1.1.1": ["198.51.100.5"]})
    payload = json.loads(generate_json(build_config(snapshot, make_answers())))
    primary = next(r for r in payload["records"] if r["name"] == "dng.example.com")
    assert primary["value"] == "198.51.100.5"


def test_json_target_value_is_placeholder_when_no_records():
    snapshot = make_snapshot(a_records={"1.1.1.1": []})
    payload = json.loads(generate_json(build_config(snapshot, make_answers())))
    primary = next(r for r in payload["records"] if r["name"] == "dng.example.com")
    assert "set" in primary["value"].lower()


def test_md_mentions_load_balancer_cidrs_table_for_acme_when_le():
    answers = make_answers().model_copy(
        update={"tls_strategy": LetsEncryptDns01(contact_email="x@y.z", dns_provider="cloudflare")}
    )
    md = generate_md(build_config(make_snapshot(), answers))
    assert "_acme-challenge" in md


def test_md_mentions_subdomain_delegation_for_rdp_smb_scope():
    md = generate_md(_config(deployment_scope="web_ssh_rdp_smb", load_balancer=lb()))
    assert "RDP/SMB subdomain delegation" in md


def test_md_omits_subdomain_section_for_web_ssh_scope():
    md = generate_md(_config())
    assert "RDP/SMB subdomain delegation" not in md


def test_md_is_deterministic():
    assert generate_md(_config()) == generate_md(_config())


def test_json_is_deterministic():
    assert generate_json(_config()) == generate_json(_config())


def test_dns_records_json_snapshot(snapshot):
    answers = make_answers(
        deployment_scope="web_ssh_rdp_smb",
        idp="okta",
        seed_apps=stub_apps(web=2, ssh=1, rdp=1),
    )
    assert generate_json(build_config(make_snapshot(), answers)) == snapshot


def test_dns_records_md_snapshot(snapshot):
    answers = make_answers(
        deployment_scope="web_ssh_rdp_smb",
        idp="okta",
        seed_apps=stub_apps(web=2, ssh=1, rdp=1),
    )
    assert generate_md(build_config(make_snapshot(), answers)) == snapshot
