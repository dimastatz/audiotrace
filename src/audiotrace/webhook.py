"""A small webhook receiver for end-of-call events (PRD 0014).

    audiotrace serve --mapping mapping.yaml --out reports/ --port 8080

Accepts ``POST`` requests whose body is the event JSON, checks an HMAC-SHA256
signature made with a shared secret, maps the payload with a
:class:`~audiotrace.adapters.CustomAdapter`, and answers ``202`` right away.
A background worker then downloads the recording, runs ``analyze()``, and
writes ``<call_id>.json`` / ``.html`` reports into the output directory.

Signature: the sender puts ``sha256=<hex HMAC-SHA256 of the raw body>`` in the
``X-AudioTrace-Signature`` header (header name configurable).

Standard library only, for modest volume: one worker, no retries, no queue
persistence. Heavier users call ``CustomAdapter.parse()`` from their own
service instead.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from audiotrace.adapters import AdapterError, CustomAdapter, ProviderCall
from audiotrace.models import CallReport

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-AudioTrace-Signature"
MAX_BODY_BYTES = 1_000_000

Analyzer = Callable[[ProviderCall], CallReport]


def sign(body: bytes, secret: str) -> str:
    """The signature header value a sender should attach to ``body``."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(body: bytes, secret: str, signature: str | None) -> bool:
    """Constant-time check of ``signature`` against ``body``."""
    return bool(signature) and hmac.compare_digest(sign(body, secret), str(signature).strip())


def default_analyzer(call: ProviderCall) -> CallReport:
    from audiotrace.core import analyze

    return analyze(call.audio, call.metadata, num_speakers=2)


@dataclass
class WebhookApp:
    """The receiver's logic, independent of the HTTP server (testable)."""

    adapter: CustomAdapter
    secret: str
    out_dir: Path
    analyzer: Analyzer = default_analyzer
    signature_header: str = SIGNATURE_HEADER
    jobs: queue.Queue[Any] = field(default_factory=queue.Queue)

    def handle(self, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        """Validate one request; on success queue it. Returns (status, JSON body)."""
        signature = next(
            (v for k, v in headers.items() if k.lower() == self.signature_header.lower()), None
        )
        if not verify(body, self.secret, signature):
            return 401, {"error": "bad or missing signature"}
        try:
            payload = json.loads(body)
            _, metadata = self.adapter.extract(payload)
        except json.JSONDecodeError:
            return 400, {"error": "body is not JSON"}
        except AdapterError as exc:
            return 422, {"error": str(exc)}
        self.jobs.put(payload)
        return 202, {"call_id": metadata["call_id"], "status": "queued"}

    def process(self, payload: Any) -> Path:
        """Download, analyze, and write the report for one queued payload."""
        from audiotrace.report import write_report

        call = self.adapter.parse(payload)
        report = self.analyzer(call)
        stem = Path(call.audio).stem
        paths = write_report(report, self.out_dir, stem=stem)
        logger.info("Wrote %s", paths["json"])
        return paths["json"]

    def work(self) -> None:
        """Worker loop: process queued payloads until ``None`` is queued."""
        while True:
            payload = self.jobs.get()
            try:
                if payload is None:
                    return
                self.process(payload)
            except Exception:  # keep serving; one bad call mustn't stop the worker
                logger.exception("Failed to process webhook payload")
            finally:
                self.jobs.task_done()


def make_server(app: WebhookApp, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    """An HTTP server routing POSTs to ``app``. Start ``app.work`` in a thread
    (or use :func:`serve`) so queued calls get processed."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self.close_connection = True  # the unread body can't be reused
                self._reply(413, {"error": "body too large"})
                return
            body = self.rfile.read(length)
            status, reply = app.handle(body, dict(self.headers.items()))
            self._reply(status, reply)

        def do_GET(self) -> None:  # noqa: N802
            self._reply(200, {"status": "ok"})

        def _reply(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            logger.info("%s %s", self.address_string(), format % args)

    return ThreadingHTTPServer((host, port), Handler)


def serve(app: WebhookApp, host: str = "127.0.0.1", port: int = 8080) -> None:  # pragma: no cover
    """Run the receiver until interrupted."""
    worker = threading.Thread(target=app.work, daemon=True)
    worker.start()
    server = make_server(app, host, port)
    print(f"Listening on http://{host}:{server.server_port} — reports → {app.out_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.jobs.put(None)
        worker.join(timeout=5)
