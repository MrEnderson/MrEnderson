"""URL safety validation and bounded fetching (v0.1.1).

Vendor-agnostic infrastructure for the research-fetch seam: whichever live
search/fetch vendor is eventually wired into `ResearchProvider.fetch()` (see
app/tools/research_tools.py) must route through `validate_url()` before
connecting and `bounded_get()` to perform the actual request. This module has
no vendor logic of its own and makes no network calls unless `bounded_get` is
called.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_REDIRECTS = 3
DEFAULT_MAX_BYTES = 2_000_000

_ALLOWED_SCHEMES = ("http", "https")
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}
_ALLOWED_CONTENT_TYPE_PREFIXES = (
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
)


class UnsafeURLError(Exception):
    pass


def validate_url(url: str) -> str:
    """Raises UnsafeURLError for anything that isn't a plain public http(s) URL.

    Rejects: non-http(s) schemes (including file://), missing host, localhost,
    loopback/private/link-local/reserved/multicast IP literals, and any
    hostname that resolves to one of those at validation time.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r} (only http/https allowed)")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise UnsafeURLError(f"Blocked host: {host}")

    _reject_unsafe_ip_literal(host)
    _reject_unsafe_resolved_address(host)
    return url


def _reject_unsafe_ip_literal(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    _assert_public(ip, host)


def _reject_unsafe_resolved_address(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        # Cannot resolve at validation time; the caller's connection will
        # still fail safely, but we do not silently allow it here either.
        return
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        _assert_public(ip, host)


def _assert_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str) -> None:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        raise UnsafeURLError(f"Blocked private/internal address for host {host}: {ip}")


async def bounded_get(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """Fetch `url` with SSRF guards, a byte cap, and a content-type allowlist.

    Every redirect hop is re-validated with `validate_url` before being
    followed. Raises UnsafeURLError for anything that fails those checks, and
    lets httpx's own TimeoutException propagate for timeouts.
    """
    import httpx

    validate_url(url)

    async with httpx.AsyncClient(
        follow_redirects=True, max_redirects=max_redirects, timeout=timeout_seconds
    ) as client:
        async with client.stream("GET", url) as response:
            for hop in [*response.history, response]:
                validate_url(str(hop.url))

            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and not any(
                content_type.startswith(p) for p in _ALLOWED_CONTENT_TYPE_PREFIXES
            ):
                raise UnsafeURLError(f"Unsupported content-type: {content_type}")

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise UnsafeURLError(f"Response exceeded max size of {max_bytes} bytes")
                chunks.append(chunk)
            return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
