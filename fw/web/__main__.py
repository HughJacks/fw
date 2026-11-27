"""python -m fw.web [--port 8020] [--no-open] [--code-stamp]"""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from fw import store
from fw.web import current, visits
from fw.web.server import Handler

PORT = 8020
JSON_LATER = 1.0   # s: the store's .json copy written this long after the last save


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m fw.web", description="fw's web editor: a local server over the store")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FW_WEB_PORT", PORT)))
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--code-stamp", action="store_true", help="print which code this is, and stop")
    a = ap.parse_args()
    if a.code_stamp:
        print(current.CODE)
        return 0
    try:
        store.cmd_migrate(None)
    except store.StoreError as e:
        store.die(str(e))
    if os.environ.get("FW_WEB_WATCH", "1") != "0":
        if current.page_stale():
            current.build_page()
        threading.Thread(target=current.keep_current, daemon=True).start()
    threading.Thread(target=visits.keep_flushing, daemon=True).start()
    store.json_later(JSON_LATER)
    atexit.register(store.flush_json)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # atexit's flush still runs
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"fw web: {url}", file=sys.stderr, flush=True)
    if not a.no_open:
        webbrowser.open(url)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
