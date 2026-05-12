"""Probe: OS, hardware, and security-mode facts about the host."""

import asyncio
import os
import platform
import shutil
import subprocess
from pathlib import Path

import psutil

from dng_preflight.models.snapshot import SystemInfo


def _read_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dict. Returns {} when the file is absent."""
    path = Path("/etc/os-release")
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _detect_selinux_mode() -> str | None:
    """Return 'enforcing' | 'permissive' | 'disabled' on RHEL-family, else None."""
    enforce = Path("/sys/fs/selinux/enforce")
    if enforce.exists():
        try:
            return {"1": "enforcing", "0": "permissive"}.get(
                enforce.read_text().strip(), "disabled"
            )
        except OSError:
            return None
    getenforce = shutil.which("getenforce")
    if getenforce is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - getenforce is a fixed path resolved by shutil.which
            [getenforce], capture_output=True, text=True, timeout=2, check=False
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip().lower() or None


def _detect_apparmor_active() -> bool | None:
    """True if AppArmor is loaded, False on Linux without it, None on non-Linux."""
    if platform.system() != "Linux":
        return None
    return Path("/sys/kernel/security/apparmor").is_dir()


def _detect_domain_joined() -> bool:
    """Domain-join heuristic: `realm list` non-empty OR /etc/krb5.conf has realms."""
    realm = shutil.which("realm")
    if realm is not None:
        try:
            out = subprocess.run(  # noqa: S603 - realm path resolved by shutil.which
                [realm, "list"], capture_output=True, text=True, timeout=2, check=False
            )
            if out.returncode == 0 and out.stdout.strip():
                return True
        except (subprocess.SubprocessError, OSError):
            pass
    krb5 = Path("/etc/krb5.conf")
    if not krb5.exists():
        return False
    try:
        text = krb5.read_text(errors="ignore")
    except OSError:
        return False
    in_realms = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            in_realms = line.lower().startswith("[realms]")
            continue
        if in_realms and "=" in line:
            return True
    return False


def _collect_sync() -> SystemInfo:
    """Gather system facts synchronously. Called via asyncio.to_thread."""
    os_release = _read_os_release()
    uname = platform.uname()
    distro = os_release.get("ID") or uname.system.lower()
    distro_version = os_release.get("VERSION_ID") or uname.release.split("-")[0]
    return SystemInfo(
        platform=platform.system().lower(),
        distro=distro,
        distro_version=distro_version,
        kernel=uname.release,
        arch=uname.machine,
        ram_mb=int(psutil.virtual_memory().total // (1024 * 1024)),
        cpu_count=os.cpu_count() or psutil.cpu_count(logical=True) or 1,
        selinux_mode=_detect_selinux_mode(),
        apparmor_active=_detect_apparmor_active(),
        domain_joined=_detect_domain_joined(),
    )


async def probe() -> SystemInfo:
    """Collect host OS, hardware, and security-mode facts."""
    return await asyncio.to_thread(_collect_sync)
