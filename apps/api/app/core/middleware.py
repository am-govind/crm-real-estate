import hashlib
import json
import logging
import threading
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

log = logging.getLogger("landcrm.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, emits structured access logs and sets security headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if get_settings().env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        ctx = getattr(request.state, "ctx", None)
        log.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(elapsed_ms, 1),
                    "user_id": str(ctx.user_id) if ctx else None,
                    "tenant_id": str(ctx.tenant_id) if ctx and ctx.tenant_id else None,
                }
            )
        )
        return response


class _MemoryWindow:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, int]] = {}

    def hit(self, key: str, window: int) -> int:
        with self._lock:
            start, count = self._hits.get(key, (window, 0))
            if start != window:
                start, count = window, 0
            count += 1
            self._hits[key] = (start, count)
            if len(self._hits) > 100_000:
                self._hits = {k: v for k, v in self._hits.items() if v[0] == window}
            return count


class _RedisWindow:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url)

    def hit(self, key: str, window: int) -> int:
        k = f"landcrm:rl:{key}:{window}"
        pipe = self._r.pipeline()
        pipe.incr(k)
        pipe.expire(k, 120)
        return int(pipe.execute()[0])


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limit per credential (or client IP when anonymous)."""

    EXEMPT = ("/health", "/ready")

    def __init__(self, app, per_minute: int):
        super().__init__(app)
        self._limit = per_minute
        s = get_settings()
        self._store = _RedisWindow(s.redis_url) if s.queue_backend == "redis" else _MemoryWindow()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self._limit <= 0 or request.url.path in self.EXEMPT:
            return await call_next(request)
        cred = request.headers.get("authorization") or request.cookies.get(get_settings().session_cookie_name)
        ident = hashlib.sha256(cred.encode()).hexdigest()[:32] if cred else (request.client.host if request.client else "anon")
        window = int(time.time() // 60)
        try:
            count = self._store.hit(ident, window)
        except Exception:  # noqa: BLE001 - fail open if the limiter backend is unavailable
            return await call_next(request)
        if count > self._limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests", "details": {}}},
                headers={"Retry-After": str(60 - int(time.time()) % 60)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self._limit - count))
        return response
