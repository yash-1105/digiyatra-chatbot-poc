"""TEST-ONLY backend for browser E2E (never deployed; not in the Railway context).

Serves the real FastAPI app on 127.0.0.1 with:
* a throwaway SYNTHETIC SQLite database (health reports database.label == "synthetic"),
* the approved corpus + verified official video/channel records and the reviewed PIB supplements,
* deterministic grounded MOCK clients for Sarvam, Anthropic and Novita (no keys, no network),
* ALL non-loopback network connections blocked (proves chat works with external sources unreachable),
* application logs written to the given log file so tests can scan them for personal data.

    .venv/bin/python scripts/e2e_stack.py --port 8100 --log ../.cache/e2e/backend.log
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo


def _loopback_only(host) -> bool:
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return str(host) in {"localhost"}


def guard_network() -> list[str]:
    blocked: list[str] = []

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and (host.startswith("/") or _loopback_only(host)):
            return _real_connect(self, address)
        blocked.append(str(host))
        raise OSError("E2E stack: outbound network blocked")

    def getaddrinfo(host, *a, **k):
        if host is None or _loopback_only(host):
            return _real_getaddrinfo(host, *a, **k)
        blocked.append(str(host))
        raise OSError("E2E stack: outbound DNS blocked")

    socket.socket.connect = connect  # type: ignore[assignment]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    return blocked


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8100)
    p.add_argument("--log", type=Path, required=True)
    args = p.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.log, level=logging.INFO, force=True,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import uvicorn

    from evaluation.expanded import _offline_app

    tmp = Path(tempfile.mkdtemp(prefix="e2e-synthetic-"))
    app, _calls, _verified = _offline_app(tmp)
    blocked = guard_network()

    @app.get("/__e2e/blocked")  # test-only introspection: outbound attempts (must stay empty)
    def _blocked():
        return {"blocked_outbound": blocked}

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
