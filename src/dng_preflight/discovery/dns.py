"""Probe: DNS resolution for the planned hostname across public resolvers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import dns.asyncresolver
import dns.exception
import dns.rdatatype
import dns.resolver
import dns.reversename

from dng_preflight.models.snapshot import DnsResolution

_PUBLIC_RESOLVERS = ("1.1.1.1", "8.8.8.8", "9.9.9.9")
_QUERY_TIMEOUT_S = 3.0


async def _query(hostname: str, rdtype: str, resolver_ip: str) -> list[str]:
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.timeout = _QUERY_TIMEOUT_S
    resolver.lifetime = _QUERY_TIMEOUT_S
    try:
        answer = await resolver.resolve(hostname, rdtype)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        return []
    return sorted(rdata.to_text() for rdata in answer)


async def _reverse_ptr(ip: str) -> str | None:
    if not ip:
        return None
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = list(_PUBLIC_RESOLVERS)
    resolver.timeout = _QUERY_TIMEOUT_S
    resolver.lifetime = _QUERY_TIMEOUT_S
    try:
        rev = dns.reversename.from_address(ip)
        answer = await resolver.resolve(rev, "PTR")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        return None
    return str(answer[0]).rstrip(".") if len(answer) else None


def _local_resolvers() -> list[str]:
    path = Path("/etc/resolv.conf")
    if not path.exists():
        return []
    result: list[str] = []
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    result.append(parts[1])
    except OSError:
        return []
    return result


async def probe(hostname: str) -> DnsResolution:
    """Resolve `hostname` against public resolvers + capture local nameservers."""
    a_tasks = {ip: _query(hostname, "A", ip) for ip in _PUBLIC_RESOLVERS}
    aaaa_tasks = {ip: _query(hostname, "AAAA", ip) for ip in _PUBLIC_RESOLVERS}
    a_results, aaaa_results = await asyncio.gather(
        asyncio.gather(*a_tasks.values()),
        asyncio.gather(*aaaa_tasks.values()),
    )
    a_records = dict(zip(_PUBLIC_RESOLVERS, a_results, strict=True))
    aaaa_records = dict(zip(_PUBLIC_RESOLVERS, aaaa_results, strict=True))

    first_a: str | None = next(
        (rr for rs in a_records.values() for rr in rs),
        None,
    )
    reverse = await _reverse_ptr(first_a) if first_a else None

    return DnsResolution(
        hostname=hostname,
        a_records=a_records,
        aaaa_records=aaaa_records,
        reverse_ptr=reverse,
        local_resolvers=_local_resolvers(),
    )
