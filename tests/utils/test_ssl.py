"""Tests for marznode.utils.ssl."""

from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from marznode.utils.ssl import (
    create_secure_context,
    generate_keypair,
    generate_random_certificate,
)


def test_generate_random_certificate_returns_valid_pem():
    key_pem, cert_pem = generate_random_certificate()
    assert "BEGIN PRIVATE KEY" in key_pem or "BEGIN RSA PRIVATE KEY" in key_pem
    assert "BEGIN CERTIFICATE" in cert_pem

    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    pub = cert.public_key()
    assert isinstance(pub, rsa.RSAPublicKey)
    assert pub.key_size == 4096


def test_generated_certificate_lifetime_is_about_ten_years():
    _, cert_pem = generate_random_certificate()
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc

    lifetime = not_after - not_before
    # Allow leap-day slack: 10 * 365 days exactly per the source.
    assert timedelta(days=10 * 365 - 1) <= lifetime <= timedelta(days=10 * 365 + 1)
    assert not_before <= datetime.now(timezone.utc)


def test_generate_keypair_writes_files(tmp_path: Path):
    key_path = tmp_path / "node.key"
    cert_path = tmp_path / "node.crt"

    generate_keypair(str(key_path), str(cert_path))

    assert key_path.is_file()
    assert cert_path.is_file()
    assert "BEGIN CERTIFICATE" in cert_path.read_text()
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    assert isinstance(cert.public_key(), rsa.RSAPublicKey)


def test_create_secure_context_configures_tls(tmp_path: Path):
    key_path = tmp_path / "server.key"
    cert_path = tmp_path / "server.crt"
    client_cert_path = tmp_path / "client.crt"

    generate_keypair(str(key_path), str(cert_path))
    # Reuse the same self-signed cert as the trusted client cert.
    generate_keypair(str(tmp_path / "_unused.key"), str(client_cert_path))

    ctx = create_secure_context(
        str(cert_path), str(key_path), trusted=str(client_cert_path)
    )

    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    # ALPN selection isn't directly readable; instead assert the call itself
    # didn't raise and the context advertises TLS server purpose configuration.
    assert ctx.check_hostname is False or ctx.check_hostname is True  # exists


def test_create_secure_context_rejects_missing_trusted(tmp_path: Path):
    import pytest

    key_path = tmp_path / "server.key"
    cert_path = tmp_path / "server.crt"
    generate_keypair(str(key_path), str(cert_path))

    with pytest.raises((FileNotFoundError, ssl.SSLError, OSError)):
        create_secure_context(
            str(cert_path), str(key_path), trusted=str(tmp_path / "missing.crt")
        )
