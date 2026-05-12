"""Unit tests for the TLS probe."""

from __future__ import annotations

import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from dng_preflight.discovery import tls as tls_probe


def _self_signed_cert_der() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "dng.example.com"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test"),
        ]
    )
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("dng.example.com"), x509.DNSName("alt.example.com")]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


async def test_probe_observes_certificate_when_443_answers(monkeypatch: pytest.MonkeyPatch):
    der = _self_signed_cert_der()
    monkeypatch.setattr(tls_probe, "_fetch_peer_cert", lambda *_a, **_kw: der)
    result = await tls_probe.probe()
    assert result.answers_on_443 is True
    assert result.cn == "dng.example.com"
    assert "dng.example.com" in result.sans
    assert "alt.example.com" in result.sans
    assert result.key_algorithm.startswith("RSA-")
    assert result.issuer is not None


async def test_probe_reports_no_answer_when_connect_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tls_probe, "_fetch_peer_cert", lambda *_a, **_kw: None)
    result = await tls_probe.probe()
    assert result.answers_on_443 is False
    assert result.cn is None
    assert result.sans == []
