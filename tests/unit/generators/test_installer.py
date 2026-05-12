"""install.sh generator: deterministic content, optional shellcheck pass."""

import shutil
import subprocess

import pytest

from dng_preflight.generators.installer import generate
from dng_preflight.models.config import build_config
from tests.factories import make_answers, make_snapshot


def _generate() -> str:
    return generate(build_config(make_snapshot(), make_answers()))


def test_installer_starts_with_shebang_and_strict_mode():
    text = _generate()
    lines = text.splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert "set -euo pipefail" in text


def test_installer_embeds_public_hostname():
    text = _generate()
    assert "PUBLIC_HOSTNAME='dng.example.com'" in text


def test_installer_embeds_dng_version_minimum():
    text = _generate()
    assert "DNG_VERSION='3.3.0'" in text


def test_installer_handles_ubuntu_and_rhel_branches():
    text = _generate()
    # both package managers must be wired up
    assert "apt-get install" in text
    assert "dnf install" in text


def test_installer_is_deterministic_for_same_input():
    assert _generate() == _generate()


def test_installer_snapshot(snapshot):
    assert _generate() == snapshot


_SHELLCHECK = shutil.which("shellcheck")


@pytest.mark.skipif(_SHELLCHECK is None, reason="shellcheck not installed")
def test_installer_passes_shellcheck(tmp_path):
    """Build-plan acceptance: install.sh must pass shellcheck with zero warnings."""
    sh = tmp_path / "install.sh"
    sh.write_text(_generate())
    # Args are hardcoded (full path from `shutil.which`, fixed flag, tmp file).
    result = subprocess.run(  # noqa: S603 — trusted invocation of shellcheck
        [_SHELLCHECK, "--severity=warning", str(sh)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"shellcheck output:\n{result.stdout}\n{result.stderr}"
