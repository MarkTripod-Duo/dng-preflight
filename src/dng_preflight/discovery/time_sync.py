"""Probe: time-sync daemon state and current offset from pool.ntp.org."""

from __future__ import annotations

import asyncio
import shutil
import socket
import struct
import subprocess
import time

from dng_preflight.models.snapshot import NotDetected, TimeSyncState

_NTP_HOST = "pool.ntp.org"
_NTP_PORT = 123
_NTP_TIMEOUT_S = 3.0
_NTP_PACKET = b"\x1b" + b"\x00" * 47  # mode 3 client, no auth
_NTP_EPOCH_OFFSET = 2_208_988_800  # seconds between 1900 and 1970


def _query_ntp_offset() -> float | None:
    """Single UDP query to pool.ntp.org. Returns offset in seconds, or None on failure."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(_NTP_TIMEOUT_S)
            t1 = time.time()
            sock.sendto(_NTP_PACKET, (_NTP_HOST, _NTP_PORT))
            data, _ = sock.recvfrom(48)
            t4 = time.time()
    except (TimeoutError, OSError):
        return None
    if len(data) < 48:
        return None
    # bytes 40..47: transmit timestamp (seconds since 1900, fixed-point)
    secs, frac = struct.unpack("!II", data[40:48])
    server_time = secs - _NTP_EPOCH_OFFSET + frac / 2**32
    # midpoint round-trip estimate
    return server_time - (t1 + t4) / 2


def _detect_daemon() -> tuple[str, str | None]:
    """Return (daemon_name, sync_source). daemon='none' when nothing is running."""
    chronyc = shutil.which("chronyc")
    if chronyc is not None:
        try:
            out = subprocess.run(  # noqa: S603 - chronyc resolved via shutil.which
                [chronyc, "tracking"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (subprocess.SubprocessError, OSError):
            out = None
        if out is not None and out.returncode == 0:
            for line in out.stdout.splitlines():
                if line.lower().startswith("reference id"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        return "chronyd", parts[1].strip() or None
            return "chronyd", None
    ntpq = shutil.which("ntpq")
    if ntpq is not None:
        try:
            out = subprocess.run(  # noqa: S603 - ntpq resolved via shutil.which
                [ntpq, "-pn"], capture_output=True, text=True, timeout=2, check=False
            )
        except (subprocess.SubprocessError, OSError):
            out = None
        if out is not None and out.returncode == 0:
            for line in out.stdout.splitlines():
                if line.startswith("*"):
                    return "ntpd", line[1:].split()[0]
            return "ntpd", None
    timedatectl = shutil.which("timedatectl")
    if timedatectl is not None:
        try:
            out = subprocess.run(  # noqa: S603 - timedatectl resolved via shutil.which
                [timedatectl, "show"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (subprocess.SubprocessError, OSError):
            out = None
        if out is not None and out.returncode == 0:
            ntp_enabled = "NTP=yes" in out.stdout
            synced = "NTPSynchronized=yes" in out.stdout
            if ntp_enabled or synced:
                return "systemd-timesyncd", None
    return "none", None


def _collect_sync() -> TimeSyncState | NotDetected:
    daemon, source = _detect_daemon()
    offset = _query_ntp_offset()
    if daemon == "none" and offset is None:
        return NotDetected(reason="no time-sync daemon detected and pool.ntp.org unreachable")
    return TimeSyncState(daemon=daemon, sync_source=source, offset_seconds=offset)


async def probe() -> TimeSyncState | NotDetected:
    """Detect chronyd/ntpd/timesyncd and measure offset from pool.ntp.org."""
    return await asyncio.to_thread(_collect_sync)
