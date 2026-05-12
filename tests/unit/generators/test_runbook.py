"""RUNBOOK.md generator: SAML circular-dependency ordering, IdP-specific text."""

from dng_preflight.generators.runbook import generate
from dng_preflight.models.config import build_config
from tests.factories import make_answers, make_snapshot


def _gen(**answer_overrides) -> str:
    return generate(build_config(make_snapshot(), make_answers(**answer_overrides)))


def test_runbook_step_order_breaks_saml_circular_dependency():
    """Steps must run: bring up DNG → export SP metadata → configure IdP →
    import IdP metadata → first-login password reset."""
    text = _gen()
    indices = {
        "step1_install": text.index("Step 1 — Run the installer"),
        "step4_bringup": text.index("Step 4 — First-time DNG bring-up"),
        "step5_export": text.index("Step 5 — Export DNG SP metadata"),
        "step6_idp": text.index("Step 6 — Configure the IdP"),
        "step7_import": text.index("Step 7 — Import IdP metadata into DNG"),
        "step8_password": text.index("Step 8 — First-login password reset"),
    }
    assert (
        indices["step1_install"]
        < indices["step4_bringup"]
        < indices["step5_export"]
        < indices["step6_idp"]
        < indices["step7_import"]
        < indices["step8_password"]
    )


def test_runbook_idp_section_is_okta_specific_when_idp_is_okta():
    text = _gen(idp="okta")
    assert "In **Okta**" in text


def test_runbook_idp_section_is_entra_specific_when_idp_is_entra():
    text = _gen(idp="entra_id")
    assert "Microsoft Entra ID" in text


def test_runbook_idp_section_is_duo_sso_specific_when_idp_is_duo_sso():
    text = _gen(idp="duo_sso")
    assert "Duo SSO" in text


def test_runbook_idp_section_is_adfs_specific_when_idp_is_adfs():
    text = _gen(idp="adfs")
    assert "AD FS" in text


def test_runbook_idp_section_falls_back_to_generic_for_generic_saml():
    text = _gen(idp="generic_saml")
    assert "generic SAML 2.0 IdP" in text


def test_runbook_includes_letsencrypt_step3_text_for_le_strategy():
    from dng_preflight.models.answers import LetsEncryptDns01

    answers = make_answers().model_copy(
        update={"tls_strategy": LetsEncryptDns01(contact_email="x@y.z", dns_provider="cloudflare")}
    )
    text = generate(build_config(make_snapshot(), answers))
    assert "Let's Encrypt (DNS-01)" in text
    assert "DNG will request the cert itself" in text


def test_runbook_flags_dns_step_zero_when_hostname_does_not_resolve():
    snapshot = make_snapshot(a_records={"1.1.1.1": []})
    text = generate(build_config(snapshot, make_answers()))
    assert "Discovery did not find any A/AAAA records" in text


def test_runbook_is_deterministic_for_same_input():
    assert _gen() == _gen()


def test_runbook_snapshot(snapshot):
    assert _gen(idp="okta") == snapshot
