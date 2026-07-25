"""
Runtime concerns that a Kubernetes deployment needs from the application.

DocuChat itself is unchanged demo logic; everything a cluster has to talk to
lives here so the two stay easy to tell apart:

  * structured (JSON) request logs on stdout — the only log sink a pod has
  * ``/healthz``  liveness  — is this process still working?
  * ``/readyz``   readiness — should this pod receive traffic right now?
  * ``/metrics``  Prometheus exposition (optional dependency)
  * ``DocumentStore`` — optional Postgres persistence so documents survive a
    pod restart. Without ``DATABASE_URL`` the app keeps its original
    zero-config in-memory behaviour.

Liveness and readiness deliberately check *different* things. Liveness must not
depend on Postgres: if the database blips and liveness fails, the kubelet
restarts every replica at once and turns a recoverable dependency outage into a
full outage. Readiness may depend on Postgres — an unready pod is pulled from
the Service endpoints but keeps running, and rejoins on its own.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from typing import Callable, List, Optional

# Imported at module scope on purpose: `from __future__ import annotations`
# turns annotations into strings, and FastAPI resolves them against this
# module's globals. A function-local import would make `response: Response`
# unresolvable, and FastAPI would treat it as a query parameter (HTTP 422).
from fastapi import Response

SERVICE_NAME = os.getenv("SERVICE_NAME", "docuchat-api")
SERVICE_VERSION = os.getenv("APP_VERSION", "dev")
POD_NAME = os.getenv("POD_NAME", "local")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

log = logging.getLogger("docuchat")


# --------------------------------------------------------------------------- #
# Structured logging
# --------------------------------------------------------------------------- #
class JsonFormatter(logging.Formatter):
    """One JSON object per line — what a log shipper (Loki/ELK) expects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "pod": POD_NAME,
            "msg": record.getMessage(),
        }
        # Anything passed via logger.info(..., extra={"fields": {...}}).
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    # uvicorn's lifecycle messages go through our formatter; propagate=False
    # stops each line from also reaching the root handler and printing twice.
    for noisy in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(noisy)
        uv.handlers = [handler]
        uv.propagate = False

    # uvicorn's plain-text access log is replaced by the middleware in
    # install(), which also records duration and request id. This module is
    # imported after uvicorn has configured logging, so silencing it here wins
    # over the server's own --no-access-log handling.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True


