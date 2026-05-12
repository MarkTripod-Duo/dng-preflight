"""Integration: load the committed plan fixture, validate, and round-trip."""

from pathlib import Path

import yaml

from dng_preflight.models.config import DngConfig
from dng_preflight.validation.hard_stops import validate_plan

PLAN_FIXTURE = Path(__file__).parent.parent / "fixtures" / "plans" / "web_ssh_rdp_smb_okta.yaml"


def test_fixture_plan_loads_into_dng_config():
    data = yaml.safe_load(PLAN_FIXTURE.read_text())
    config = DngConfig.model_validate(data)
    assert config.answers.deployment_scope == "web_ssh_rdp_smb"
    assert config.answers.wildcard_cert is True
    assert config.requires_extra_dns_container is True


def test_fixture_plan_yaml_roundtrips_preserving_equality():
    data = yaml.safe_load(PLAN_FIXTURE.read_text())
    config = DngConfig.model_validate(data)
    text = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    rehydrated = DngConfig.model_validate(yaml.safe_load(text))
    assert rehydrated == config


def test_fixture_plan_passes_hard_stops():
    data = yaml.safe_load(PLAN_FIXTURE.read_text())
    config = DngConfig.model_validate(data)
    assert validate_plan(config) == []
