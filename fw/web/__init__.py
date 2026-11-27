"""fw.web: the core of fw's web editor, a local server over the store (`python -m fw.web --port P [--no-open]`).

The page (web/, built into web/dist/) sees JSON, never the store; every write goes through fw.store's own functions.
Standard library only. Listens on 127.0.0.1.

    common    the library, ids, a list row's right column
    views     a pericope as the page edits it: blocks, quotes, lenses, header
    lists     home, exits, search, kinds' members
    snapshot  the store as the expression engine reads it
    live      the store's stamp, what changed block by block, the /api/live stream
    visits    attention from the page, written as visits
    current   code and page stamps, rebuilding the page, re-exec on new code
    routes    the API: a table of (method, path) -> handler
    server    the HTTP handler, the refusal of other origins
"""

from fw.web.common import MAX_DEPTH  # noqa: E402,F401
from fw.web.lists import home_json, search_json  # noqa: E402,F401
from fw.web.server import refusal, serve  # noqa: E402,F401
