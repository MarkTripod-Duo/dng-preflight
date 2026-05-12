"""Run every probe in parallel and assemble an `EnvironmentSnapshot`.

Budget: 10 seconds per probe, 30 seconds total. Probes whose result type
includes `NotDetected` (docker, time_sync, firewall) downgrade to
`NotDetected(reason="timeout")` if they exceed their per-probe budget.
Probes whose result type does NOT include `NotDetected` (system, network,
dns, tls, duo_reachability) are expected to honour their own internal
timeouts; if they breach the per-probe budget the aggregator raises
`TimeoutError`, since that indicates a probe bug rather than a missing tool.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from dng_preflight.discovery import (
    dns as dns_probe,
)
from dng_preflight.discovery import (
    docker as docker_probe,
)
from dng_preflight.discovery import (
    duo_reachability as duo_probe,
)
from dng_preflight.discovery import (
    firewall as firewall_probe,
)
from dng_preflight.discovery import (
    network as network_probe,
)
from dng_preflight.discovery import (
    system as system_probe,
)
from dng_preflight.discovery import (
    time_sync as time_sync_probe,
)
from dng_preflight.discovery import (
    tls as tls_probe,
)
from dng_preflight.models.snapshot import EnvironmentSnapshot, NotDetected

_PER_PROBE_TIMEOUT_S = 10.0
_TOTAL_BUDGET_S = 30.0


async def _required[T](coro: Coroutine[Any, Any, T]) -> T:
    """Apply the per-probe timeout. Raises `TimeoutError` on breach."""
    return await asyncio.wait_for(coro, timeout=_PER_PROBE_TIMEOUT_S)


async def _optional[T](coro: Coroutine[Any, Any, T | NotDetected], label: str) -> T | NotDetected:
    """Apply the per-probe timeout. Downgrades to `NotDetected` on breach."""
    try:
        return await asyncio.wait_for(coro, timeout=_PER_PROBE_TIMEOUT_S)
    except TimeoutError:
        return NotDetected(reason=f"{label} probe exceeded {_PER_PROBE_TIMEOUT_S:.0f}s timeout")


async def collect(hostname: str) -> EnvironmentSnapshot:
    """Run every probe in parallel and return a fully-populated snapshot."""

    async def _run() -> EnvironmentSnapshot:
        async with asyncio.TaskGroup() as tg:
            sys_task = tg.create_task(_required(system_probe.probe()))
            docker_task = tg.create_task(_optional(docker_probe.probe(), "docker"))
            network_task = tg.create_task(_required(network_probe.probe()))
            dns_task = tg.create_task(_required(dns_probe.probe(hostname)))
            tls_task = tg.create_task(_required(tls_probe.probe()))
            time_sync_task = tg.create_task(_optional(time_sync_probe.probe(), "time_sync"))
            firewall_task = tg.create_task(_optional(firewall_probe.probe(), "firewall"))
            duo_task = tg.create_task(_required(duo_probe.probe()))
        return EnvironmentSnapshot(
            captured_at=datetime.now(UTC).isoformat(),
            hostname_planned=hostname,
            system=sys_task.result(),
            docker=docker_task.result(),
            network=network_task.result(),
            dns=dns_task.result(),
            tls=tls_task.result(),
            time_sync=time_sync_task.result(),
            firewall=firewall_task.result(),
            duo_reachability=duo_task.result(),
        )

    return await asyncio.wait_for(_run(), timeout=_TOTAL_BUDGET_S)
