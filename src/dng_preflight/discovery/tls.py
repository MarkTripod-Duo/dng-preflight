"""Probe: TLS certificate observed on the local host's port 443, if anything answers."""

from __future__ import annotations

import asyncio
import socket
import ssl

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa

from dng_preflight.models.snapshot import TlsObservation

_CONNECT_TIMEOUT_S = 3.0


def _key_algorithm(cert: x509.Certificate) -> str:
    pub = cert.public_key()
    if isinstance(pub, rsa.RSAPublicKey):
        return f"RSA-{pub.key_size}"
    if isinstance(pub, ec.EllipticCurvePublicKey):
        return f"EC-{pub.curve.name}"
    if isinstance(pub, dsa.DSAPublicKey):
        return f"DSA-{pub.key_size}"
    if isinstance(pub, ed25519.Ed25519PublicKey):
        return "Ed25519"
    if isinstance(pub, ed448.Ed448PublicKey):
        return "Ed448"
    return type(pub).__name__


def _extract_sans(cert: x509.Certificate) -> list[str]:
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    return sorted(str(name.value) for name in ext.value)


def _extract_cn(cert: x509.Certificate) -> str | None:
    cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    if not cn_attrs:
        return None
    return str(cn_attrs[0].value)


def _fetch_peer_cert(host: str, port: int) -> bytes | None:
    """Connect, complete TLS handshake, and return the peer cert DER bytes."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT_S) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as tls,
        ):
            return tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError):
        return None


def _collect_sync() -> TlsObservation:
    cert_bytes = _fetch_peer_cert("127.0.0.1", 443)
    if cert_bytes is None:
        return TlsObservation(answers_on_443=False)
    try:
        cert = x509.load_der_x509_certificate(cert_bytes)
    except ValueError:
        return TlsObservation(answers_on_443=True)
    return TlsObservation(
        answers_on_443=True,
        cn=_extract_cn(cert),
        sans=_extract_sans(cert),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        issuer=cert.issuer.rfc4514_string(),
        key_algorithm=_key_algorithm(cert),
    )


async def probe() -> TlsObservation:
    """Observe whatever TLS cert is currently presented on 127.0.0.1:443."""
    return await asyncio.to_thread(_collect_sync)
