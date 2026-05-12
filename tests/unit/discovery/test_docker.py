"""Unit tests for the docker probe."""

from __future__ import annotations

import subprocess

import pytest

from dng_preflight.discovery import docker as docker_probe
from dng_preflight.models.snapshot import DockerInfo, NotDetected


def _fake_run(stdout: str, returncode: int = 0) -> object:
    class _R:
        pass

    r = _R()
    r.stdout = stdout
    r.returncode = returncode
    return r


async def test_probe_returns_not_detected_when_docker_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(docker_probe.shutil, "which", lambda _x: None)
    result = await docker_probe.probe()
    assert isinstance(result, NotDetected)
    assert "docker" in result.reason.lower()


async def test_probe_returns_docker_info_when_engine_present(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(docker_probe.shutil, "which", lambda _x: "/usr/bin/docker")

    def fake_subprocess_run(cmd, **_kw):
        if cmd[1] == "version":
            return _fake_run("27.0.3\n")
        if cmd[1] == "compose":
            return _fake_run("v2.27.0\n")
        if cmd[1] == "info":
            return _fake_run("27.0.3\n")
        return _fake_run("", returncode=1)

    monkeypatch.setattr(docker_probe.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(docker_probe, "_current_user_in_docker_group", lambda: True)

    result = await docker_probe.probe()
    assert isinstance(result, DockerInfo)
    assert result.engine_version == "27.0.3"
    assert result.compose_version == "v2.27.0"
    assert result.daemon_reachable is True
    assert result.current_user_in_docker_group is True


async def test_probe_returns_not_detected_on_version_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(docker_probe.shutil, "which", lambda _x: "/usr/bin/docker")

    def fake_run(*_a, **_kw):
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr(docker_probe.subprocess, "run", fake_run)
    result = await docker_probe.probe()
    assert isinstance(result, NotDetected)
