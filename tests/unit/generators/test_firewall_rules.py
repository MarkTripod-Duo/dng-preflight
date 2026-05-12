"""firewall.sh generator: per-firewall-kind template selection, content shape."""

from dng_preflight.generators.firewall_rules import generate
from dng_preflight.models.config import build_config
from dng_preflight.models.snapshot import FirewallKind, FirewallState, NotDetected
from tests.factories import lb, make_answers, make_snapshot


def _config(*, firewall: FirewallState | NotDetected | None = None, **answer_overrides):
    return build_config(make_snapshot(firewall=firewall), make_answers(**answer_overrides))


def test_firewall_emits_ufw_when_detected_kind_is_ufw():
    text = generate(_config(firewall=FirewallState(kind=FirewallKind.UFW, active=True)))
    assert "ufw allow 443/tcp" in text
    assert "firewall-cmd" not in text


def test_firewall_emits_firewalld_when_detected_kind_is_firewalld():
    text = generate(_config(firewall=FirewallState(kind=FirewallKind.FIREWALLD, active=True)))
    assert "firewall-cmd --permanent --zone=public --add-port=443/tcp" in text
    assert "ufw allow" not in text


def test_firewall_emits_stub_for_iptables():
    text = generate(_config(firewall=FirewallState(kind=FirewallKind.IPTABLES, active=True)))
    # stub script prints manual guidance instead of issuing commands
    assert "could not be generated" in text
    assert "manually" in text


def test_firewall_emits_stub_when_not_detected():
    text = generate(_config(firewall=NotDetected(reason="no firewall tool found")))
    assert "could not be generated" in text


def test_firewall_ufw_uses_load_balancer_cidrs_for_admin_port():
    text = generate(
        _config(
            firewall=FirewallState(kind=FirewallKind.UFW, active=True),
            load_balancer=lb("nginx", "10.0.0.0/8"),
        )
    )
    assert "ufw allow from 10.0.0.0/8 to any port 8443 proto tcp" in text


def test_firewall_ufw_warns_when_no_admin_cidrs_provided():
    text = generate(_config(firewall=FirewallState(kind=FirewallKind.UFW, active=True)))
    assert "NO public access" in text


def test_firewall_opens_3389_for_rdp_smb_scope():
    text = generate(
        _config(
            firewall=FirewallState(kind=FirewallKind.UFW, active=True),
            deployment_scope="web_ssh_rdp_smb",
        )
    )
    assert "ufw allow 3389/tcp" in text


def test_firewall_does_not_open_3389_for_web_ssh_only_scope():
    text = generate(_config(firewall=FirewallState(kind=FirewallKind.UFW, active=True)))
    assert "3389/tcp" not in text


def test_firewall_is_deterministic():
    config = _config(firewall=FirewallState(kind=FirewallKind.UFW, active=True))
    assert generate(config) == generate(config)


def test_firewall_snapshot_ufw(snapshot):
    config = _config(
        firewall=FirewallState(kind=FirewallKind.UFW, active=True),
        load_balancer=lb("nginx", "10.0.0.0/8"),
        deployment_scope="web_ssh_rdp_smb",
    )
    assert generate(config) == snapshot