# --------------------------------------------------------------------------- #
# Optional Postgres persistence
# --------------------------------------------------------------------------- #
class DocumentStore:
    """
    Write-through document persistence.

    Enabled only when DATABASE_URL is set. Every failure is logged and swallowed
    so a database outage degrades the pod to "not ready" instead of crashing it.
    """

    def __init__(self, url: str = DATABASE_URL) -> None:
        self.url = url
        self.enabled = bool(url)
        self._ping_cache: tuple[float, bool] = (0.0, False)
        self._driver = None
        if self.enabled:
            try:
                import psycopg  # imported lazily: optional dependency

                self._driver = psycopg
            except ImportError:
                log.warning("psycopg not installed — persistence disabled")
                self.enabled = False

    # -- internals ---------------------------------------------------------- #
    def _connect(self):
        return self._driver.connect(self.url, connect_timeout=5)

    # -- lifecycle ---------------------------------------------------------- #
    def init_schema(self) -> bool:
        """Idempotent: the Postgres init hook only runs on a fresh volume."""
        if not self.enabled:
            return False
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        id         text PRIMARY KEY,
                        title      text NOT NULL,
                        content    text NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001 — degrade, never crash
            log.warning("schema init failed", extra={"fields": {"error": str(exc)}})
            return False

    def load_all(self) -> List[dict]:
        if not self.enabled:
            return []
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT id, title, content FROM documents ORDER BY created_at")
                return [{"id": r[0], "title": r[1], "text": r[2]} for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log.warning("document load failed", extra={"fields": {"error": str(exc)}})
            return []

    def save(self, doc: dict, _retry: bool = True) -> None:
        if not self.enabled:
            return
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents (id, title, content) VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title,
                                                   content = EXCLUDED.content
                    """,
                    (doc["id"], doc["title"], doc["text"]),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            # The table can be missing if the database was reachable at startup
            # but empty (restored volume, dropped schema). Create it and retry
            # once rather than losing the write.
            if _retry and self.init_schema():
                self.save(doc, _retry=False)
                return
            log.warning("document save failed", extra={"fields": {"error": str(exc)}})

    def delete(self, doc_id: str) -> None:
        if not self.enabled:
            return
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("document delete failed", extra={"fields": {"error": str(exc)}})

    # -- health ------------------------------------------------------------- #
    def ping(self, ttl: float = 2.0, quiet: bool = False) -> bool:
        """
        Is the store actually usable?

        Deliberately stronger than "the connection opened": it asserts the
        documents table exists. A pod that can reach Postgres but has no schema
        accepts uploads and drops them on the floor, and a readiness check that
        only ran SELECT 1 would call that healthy.

        Cached briefly so readiness probes don't hammer the database.
        """
        if not self.enabled:
            return True  # nothing to depend on
        now = time.monotonic()
        cached_at, cached = self._ping_cache
        if now - cached_at < ttl:
            return cached
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.documents')")
                ok = cur.fetchone()[0] is not None
            if not ok and not quiet:
                log.warning("database reachable but documents table is missing")
        except Exception as exc:  # noqa: BLE001
            if not quiet:
                log.warning("database ping failed", extra={"fields": {"error": str(exc)}})
            ok = False
        self._ping_cache = (now, ok)
        return ok

    def wait_reachable(self, timeout: float = 90.0) -> bool:
        """
        Block until Postgres answers, or give up and run in memory.

        Pods routinely start before the database's DNS record exists — the
        StatefulSet may still be scheduling. Without this the first connection
        fails with "Temporary failure in name resolution", the schema is never
        created, and every later write is silently lost.
        """
        if not self.enabled:
            return True
        deadline = time.monotonic() + timeout
        delay = 0.5
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            try:
                with self._connect() as conn, conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                if attempts > 1:
                    log.info(
                        "database reachable",
                        extra={"fields": {"attempts": attempts}},
                    )
                return True
            except Exception:  # noqa: BLE001 — expected while the DB boots
                time.sleep(delay)
                delay = min(delay * 2, 5.0)
        log.warning(
            "database unreachable — continuing without persistence",
            extra={"fields": {"timeout_s": timeout, "attempts": attempts}},
        )
        return False


# --------------------------------------------------------------------------- #
# Wiring into FastAPI
# --------------------------------------------------------------------------- #
def install(app, store: "DocumentStore", is_indexed: Callable[[], bool]) -> None:
    """Attach access logging, health endpoints and metrics to a FastAPI app."""
    started = time.monotonic()

    @app.middleware("http")
    async def access_log(request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        begin = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - begin) * 1000, 1)
        # Probe traffic is high-volume and boring — keep it out of the log.
        if request.url.path not in ("/healthz", "/readyz", "/metrics"):
            log.info(
                "request",
                extra={
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": duration_ms,
                        "request_id": request_id,
                    }
                },
            )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        """Liveness: the process is up and serving. Never touches the database."""
        return {"status": "ok", "uptime_s": round(time.monotonic() - started, 1), "pod": POD_NAME}

    @app.get("/readyz", include_in_schema=False)
    def readyz(response: Response) -> dict:
        """Readiness: this pod can actually serve a question right now."""
        checks = {"index": is_indexed(), "database": store.ping()}
        ready = all(checks.values())
        if not ready:
            response.status_code = 503
        return {"status": "ready" if ready else "not-ready", "checks": checks, "pod": POD_NAME}

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            excluded_handlers=["/healthz", "/readyz", "/metrics"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    except ImportError:
        log.warning("prometheus-fastapi-instrumentator not installed — /metrics disabled")


def startup_log(**fields) -> None:
    log.info("startup", extra={"fields": fields})
