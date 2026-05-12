"""Hard-stop rules (build plan §9). One test per rule, plus override behaviour."""

import pytest

from dng_preflight.models.config import DngConfig, build_config
from dng_preflight.models.snapshot import FirewallKind, FirewallState, NotDetected
from dng_preflight.validation.hard_stops import Severity, validate_plan
from tests.factories import lb, make_answers, make_snapshot


def _config_with(*, snapshot_kwargs=None, answers_kwargs=None) -> DngConfig:
    snapshot = make_snapshot(**(snapshot_kwargs or {}))
    answers = make_answers(**(answers_kwargs or {}))
    return build_config(snapshot, answers)


def test_clean_plan_has_no_violations():
    assert validate_plan(_config_with()) == []


# Rule 1 — admin port


def test_admin_port_flags_public_interface_without_firewall():
    config = _config_with(
        snapshot_kwargs={
            "egress_public_ip": "203.0.113.10",
            "interfaces": {"eth0": ["203.0.113.10"]},
            "firewall": FirewallState(kind=FirewallKind.NONE, active=False),
        }
    )
    rules = [v.rule for v in validate_plan(config)]
    assert "admin_port_must_be_private" in rules


def test_admin_port_passes_when_firewall_active():
    config = _config_with(
        snapshot_kwargs={
            "egress_public_ip": "203.0.113.10",
            "interfaces": {"eth0": ["203.0.113.10"]},
            "firewall": FirewallState(kind=FirewallKind.UFW, active=True),
        }
    )
    assert all(v.rule != "admin_port_must_be_private" for v in validate_plan(config))


def test_admin_port_override_drops_violation():
    config = _config_with(
        snapshot_kwargs={
            "egress_public_ip": "203.0.113.10",
            "interfaces": {"eth0": ["203.0.113.10"]},
            "firewall": FirewallState(kind=FirewallKind.NONE, active=False),
        }
    )
    after = validate_plan(config, overrides=frozenset({"--allow-public-admin"}))
    assert all(v.rule != "admin_port_must_be_private" for v in after)


# Rule 2 — domain join


def test_domain_joined_flagged():
    config = _config_with(snapshot_kwargs={"domain_joined": True})
    rules = [v.rule for v in validate_plan(config)]
    assert "host_must_not_be_domain_joined" in rules


def test_domain_joined_override():
    config = _config_with(snapshot_kwargs={"domain_joined": True})
    after = validate_plan(config, overrides=frozenset({"--allow-domain-joined"}))
    assert all(v.rule != "host_must_not_be_domain_joined" for v in after)


# Rule 3 — wildcard required for RDP/SMB


def test_wildcard_required_block_when_rdp_smb_and_not_wildcard():
    answers = make_answers(deployment_scope="web_ssh_rdp_smb", wildcard_cert=False)
    config = build_config(make_snapshot(), answers)
    violations = [v for v in validate_plan(config) if v.rule == "wildcard_required_for_rdp_smb"]
    assert len(violations) == 1
    assert violations[0].severity is Severity.BLOCK


def test_wildcard_required_no_violation_when_wildcard_true():
    answers = make_answers(deployment_scope="web_ssh_rdp_smb", wildcard_cert=True)
    config = build_config(make_snapshot(), answers)
    assert all(v.rule != "wildcard_required_for_rdp_smb" for v in validate_plan(config))


def test_wildcard_required_is_non_overridable():
    answers = make_answers(deployment_scope="web_ssh_rdp_smb", wildcard_cert=False)
    config = build_config(make_snapshot(), answers)
    after = validate_plan(
        config, overrides=frozenset({"--allow-public-admin", "--skip-time-check"})
    )
    assert any(v.rule == "wildcard_required_for_rdp_smb" for v in after)


# Rule 4 — time offset


def test_time_offset_flagged_above_30s():
    config = _config_with(snapshot_kwargs={"time_offset_seconds": 45.0})
    rules = [v.rule for v in validate_plan(config)]
    assert "time_offset_within_30s" in rules


def test_time_offset_flagged_for_negative_drift():
    config = _config_with(snapshot_kwargs={"time_offset_seconds": -120.0})
    rules = [v.rule for v in validate_plan(config)]
    assert "time_offset_within_30s" in rules


