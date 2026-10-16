"""Basit in-memory sabit-pencere hız sınırlayıcı.

Demo tek-process olduğu için yeterlidir; çok instance'lı kurulumda Redis
tabanlı bir çözümle değiştirilmelidir. Brute-force (login) ve kaynak
tüketimi (kamuya açık /v1/verify taraması) saldırılarını sınırlar.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request, name: str, limit: int, window_seconds: int) -> None:
    from .deps import client_ip

    key = f"{name}:{client_ip(request) or 'unknown'}"
    now = time.monotonic()
    cutoff = now - window_seconds
    bucket = _buckets[key]
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla istek; lütfen biraz sonra tekrar deneyin.",
        )
    bucket.append(now)
