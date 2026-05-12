"""Probe: local interfaces, listening ports, default route, and egress IP."""

import asyncio
import platform
import shutil
import subprocess
from pathlib import Path

import httpx
import psutil

from dng_preflight.models.snapshot import NetworkInfo

_RELEVANT_PORTS = (80, 443, 8443)
_EGRESS_FALLBACK = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)
_EGRESS_TIMEOUT_S = 4.0


def _interfaces() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name, addrs in psutil.net_if_addrs().items():
        ips = [a.address for a in addrs if a.family.name in {"AF_INET", "AF_INET6"}]
        if ips:
            result[name] = ips
    return result


def _default_route_iface() -> str | None:
    """Parse /proc/net/route on Linux; on macOS shell out to `route -n get default`."""
    route_file = Path("/proc/net/route")
    if route_file.exists():
        try:
            for raw in route_file.read_text().splitlines()[1:]:
                parts = raw.split()
                if len(parts) >= 2 and parts[1] == "00000000":
                    return parts[0]
        except OSError:
            return None
        return None
    if platform.system() == "Darwin":
        route_bin = shutil.which("route")
        if route_bin is None:
            return None
        try:
            out = subprocess.run(  # noqa: S603 - route path resolved by shutil.which
                [route_bin, "-n", "get", "default"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        for raw in out.stdout.splitlines():
            line = raw.strip()
            if line.startswith("interface:"):
                return line.split(":", 1)[1].strip()
    return None


def _listening_ports() -> dict[int, str]:
    result: dict[int, str] = {}
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        return result
    for conn in conns:
        if conn.status != psutil.CONN_LISTEN or conn.laddr is None:
            continue
        port = conn.laddr.port
        if port not in _RELEVANT_PORTS:
            continue
        name = "unknown"
        if conn.pid is not None:
            try:
                name = psutil.Process(conn.pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                name = "unknown"
        result[port] = name
    return result


async def _egress_public_ip(client: httpx.AsyncClient) -> str | None:
    for url in _EGRESS_FALLBACK:
        try:
            resp = await client.get(url, timeout=_EGRESS_TIMEOUT_S)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            ip = resp.text.strip()
            if ip:
                return ip
    return None


async def probe() -> NetworkInfo:
    """Collect interfaces, listening ports, default route, and egress IP."""
    interfaces, listening, default_iface = await asyncio.gather(
        asyncio.to_thread(_interfaces),
        asyncio.to_thread(_listening_ports),
        asyncio.to_thread(_default_route_iface),
    )
    async with httpx.AsyncClient() as client:
        egress = await _egress_public_ip(client)
    return NetworkInfo(
        interfaces=interfaces,
        default_route_iface=default_iface,
        listening_ports=listening,
        egress_public_ip=egress,
    )