def test_time_offset_passes_at_boundary():
    config = _config_with(snapshot_kwargs={"time_offset_seconds": 30.0})
    assert all(v.rule != "time_offset_within_30s" for v in validate_plan(config))


def test_time_offset_skipped_when_no_daemon():
    config = _config_with(snapshot_kwargs={"time_offset_seconds": None})
    assert all(v.rule != "time_offset_within_30s" for v in validate_plan(config))


def test_time_offset_override():
    config = _config_with(snapshot_kwargs={"time_offset_seconds": 45.0})
    after = validate_plan(config, overrides=frozenset({"--skip-time-check"}))
    assert all(v.rule != "time_offset_within_30s" for v in after)


# Rule 5 — DNG version


def test_dng_version_flagged_below_330():
    config = build_config(make_snapshot(), make_answers()).model_copy(
        update={"dng_version_minimum": "3.2.0"}
    )
    rules = [v.rule for v in validate_plan(config)]
    assert "dng_version_minimum" in rules


def test_dng_version_passes_at_330():
    rules = [v.rule for v in validate_plan(_config_with())]
    assert "dng_version_minimum" not in rules


# Rule 6 — LB requires trusted_proxies (model-level guard means we exercise it via model_copy)


def test_lb_requires_trusted_proxies_passes_with_normal_lb():
    config = _config_with(answers_kwargs={"load_balancer": lb()})
    assert all(v.rule != "lb_requires_trusted_proxies" for v in validate_plan(config))


def test_lb_requires_trusted_proxies_blocks_when_empty_after_handedit():
    """The pydantic model rejects an empty list, but a hand-edited YAML plan
    could in theory bypass that. We re-check at validation time."""
    config = _config_with(answers_kwargs={"load_balancer": lb()})
    # Simulate the hand-edit: bypass model validation by constructing in-place.
    hacked_answers = config.answers.model_copy(
        update={
            "load_balancer": config.answers.load_balancer.model_construct(
                name="nginx", trusted_proxies=[]
            )
        }
    )
    hacked = config.model_copy(update={"answers": hacked_answers})
    rules = [v.rule for v in validate_plan(hacked)]
    assert "lb_requires_trusted_proxies" in rules


# Rule 7 — hostname resolves


def test_hostname_resolves_blocks_when_no_records():
    config = _config_with(snapshot_kwargs={"a_records": {"1.1.1.1": []}})
    rules = [v.rule for v in validate_plan(config)]
    assert "public_hostname_must_resolve" in rules


def test_hostname_resolves_passes_when_any_resolver_returns_records():
    config = _config_with(snapshot_kwargs={"a_records": {"8.8.8.8": ["198.51.100.1"]}})
    assert all(v.rule != "public_hostname_must_resolve" for v in validate_plan(config))


def test_hostname_resolves_is_non_overridable():
    config = _config_with(snapshot_kwargs={"a_records": {"1.1.1.1": []}})
    after = validate_plan(config, overrides=frozenset({"--skip-time-check"}))
    assert any(v.rule == "public_hostname_must_resolve" for v in after)


# General


def test_validate_plan_handles_missing_time_sync_daemon():
    snapshot = make_snapshot().model_copy(update={"time_sync": NotDetected(reason="no daemon")})
    config = build_config(snapshot, make_answers())
    # Should not raise; should not report time_offset_within_30s
    rules = [v.rule for v in validate_plan(config)]
    assert "time_offset_within_30s" not in rules


@pytest.mark.parametrize(
    "rule",
    [
        "admin_port_must_be_private",
        "host_must_not_be_domain_joined",
        "time_offset_within_30s",
    ],
)
def test_overridable_rules_have_override_flag(rule: str):
    """All OVERRIDABLE rules must declare their override flag for CLI discovery."""
    # Trigger every overridable rule simultaneously
    config = _config_with(
        snapshot_kwargs={
            "egress_public_ip": "203.0.113.10",
            "interfaces": {"eth0": ["203.0.113.10"]},
            "firewall": FirewallState(kind=FirewallKind.NONE, active=False),
            "domain_joined": True,
            "time_offset_seconds": 45.0,
        }
    )
    by_rule = {v.rule: v for v in validate_plan(config)}
    assert rule in by_rule
    assert by_rule[rule].severity is Severity.OVERRIDABLE
    assert by_rule[rule].override_flag is not None
