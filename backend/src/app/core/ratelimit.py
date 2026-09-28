"""Shared rate-limiting primitives.

`client_identifier` is the rate-limit identity function. It uses the socket
peer address and only trusts ``X-Forwarded-For`` when the peer is in the
explicitly configured trusted-proxy networks (``RATE_LIMIT_TRUSTED_PROXY``).
Arbitrary client-supplied forwarding headers are never trusted by default,
which prevents spoofing the rate-limit key.

The limiter is created with ``enabled=settings.rate_limit_enabled`` so local
development and the test suite (which set ``RATE_LIMIT_ENABLED=false``) behave
exactly as before while production enforces limits.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from slowapi import Limiter

from app.core.config import settings


def client_identifier(request) -> str:
    """Return the identity used for rate-limit accounting.

    1. Default: the direct socket peer (``request.client.host``). No header is
       consulted, so a client can never choose its own key.
    2. Trusted-proxy mode: when the peer IP is inside
       ``settings.trusted_proxy_networks``, the leftmost entry of
       ``X-Forwarded-For`` (the true client) is used. The value is validated as
       an IP address; anything malformed falls back to the socket peer.
    """
    peer = request.client.host if request.client else "unknown"
    networks = settings.trusted_proxy_networks
    if not networks:
        return peer
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in network for network in networks):
        return peer
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        leftmost = forwarded.split(",")[0].strip()
        try:
            ipaddress.ip_address(leftmost)
            return leftmost
        except ValueError:
            return peer
    return peer


def _default_limits() -> list[Any]:
    # Limit strings are homogeneous; Any keeps mypy happy with slowapi's
    # `list[str | Callable[..., str]]` parameter (list is invariant).
    return [settings.rate_limit_default] if settings.rate_limit_enabled else []


def route_limit(limit: str):
    """Decorator factory: enforce ``limit`` when rate limiting is enabled,
    otherwise pass the endpoint through untouched (local dev, test suite)."""

    def decorator(fn):
        if not settings.rate_limit_enabled:
            return fn
        return limiter.limit(limit)(fn)

    return decorator


limiter = Limiter(
    key_func=client_identifier,
    default_limits=_default_limits(),
    enabled=settings.rate_limit_enabled,
    headers_enabled=False,
    retry_after="delta-seconds",
)

__all__ = ["limiter", "client_identifier", "route_limit"]