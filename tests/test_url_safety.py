"""URL safety validation and bounded fetching. No real network access —
hostname resolution is monkeypatched so these tests are deterministic offline."""
from __future__ import annotations

import socket

import httpx
import pytest

from app.tools.url_safety import UnsafeURLError, bounded_get, validate_url

_RealAsyncClient = httpx.AsyncClient


def _fake_getaddrinfo(ip: str):
    def _inner(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _inner


def _patch_async_client_with_transport(monkeypatch, transport: httpx.MockTransport) -> None:
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(*a, transport=transport, **kw)
    )


# --- validate_url ------------------------------------------------------


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        validate_url("file:///etc/passwd")


def test_rejects_ftp_scheme():
    with pytest.raises(UnsafeURLError):
        validate_url("ftp://example.com/file")


def test_rejects_localhost_hostname():
    with pytest.raises(UnsafeURLError):
        validate_url("http://localhost/admin")


def test_rejects_loopback_ip_literal():
    with pytest.raises(UnsafeURLError):
        validate_url("http://127.0.0.1/admin")


def test_rejects_private_ip_literal():
    with pytest.raises(UnsafeURLError):
        validate_url("http://10.0.0.5/internal")


def test_rejects_link_local_ip_literal():
    with pytest.raises(UnsafeURLError):
        validate_url("http://169.254.169.254/latest/meta-data")


def test_rejects_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.1.2.3"))
    with pytest.raises(UnsafeURLError):
        validate_url("http://internal.example.com/")


def test_accepts_hostname_resolving_to_public_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert validate_url("https://example.com/page") == "https://example.com/page"


def test_rejects_url_with_no_host():
    with pytest.raises(UnsafeURLError):
        validate_url("http://")


# --- bounded_get ---------------------------------------------------------


async def test_bounded_get_returns_body_for_allowed_content_type(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>hi</p>")

    transport = httpx.MockTransport(handler)
    _patch_async_client_with_transport(monkeypatch, transport)

    body = await bounded_get("https://example.com/page")
    assert "hi" in body


async def test_bounded_get_rejects_disallowed_content_type(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    transport = httpx.MockTransport(handler)
    _patch_async_client_with_transport(monkeypatch, transport)

    with pytest.raises(UnsafeURLError):
        await bounded_get("https://example.com/file.pdf")


async def test_bounded_get_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x" * 1000)

    transport = httpx.MockTransport(handler)
    _patch_async_client_with_transport(monkeypatch, transport)

    with pytest.raises(UnsafeURLError):
        await bounded_get("https://example.com/big", max_bytes=100)


async def test_bounded_get_propagates_timeout(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    transport = httpx.MockTransport(handler)
    _patch_async_client_with_transport(monkeypatch, transport)

    with pytest.raises(httpx.TimeoutException):
        await bounded_get("https://example.com/slow", timeout_seconds=0.01)


async def test_bounded_get_rejects_url_before_any_network_call(monkeypatch):
    def _should_not_be_called(*a, **kw):
        raise AssertionError("AsyncClient must not be constructed for an unsafe URL")

    monkeypatch.setattr(httpx, "AsyncClient", _should_not_be_called)
    with pytest.raises(UnsafeURLError):
        await bounded_get("http://localhost/admin")
