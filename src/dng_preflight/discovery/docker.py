"""Probe: Docker Engine and Compose plugin presence on the host."""

import asyncio
import grp
import os
import shutil
import subprocess

from dng_preflight.models.snapshot import DockerInfo, NotDetected

_TIMEOUT_S = 5


def _run(cmd: list[str]) -> tuple[int, str]:
    """Run a fixed-path command and return (returncode, stdout). Empty on failure."""
    try:
        result = subprocess.run(  # noqa: S603 - cmd[0] resolved by shutil.which upstream
            cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
    except (subprocess.SubprocessError, OSError):
        return -1, ""
    return result.returncode, result.stdout.strip()


def _engine_version(docker_bin: str) -> str | None:
    code, out = _run([docker_bin, "version", "--format", "{{.Server.Version}}"])
    if code == 0 and out:
        return out
    code, out = _run([docker_bin, "--version"])
    if code == 0 and out:
        return out
    return None


def _compose_version(docker_bin: str) -> str | None:
    code, out = _run([docker_bin, "compose", "version", "--short"])
    if code == 0 and out:
        return out
    return None


def _daemon_reachable(docker_bin: str) -> bool:
    code, _ = _run([docker_bin, "info", "--format", "{{.ServerVersion}}"])
    return code == 0


def _current_user_in_docker_group() -> bool:
    try:
        group = grp.getgrnam("docker")
    except KeyError:
        return False
    user_gids = set(os.getgroups())
    if group.gr_gid in user_gids:
        return True
    try:
        login = os.getlogin()
    except OSError:
        return False
    return login in group.gr_mem


def _collect_sync() -> DockerInfo | NotDetected:
    docker_bin = shutil.which("docker")
    if docker_bin is None:
        return NotDetected(reason="docker CLI not found in PATH")
    engine = _engine_version(docker_bin)
    if engine is None:
        return NotDetected(reason="docker CLI present but `docker version` failed")
    return DockerInfo(
        engine_version=engine,
        compose_version=_compose_version(docker_bin),
        daemon_reachable=_daemon_reachable(docker_bin),
        current_user_in_docker_group=_current_user_in_docker_group(),
    )


async def probe() -> DockerInfo | NotDetected:
    """Detect Docker Engine + Compose presence and daemon reachability."""
    return await asyncio.to_thread(_collect_sync)
