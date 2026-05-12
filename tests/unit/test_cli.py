"""Unit tests for the dng-preflight CLI."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from dng_preflight import cli as cli_module
from dng_preflight.interview.questions import Question
from dng_preflight.models.answers import ExistingBundle, SeedApps
from dng_preflight.models.snapshot import EnvironmentSnapshot
from tests.factories import make_snapshot


def _stub_snapshot() -> EnvironmentSnapshot:
    return make_snapshot(
        docker_detected=False,
        a_records={"1.1.1.1": []},
        time_offset_seconds=0.0,
    )


def _canned_answers() -> dict[str, Any]:
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


def _canned_provider(answers: dict[str, Any] | None = None):
    answers = answers or _canned_answers()

    def provide(
        question: Question, snapshot: EnvironmentSnapshot, default: Any, prior: Mapping[str, Any]
    ) -> Any:
        return answers[question.id]

    return provide


@pytest.fixture
def patched_collect(monkeypatch: pytest.MonkeyPatch):
    async def _fake_collect(_hostname: str) -> EnvironmentSnapshot:
        return _stub_snapshot()

    monkeypatch.setattr(cli_module, "collect", _fake_collect)


def test_inspect_emits_yaml_by_default(patched_collect):
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["inspect", "--hostname", "dng.example.com"])
    assert result.exit_code == 0, result.output
    parsed = yaml.safe_load(result.output)
    assert parsed["hostname_planned"] == "dng.example.com"
    assert parsed["docker"]["detected"] is False


def test_inspect_emits_json_when_requested(patched_collect):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["inspect", "--hostname", "dng.example.com", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["docker"]["detected"] is False


def test_inspect_writes_to_output_file(patched_collect, tmp_path: Path):
    target = tmp_path / "snap.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["inspect", "--hostname", "dng.example.com", "--output", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert target.exists()
    parsed = yaml.safe_load(target.read_text())
    assert parsed["hostname_planned"] == "dng.example.com"


def test_inspect_requires_hostname():
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["inspect"])
    assert result.exit_code != 0
    assert "hostname" in result.output.lower() or "missing" in result.output.lower()


# -----------------------------------------------------------------------------
# plan
# -----------------------------------------------------------------------------


@pytest.fixture
def patched_plan(monkeypatch: pytest.MonkeyPatch):
    """Stub out discovery and the questionary prompt for `plan` tests."""

    async def _fake_collect(_hostname: str) -> EnvironmentSnapshot:
        # snapshot with a resolving hostname so rule 7 doesn't block
        return make_snapshot(time_offset_seconds=0.0)

    monkeypatch.setattr(cli_module, "collect", _fake_collect)
    monkeypatch.setattr(cli_module, "questionary_provider", _canned_provider())


def test_plan_emits_yaml_to_stdout_by_default(patched_plan):
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["plan", "--hostname", "dng.example.com"])
    assert result.exit_code == 0, result.output
    parsed = yaml.safe_load(result.output)
    assert parsed["answers"]["deployment_scope"] == "web_ssh"
    assert parsed["dng_version_minimum"] == "3.3.0"


def test_plan_writes_to_save_path(patched_plan, tmp_path: Path):
    target = tmp_path / "plan.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["plan", "--hostname", "dng.example.com", "--save", str(target)]
    )
    assert result.exit_code == 0, result.output
    assert target.exists()
    parsed = yaml.safe_load(target.read_text())
    assert parsed["answers"]["public_hostname"] == "dng.example.com"


def test_plan_requires_hostname_or_snapshot():
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["plan"])
    assert result.exit_code != 0
    assert "hostname" in result.output.lower() or "snapshot" in result.output.lower()


def test_plan_loads_snapshot_from_file_when_provided(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    snapshot = make_snapshot(time_offset_seconds=0.0)
    snap_file = tmp_path / "snap.yaml"
    snap_file.write_text(yaml.safe_dump(snapshot.model_dump(mode="json"), sort_keys=False))

    def _no_collect(_hostname: str):
        pytest.fail("collect() should not be called when --snapshot is supplied")

    monkeypatch.setattr(cli_module, "collect", _no_collect)
    monkeypatch.setattr(cli_module, "questionary_provider", _canned_provider())

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["plan", "--snapshot", str(snap_file)])
    assert result.exit_code == 0, result.output


def test_plan_exits_nonzero_on_hard_stop_violation(monkeypatch: pytest.MonkeyPatch):
    # Snapshot that triggers rule 7 (no resolving records)
    async def _fake_collect(_hostname: str) -> EnvironmentSnapshot:
        return make_snapshot(a_records={"1.1.1.1": []}, time_offset_seconds=0.0)

    monkeypatch.setattr(cli_module, "collect", _fake_collect)
    monkeypatch.setattr(cli_module, "questionary_provider", _canned_provider())

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["plan", "--hostname", "dng.example.com"])
    assert result.exit_code == 2
    assert "public_hostname_must_resolve" in result.output + (result.stderr or "")


def test_plan_override_flag_drops_overridable_violation(monkeypatch: pytest.MonkeyPatch):
    # Snapshot that triggers rule 4 (time offset)
    async def _fake_collect(_hostname: str) -> EnvironmentSnapshot:
        return make_snapshot(time_offset_seconds=90.0)

    monkeypatch.setattr(cli_module, "collect", _fake_collect)
    monkeypatch.setattr(cli_module, "questionary_provider", _canned_provider())

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["plan", "--hostname", "dng.example.com", "--skip-time-check"],
    )
    assert result.exit_code == 0, result.output


# -----------------------------------------------------------------------------
# validate
# -----------------------------------------------------------------------------


def _write_plan_file(tmp_path: Path, *, time_offset: float = 0.0) -> Path:
    """Build a clean plan YAML on disk and return its path."""
    from dng_preflight.models.config import build_config
    from tests.factories import make_answers

    snapshot = make_snapshot(time_offset_seconds=time_offset)
    config = build_config(snapshot, make_answers())
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    return path


def test_validate_clean_plan_exits_zero(tmp_path: Path):
    plan_path = _write_plan_file(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["validate", "--plan", str(plan_path)])
    assert result.exit_code == 0, result.output


def test_validate_failing_plan_exits_nonzero(tmp_path: Path):
    plan_path = _write_plan_file(tmp_path, time_offset=120.0)
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["validate", "--plan", str(plan_path)])
    assert result.exit_code == 2
    assert "time_offset_within_30s" in result.output + (result.stderr or "")


def test_validate_override_drops_violation(tmp_path: Path):
    plan_path = _write_plan_file(tmp_path, time_offset=120.0)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["validate", "--plan", str(plan_path), "--skip-time-check"]
    )
    assert result.exit_code == 0, result.output


def test_validate_requires_plan_path():
    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["validate"])
    assert result.exit_code != 0
    assert "plan" in result.output.lower() or "missing" in result.output.lower()
