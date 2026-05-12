"""E2E: read committed plan fixture → generate → assert artifact set."""

from pathlib import Path

import yaml

from dng_preflight.generators import ARTIFACT_NAMES, generate_all
from dng_preflight.models.config import DngConfig

PLAN_FIXTURE = Path(__file__).parent.parent / "fixtures" / "plans" / "web_ssh_rdp_smb_okta.yaml"


def test_generate_all_writes_every_expected_artifact(tmp_path: Path):
    config = DngConfig.model_validate(yaml.safe_load(PLAN_FIXTURE.read_text()))
    written = generate_all(config, tmp_path)

    assert {p.name for p in written} == set(ARTIFACT_NAMES)
    for name in ARTIFACT_NAMES:
        assert (tmp_path / name).exists()


def test_generate_all_marks_shell_scripts_executable(tmp_path: Path):
    config = DngConfig.model_validate(yaml.safe_load(PLAN_FIXTURE.read_text()))
    generate_all(config, tmp_path)
    for name in ARTIFACT_NAMES:
        if name.endswith(".sh"):
            mode = (tmp_path / name).stat().st_mode & 0o777
            assert mode & 0o100, f"{name} should be executable"


def test_generate_all_scripted_config_reparses_with_pyyaml(tmp_path: Path):
    config = DngConfig.model_validate(yaml.safe_load(PLAN_FIXTURE.read_text()))
    generate_all(config, tmp_path)
    parsed = yaml.safe_load((tmp_path / "scripted-config.yaml").read_text())
    assert isinstance(parsed, dict)
    assert "network_gateway" in parsed
    assert "primary_auth" in parsed
    # RDP/SMB scope: must include application_relays + subdomains
    assert "application_relays" in parsed
    assert "subdomains" in parsed


def test_generate_all_creates_output_dir_if_missing(tmp_path: Path):
    config = DngConfig.model_validate(yaml.safe_load(PLAN_FIXTURE.read_text()))
    target = tmp_path / "nested" / "dng-build"
    assert not target.exists()
    generate_all(config, target)
    assert target.is_dir()
    assert (target / "scripted-config.yaml").exists()


def test_generate_all_is_idempotent(tmp_path: Path):
    """Running generate_all twice into the same dir must overwrite without errors
    and produce byte-identical content."""
    config = DngConfig.model_validate(yaml.safe_load(PLAN_FIXTURE.read_text()))
    generate_all(config, tmp_path)
    first = {n: (tmp_path / n).read_bytes() for n in ARTIFACT_NAMES}
    generate_all(config, tmp_path)
    second = {n: (tmp_path / n).read_bytes() for n in ARTIFACT_NAMES}
    assert first == second
