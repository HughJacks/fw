"""fw_web — the core of fw's web editor (2026-11-17): a local server over the store.

    fw web                 start it (if it isn't running) and open the browser
    python3 fw_web.py [--port 8020] [--no-open]

The editor is a page (web/: ProseMirror, built into web/dist/); this is
everything else, and the only part that touches the store. It goes through
fw_store's own functions, so every rule the terminal editor keeps is kept
here too: a save is the same `commit` of a draft in fw's draft format
(marker lines, fw_draft), refused over a change made elsewhere (`base`),
tidied, validated. The data model stays apart from the editor: the page
sees JSON, never the store.

Standard library only (and loro, through fw_store). Listens on 127.0.0.1.

    GET  /                          the page
    GET  /api/home                  every pericope, a line each, in the recommendation's order
    POST /api/visit                 {pericope?, block?, flags?, ago?, flush?}: attention from the page, kept as
                                    visits (fw_block.attend) and written when they end (store.record_visits)
    GET  /api/exits/<id>[?meaning=1] where to go from a pericope (fw_search.exits), a line each
    GET  /api/search?q=&meaning=1   home's search (fw_search.Search's rows); with
                                    meaning=1, the search service asked too (fw_meaning) and mixed in
    GET  /api/pericope/<id>         a pericope: its header and its blocks, as a tree
    PUT  /api/pericope/<id>         {draft, title, base, final, also}: saved (store.commit), any block (a
                                    quote's target too); `also`: ids whose new base comes back (the editors
                                    around a quote written through, whose shown text changed)
    PUT  /api/lens/<quote id>       {text, base}: a masked quote's view written through (store.commit_view)
    POST /api/pericope              {title}: a new pericope, {id, base}
    GET  /api/quote?target=         a new quote of a block, as the page draws it
    POST /api/popout                {block}: a pericope of its own, quoted where it was (store.pop_out)
    POST /api/maskto                {quote, block}: the quote masked to just that block
    POST /api/picture               {url}, or a picture's bytes: a picture pericope (store.add_image_data)
    POST /api/act                   {do, …}: the Ctrl+/ menu's actions (detach, popout, showall, show, lock,
                                    link, unlink, kind, newkind, rename, paraphrase_it, paraphrase, delete), each a
                                    store function; its undo record
                                    comes back
    GET  /api/kinds[?members=1]     every kind, {id, name} (the kinds picker); with members, each kind's, and the
                                    pericopes of no kind, `unkinded` (the kinds view)
    GET  /api/clip                  what fw last clipped (the rich clipboard, .fw-clip.json, shared with the terminal)
    POST /api/clip                  {ids, cut, text}: blocks clipped (a cut one kept by the store while it's held)
    GET  /api/blocks?ids=           blocks as the page edits them, keeping their ids (pasted after a cut: moved)
    POST /api/restore               {record}: an action taken back (store.restore); its inverse comes back
    GET  /api/masking?quote=        what masking a quote works on: its target's draft, the mask, the lines
    POST /api/maskop                {draft, mask, op, a, b, i}: one key while masking, the mask back
    GET  /api/snapshot              every pericope as the expression engine reads it (snapshot_json)
    GET  /api/stamp                 when the store last changed (the page follows it)
    GET  /api/keys, PUT /api/keys   the user's key bindings for the web editor (web-keys.json beside the store)
    GET  /images/<file>             a picture
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw_meaning  # noqa: E402
import fw_store as store  # noqa: E402
from fw_search import NEW, Search, blocks_inside, exits, home_order  # noqa: E402

WEB = HERE / "web"
PORT = 8020


def code_stamp() -> str:
    """Which code this is: the fw_*.py beside it, by name, size and time (`fw web` starts the core again when the
    one running is older than the code)."""
    import hashlib
    files = sorted(HERE.glob("fw_*.py"))
    return hashlib.sha1("".join(f"{f.name}:{f.stat().st_size}:{f.stat().st_mtime_ns};" for f in files).encode()).hexdigest()[:12]


CODE = code_stamp()   # (as it was when this one started)


def page_stamp() -> str:
    """Which page is built (web/dist, by name, size and time): the page reloads itself when it changes."""
    import hashlib
    files = sorted((WEB / "dist").glob("*"))
    return hashlib.sha1("".join(f"{f.name}:{f.stat().st_size}:{f.stat().st_mtime_ns};" for f in files if f.is_file()).encode()).hexdigest()[:12]


def page_stale() -> bool:
    """The page's source (web/src, its build script and config) changed since it was last built."""
    built = WEB / "dist" / "app.js"
    if not built.exists():
        return True
    sources = [*(WEB / "src").glob("*"), WEB / "build.mjs", WEB / "tailwind.config.js", WEB / "index.html"]
    return max((f.stat().st_mtime for f in sources if f.exists()), default=0) > built.stat().st_mtime


def build_page() -> bool:
    """`npm run build`'s build (node build.mjs), with whichever node there is (on PATH, else fnm's). Whether it built."""
    import shutil
    import subprocess
    node = shutil.which("node")
    cmd = [node, "build.mjs"] if node else (["fnm", "exec", "--using=default", "node", "build.mjs"] if shutil.which("fnm") else None)
    if not cmd:
        return False
    return subprocess.run(cmd, cwd=WEB, capture_output=True, timeout=120).returncode == 0


ACTIVE = [0]   # requests being answered now (a restart waits for none); changed under ACTIVE_LOCK (threads)
ACTIVE_LOCK = threading.Lock()


def keys_path() -> Path:
    """The user's own key bindings for the web editor (#/keys): beside the store, not in it."""
    return store.DATA_PATH.with_name("web-keys.json")


def read_keys() -> dict:
    try:
        got = json.loads(keys_path().read_text(encoding="utf-8"))
        return {k: v for k, v in got.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def write_keys(keys: dict) -> None:
    tmp = keys_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(keys, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, keys_path())


VISITS = {"live": {}, "pending": {}}   # the visits under way and those waiting to be written (fw_block.attend), the
VISITS_LOCK = threading.Lock()         # page's attention told here (POST /api/visit); the core outlives the tab


def attention(blocks: dict, pericope: str | None, block: str | None, flags: str, at: float) -> None:
    """Attention from the page, as the terminal editor's visit_tick: on the pericope open (any key, opening it: "o");
    on the block the cursor's in, once it's stayed or been written in ("c", "w", "q" through a quote), carried up to
    its entry (fw_block.ancestors: not through quotes)."""
    with VISITS_LOCK:
        for ids, f in (([pericope], "o") if pericope else ([], ""),
                       ([block, *store.ancestors(blocks, block)], flags) if block and flags else ([], "")):
            ids = [i for i in ids if i in blocks]
            if ids:
                VISITS["live"], seen = store.attend(VISITS["live"], ids, f, at)
                VISITS["pending"] = store.note_visits(VISITS["pending"], seen)


def flush_visits(everything: bool = False) -> None:
    """The visits that have ended (no attention for VISIT_GAP), or all of them, written into the store
    (store.record_visits: not an edit); kept to try again if it refuses."""
    with VISITS_LOCK:
        now = store.clock()
        if not VISITS["pending"] or not (everything or store.ended(VISITS["live"], now) & VISITS["pending"].keys()):
            return
        try:
            store.record_visits(VISITS["pending"])
        except (store.StoreError, OSError):
            return
        VISITS["pending"] = {}
        VISITS["live"] = {i: x for i, x in VISITS["live"].items() if now - x[1] <= store.VISIT_GAP}


def keep_flushing() -> None:
    """Every half minute, the visits that have ended written (the tab may have gone)."""
    import time
    while True:
        time.sleep(30)
        flush_visits()


def keep_current() -> None:
    """Always the latest code (the user, 2026-11-18): every second, the page built again when its source changed,
    and this core started again, in place, when fw's code changed (once no request is being answered, so no save
    is cut off). The page sees both (/api/version) and reloads itself. Off in the tests ($FW_WEB_WATCH=0)."""
    import time
    while True:
        time.sleep(1)
        try:
            if page_stale():
                build_page()
            with ACTIVE_LOCK:
                idle = ACTIVE[0] == 0
            if code_stamp() != CODE and idle:
                print("fw web: fw's code changed; starting again", file=sys.stderr, flush=True)
                os.execv(sys.executable, [sys.executable, *sys.argv])
        except (OSError, ValueError):
            continue
ID_RE = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{4}$")
IMAGE_RE = re.compile(r"^[0-9a-f]+\.(png|jpg|jpeg|gif|webp)$")
MAX_DEPTH = store.MAX_DEPTH  # quotes inside quotes shown this deep, then a stand-in


# --- pure: the store as the page sees it -----------------------------------------

def blocks_of(library: dict) -> dict:
    return {i: e["block"] for i, e in library.items()}


def shown_text(text: str) -> str:
    """A masked view's text as the page shows it: each hidden stretch a …."""
    return text.replace(store.ELLIPSIS, "…").replace(store.CLOSE, "").replace(store.OPEN, "")


def items_json(library: dict, items: list, depth: int, path: tuple) -> list:
    """A quote's body (fw_block.quote_items' items) as the page draws it, read only."""
    out = []
    for item in items:
        match item:
            case ("text", text):
                out.append({"t": "text", "text": shown_text(text)})
            case ("image", iid):
                out.append({"t": "image", "file": store.image_of(library.get(iid, {}).get("block"))})
            case ("expr", eid):   # (the expr branch: its source; the page evaluates it)
                out.append({"t": "expr", "source": store.expr_of(library.get(eid, {}).get("block")) or ""})
            case ("quote", target, mask, show, inner):
                out.append(quote_json(library, None, target, mask, show, inner, depth + 1, path))
    return out


def editable(library: dict, target: str, mask, depth: int, path: tuple, locked: bool) -> bool:
    """Whether a quote of `target` can be written through here: unmasked
    (a masked one through the lens: not yet), not locked (nor inside a locked
    one: fw_block.locked_by's cascade), not a loop, not past MAX_DEPTH, and
    not a picture (nothing to write in)."""
    entry = library.get(target)
    return (entry is not None and mask is None and not locked and depth <= MAX_DEPTH and target not in path
            and not store.image_of(entry["block"]))


def tree_json(library: dict, ref: str, depth: int = 1, path: tuple = (), locked: bool = False) -> list:
    """What block `ref` holds, as the page edits it: its blocks (node_json);
    a block of text, its own text (`own`: saved as plain text, no marker);
    a picture, the picture."""
    blocks = blocks_of(library)
    b = blocks[ref]
    if store.text_of(b) is not None:   # (a pericope is never a paraphrase: para_json says none)
        return [{"t": "text", "id": ref, "own": True, "text": store.text_of(b), "links": links_json(library, b), "para": para_json(library, b)}]
    if store.image_of(b):
        return [{"t": "image", "id": None, "file": store.image_of(b)}]
    return [node_json(library, k, depth, path, locked) for k in store.children(b)]


def kept_json(library: dict, line: str, depth: int, path: tuple) -> dict | None:
    """A quote or picture line of a draft (one the lens keeps as it is, or masking shows as one unit) as the page
    draws it, read only: a quote with what it shows (in full, as anywhere else), or the picture."""
    if (q := store.QUOTE_RE.fullmatch(line)):
        qid, target = q.group(2), q.group(1)
        blocks = blocks_of(library)
        data = node_json(library, qid, depth, path) if qid in blocks else quote_json(library, None, target, None, [], {}, depth, path)
        for k in ("tree", "lens", "base"):   # (read only here: written in where it lives)
            data.pop(k, None)
        return data
    if (m := store.IMAGE_RE.fullmatch(line)):
        return {"t": "image", "file": store.image_of(blocks_of(library).get(m.group(1)))}
    return None


def lens_json(library: dict, target: str, mask: list, depth: int = 1, path: tuple = ()) -> list:
    """A masked quote's view, as the page writes through it (the lens: fw_lens.view, put back by commit_view):
    segments in order: a block's text (`marker`, its marker line as the view has it, kept exactly; `text`, its
    shown lines, each hidden stretch the view's ELLIPSIS: a hole the page won't let go), or a line kept as
    it is (`line`: a quote or picture inside, drawn read only)."""
    blocks = blocks_of(library)
    out = []
    for line in store.view(store.block_draft(blocks, target), mask).split("\n"):
        if (m := store.BLOCK_RE.fullmatch(line)):
            out.append({"t": "text", "id": m.group(1), "marker": line, "lines": []})
        elif (q := store.QUOTE_RE.fullmatch(line)) or store.IMAGE_RE.fullmatch(line):
            title = (library.get(q.group(1)) or {}).get("title", "missing block") if q else "picture"
            out.append({"t": "line", "line": line, "title": title, "data": kept_json(library, line, depth + 1, path + (target,))})
        else:
            if not out or out[-1]["t"] != "text":
                out.append({"t": "text", "id": None, "marker": None, "lines": []})
            out[-1]["lines"].append(line)
    for seg in out:
        if seg["t"] == "text":
            seg["empty"] = not seg["lines"]
            seg["text"] = "\n".join(seg.pop("lines"))
    return out


def quoted_expr(blocks: dict, target: str) -> str | None:
    """The one expression block a quote of `target` shows: `target` itself, or a pericope (or container) holding just
    it; else None. Pure."""
    b = blocks.get(target)
    if store.expr_of(b) is not None:
        return target
    kids = store.children(b) if b else []
    return kids[0] if len(kids) == 1 and store.expr_of(blocks.get(kids[0])) is not None else None


def quote_json(library: dict, qid: str | None, target: str, mask, show, inner, depth: int, path: tuple,
               locked: bool = False) -> dict:
    """A quote of `target` (its own block `qid`, if it's one of the pericope's), with what it shows; and,
    when it can be written through (`editable`), what its target holds (`tree`) and its `base`."""
    blocks = blocks_of(library)
    entry = library.get(target)
    locked = locked or bool(qid and store.quote_lock(blocks.get(qid)))
    q = {"t": "quote", "id": qid, "target": target, "title": entry["title"] if entry else "missing block",
         "home": store.home_of(blocks, target)[0] if entry else None,
         "masked": mask is not None, "show": list(show or []),
         "lock": bool(qid and store.quote_lock(blocks.get(qid))), "locked": locked,
         "picture": bool(entry and store.image_of(entry["block"])),
         # (what its top line can show of its source, its mini header: made, last update, words)
         "created": entry["block"].get("created") if entry else None,
         "updated": entry["block"].get("updated") if entry else None,
         "words": entry["block"].get("words", 0) if entry else 0}
    one = quoted_expr(blocks, target) if entry else None
    if one:   # (a quote of one expression is a call: the page evaluates it where the quote sits, TYPE.md)
        q["expr"] = {"id": one, "source": store.expr_of(blocks[one])}
    if entry is None:
        q["body"] = [{"t": "note", "text": f"missing block {target}"}]
    elif target in path:
        q["body"] = [{"t": "note", "text": f"↻ {entry['title']}"}]
    elif depth > MAX_DEPTH:
        q["body"] = [{"t": "note", "text": f"⋯ {entry['title']}"}]
    else:
        items = store.quote_items(blocks, target, mask, frozenset(), inner)
        q["body"] = items_json(library, items, depth, path + (target,)) or [{"t": "note", "text": "(empty)"}]
        if editable(library, target, mask, depth, path, locked):
            q["tree"] = tree_json(library, target, depth + 1, path + (target,), locked)
            q["base"] = store.content_hash(blocks, target)
        elif mask is not None and qid and editable(library, target, None, depth, path, locked):   # masked: through the lens
            q["lens"] = lens_json(library, target, mask, depth, path)
            q["hole"] = store.ELLIPSIS
            q["base"] = store.content_hash(blocks, target)
    return q


def node_json(library: dict, ref: str, depth: int = 1, path: tuple = (), locked: bool = False) -> dict:
    """One block of a pericope, as the page edits it: text, a container of
    blocks, a quote (with what it shows, and what it holds when it can be
    written through), or a picture. `path`: the blocks quoted on the way
    here (a loop is drawn, not followed); `locked`: inside a locked quote."""
    blocks = blocks_of(library)
    b = blocks[ref]
    if store.quoted(b):
        target, _ = store.quoted(b)
        _, _, mask, show, inner = store.seen_quote(blocks, ref, {})
        return quote_json(library, ref, target, mask, show, inner, depth, path, locked)
    if store.image_of(b):
        return {"t": "image", "id": ref, "file": store.image_of(b)}
    if store.expr_of(b) is not None:   # (the expr branch: its source; the page evaluates it)
        return {"t": "expr", "id": ref, "source": store.expr_of(b)}
    kids = store.children(b)
    if kids:
        return {"t": "container", "id": ref, "children": [node_json(library, k, depth, path, locked) for k in kids]}
    return {"t": "text", "id": ref, "text": store.own_text(blocks, ref), "links": links_json(library, b), "para": para_json(library, b)}


def para_json(library: dict, b: dict) -> dict | None:
    """What block `b` paraphrases, if it's a paraphrase: its id, title, where it lives, and its text (the dim
    guide an empty paraphrase shows, and Show its source)."""
    src = store.paraphrases(b)
    if not src:
        return None
    blocks = blocks_of(library)
    if src not in library:
        return {"id": src, "title": "(its source is gone)", "text": "", "home": None}
    return {"id": src, "title": library[src]["title"], "text": store.full_text(blocks, src)[:4000],
            "home": store.home_of(blocks, src)[0]}


def links_json(library: dict, b: dict) -> list:
    """A block of text's hyperlinks, as the page marks them: where, to what (and its title)."""
    return [{"to": l["to"], "at": l["at"], "title": library[l["to"]]["title"] if l["to"] in library else "gone"}
            for l in store.links(b)]


def masking_json(library: dict, qid: str) -> dict:
    """What masking quote `qid` works on (the terminal's masking mode): its target's whole draft, the mask as
    it's edited (fw_lens.edit_mask: all of it when unmasked), and the draft's lines as the page draws them,
    each with where it starts in the draft (marker lines left out: a block's lines carry its id)."""
    blocks = blocks_of(library)
    target, mask = store.quoted(blocks[qid])
    draft = store.block_draft(blocks, target)
    lines, pos, block = [], 0, None
    for line in draft.split("\n"):
        m = store.BLOCK_RE.fullmatch(line)
        if m:
            block = m.group(1)
        elif (q := store.QUOTE_RE.fullmatch(line)):
            lines.append({"t": "quote", "start": pos, "end": pos + len(line),
                          "title": library[q.group(1)]["title"] if q.group(1) in library else "missing block",
                          "data": kept_json(library, line, 2, (target,))})
        elif store.IMAGE_RE.fullmatch(line):
            lines.append({"t": "picture", "start": pos, "end": pos + len(line), "data": kept_json(library, line, 2, (target,))})
        else:
            lines.append({"t": "text", "start": pos, "text": line, "block": block})
        pos += len(line) + 1
    return {"quote": qid, "target": target, "title": library[target]["title"], "draft": draft,
            "mask": store.edit_mask(draft, mask), "lines": lines}


def mask_op(draft: str, mask: list, op: str, a: int = 0, b: int = 0, i: int = 0) -> list:
    """One key while masking, on the mask being edited (fw_lens's interval set), kept well formed:
    `[` on a selection a..b shows exactly it (wrap), `]` hides it (minus); `[` at a point a opens there
    (open_at), `]` closes (close_at); Backspace on bracket i takes it out (drop_anchor)."""
    n = len(draft)
    got = {"wrap": lambda: store.wrap(mask, a, b), "minus": lambda: store.minus(mask, a, b),
           "open": lambda: store.open_at(mask, a, n), "close": lambda: store.close_at(mask, a, n),
           "drop": lambda: store.drop_anchor(mask, i, n)}[op]()
    return store.tidy_edit(draft, got)


def clip_unit(blocks: dict, ref: str) -> dict:
    """Block `ref` as the rich clipboard keeps it (the terminal's units, fw_blocks: so either editor can paste
    it): a quote's content, a picture's file, a container's blocks, a block of text's text and links."""
    b = blocks[ref]
    if store.quoted(b):
        return {"id": ref, "quote": store.copy.deepcopy(b["content"]), "shown": store.shown_text(blocks, ref)}
    if store.image_of(b):
        return {"id": ref, "image": store.image_of(b)}
    if store.children(b):
        return {"id": ref, "blocks": [clip_unit(blocks, k) for k in store.children(b) if k in blocks]}
    return {"id": ref, "text": store.own_text(blocks, ref), "links": store.links(b)}


def maybes_json(library: dict, kid: str) -> list:
    """A kind's maybes (fw_block.maybes: the pericopes a model guesses might be one, likeliest first), each where it
    lives, to review from the kind."""
    blocks = blocks_of(library)
    return [{"block": b, "home": store.home_of(blocks, b)[0], "title": library[b]["title"], "p": round(p, 2)}
            for b, p in store.maybes(store.load_guesses(), library, kid) if b in library]


def unkinded_json(library: dict) -> list:
    """The pericopes of no kind (the kinds view's last group, the user, 2026-11-23: "a grouping of anything with no
    kind"): no yes of yours, no sure guess (a maybe isn't one); not a kind itself. Newest first, a line each as
    members_json's."""
    blocks = blocks_of(library)
    guesses = store.guessed(store.load_guesses(), library)
    none = [i for i, e in library.items() if e.get("entry") and store.kind_of(blocks.get(i)) is None
            and True not in store.merge_kinds(store.kinds_of(blocks.get(i)), guesses.get(i)).values()]
    return [{"key": b, "open": b, "title": library[b]["title"], "dim": False,
             "right": f"{b[4:6]}/{b[6:8]}  {library[b].get('words', 0)}w"} for b in sorted(none, reverse=True)]


def members_json(library: dict, kid: str) -> list:
    """A kind's members (fw_block.of_kind: your answers, newest first; then a model's sure guesses, GUESS_AT up,
    newest first; then its maybes, fw_block.maybes, likeliest first), a line each as home's list, each opening where it
    lives; a guess `dim` with its `p`, a maybe's `maybe` too, to answer from the list (the kinds view, and a kind's own
    page below what it says: worked out, never stored as quotes, the user, 2026-11-22)."""
    blocks = blocks_of(library)
    data = store.load_guesses()
    guesses = store.guessed(data, library)
    found = [b for b in reversed(store.of_kind(blocks, kid, guesses)) if b != kid and b in library]
    yours = [b for b in found if kid in store.kinds_of(blocks[b])]
    sure = [(b, guesses[b][kid]) for b in found if b not in yours]
    maybe = [(b, p) for b, p in store.maybes(data, library, kid) if b in library and b not in found]
    out = []
    for b, p, ask in [(b, None, False) for b in yours] + [(b, p, False) for b, p in sure] + [(b, p, True) for b, p in maybe]:
        home = store.home_of(blocks, b)[0]
        out.append({"key": b, "open": home, "title": library[b]["title"], "dim": p is not None,
                    **({"p": round(p, 2)} if p is not None else {}), **({"maybe": True} if ask else {}),
                    "right": f"{b[4:6]}/{b[6:8]}  {library[home].get('words', 0)}w"})
    return out


def kind_tokens(library: dict, ref: str) -> list:
    """The header's kinds line, as the terminal's (Editor.kind_chips): each answer (`yes`: true, false), then a
    model's guesses that count (store.guessed): a learned kind's applied ("applied"), any other a guess
    ("guess", its p)."""
    b = library[ref]["block"]
    out = [{"kind": k, "name": library[k]["title"], "mark": "yes" if yes else "no"}
           for k, yes in store.kinds_of(b).items() if store.kind_of(library.get(k, {}).get("block")) is not None]
    data = store.load_guesses()
    auto = store.learned(data)
    for k, p in store.guessed(data, library).get(ref, {}).items():
        out.append({"kind": k, "name": library[k]["title"], "p": round(p, 2),
                    "mark": "applied" if store.is_applied(library, ref, k, auto) else "guess"})
    return out


def backlink_rows(library: dict, found: list) -> list:
    """The backlinks as the list above the header shows them (the user, 2026-11-23: "a reverse of the go to", just off
    screen): oldest first, so the newest is nearest the header; a kind's members aren't here (they're below it). Each
    {key, open: the pericope it's in, at: the pointing block, title, kind, right: "MM/DD", words: the words around it
    (a link's, a paraphrase's own; a quote's, the block before it, else after)}."""
    blocks = blocks_of(library)
    up = {k: i for i, b in blocks.items() for k in store.children(b)}
    def near(i):
        kids = store.children(blocks.get(up.get(i), {})) or []
        n = kids.index(i) if i in kids else -1
        for k in ([kids[n - 1]] if n > 0 else []) + kids[n + 1:n + 2]:
            t = store.own_text(blocks, k).strip()
            if t and not store.quoted(blocks[k]):
                return t
        return ""
    out = []
    for x in found:
        if x["kind"] == "kind" or x["home"] not in library:
            continue
        by, text = x["by"], ""
        if x["kind"] == "link":
            own = store.own_text(blocks, by)
            spot = next((link["at"] for link in store.links(blocks[by]) if link["at"][0] == x["at"] - store.home_of(blocks, by)[1]), None)
            a, e = spot or (0, 0)
            text = ("…" if a > 40 else "") + own[max(0, a - 40):e + 40].strip() + ("…" if e + 40 < len(own) else "")
        elif x["kind"] == "paraphrase":
            text = store.text_of(blocks[by])
        else:
            text = near(by)
        when = x["created"] or blocks[x["home"]].get("created") or ""
        out.append({"key": f"{x['kind']}:{by}:{x['at']}", "open": x["home"], "at": by, "title": library[x["home"]]["title"],
                    "kind": x["kind"], "right": f"{when[5:7]}/{when[8:10]}" if when else "",
                    "words": " ".join(text.split())[:120]})
    return out


def pericope_json(library: dict, ref: str) -> dict:
    """A pericope (or any block) as the page opens it: its header and what it holds."""
    blocks = blocks_of(library)
    b = blocks[ref]
    found = store.backlinks(blocks, ref)
    return {"id": ref, "title": b.get("title"), "shown": library[ref]["title"],
            "type": store.type_label(b, blocks), "kind": store.kind_of(b) is not None,
            "created": b.get("created"), "updated": b.get("updated"), "words": b.get("words", 0),
            "visited": store.minute_iso(store.last_visit(b)) or None,   # (its last visit, as the terminal's "last visited")
            "kinds": store.kinds_text(blocks, b), "kindTokens": kind_tokens(library, ref),
            "maybes": maybes_json(library, ref) if store.kind_of(b) is not None else None,
            "members": members_json(library, ref) if store.kind_of(b) is not None else None,
            "backlinks": store.backlink_summary(found) if found else "",
            "backlinkRows": backlink_rows(library, found),
            "base": store.content_hash(blocks, ref), "children": tree_json(library, ref, 1, (ref,))}


def home_json(library: dict) -> list:
    """Home's list: every pericope, a line each, in the recommendation's order (fw_search.home_order: what's alive
    for you, fused with where to start). The garden's cards were taken out (the user, 2026-11-20: "keep just the
    simple list")."""
    blocks = blocks_of(library)
    refs = sorted((r for r, e in library.items() if e["entry"]), reverse=True)
    return [{"key": i, "title": library[i]["title"], "right": f"{i[4:6]}/{i[6:8]}  {library[i].get('words', 0)}w",
             "kind": store.kind_of(blocks[i]) is not None}
            for i in home_order(blocks, refs, int(store.clock() // 60))]


def exits_json(library: dict, here: str, meaning: bool = False) -> list:
    """Where to go from `here` (fw_search.exits), a line each as home's list, those filled from home's order marked
    `unrelated`; with `meaning`, the search service asked for
    the blocks nearest its text (its title and the start of what it says), none if it doesn't answer."""
    blocks = blocks_of(library)
    refs = [r for r, e in library.items() if e["entry"]]
    near = None
    if meaning and fw_meaning.URL not in ("", "off"):
        text = f"{library[here]['title']}\n{store.full_text(blocks, here)}"[:600]
        try:
            near = fw_meaning.fetch(fw_meaning.URL, text) if len(text.strip()) >= fw_meaning.MIN_CHARS else None
        except (OSError, ValueError):
            near = None
    related, filled = exits(blocks, refs, here, int(store.clock() // 60), near)
    return [{"key": i, "title": library[i]["title"], "right": f"{i[4:6]}/{i[6:8]}  {library[i].get('words', 0)}w",
             "kind": store.kind_of(blocks[i]) is not None, "unrelated": i in filled} for i in related + filled]


def search_json(library: dict, query: str, meaning: list | None = None) -> list:
    """Home's search, as the terminal's: fw_search.Search's rows (with the
    the search service's answer, `meaning`, mixed in when there is one)."""
    refs = sorted((r for r, e in library.items() if e["entry"]), reverse=True)
    p = Search(library, refs, pinned=[(NEW, lambda q: f"+ new pericope “{q}”" if q else "+ new pericope")],
               inside=blocks_inside(library, refs))
    p.query = query
    if meaning is not None:
        p.meaning = (query, meaning)
    blocks = blocks_of(library)
    rows = []
    for key, shown, right, *dim in p.rows():
        home = key if key == NEW or library[key]["entry"] else store.home_of(blocks, key)[0]
        go = key if key == NEW else p.source(key)
        orig = store.paraphrases(blocks.get(go))   # a paraphrase is never opened: its original is (the user, 2026-11-21)
        if orig in blocks and store.home_of(blocks, orig)[0]:
            home, go = store.home_of(blocks, orig)[0], orig
        rows.append({"key": "new" if key == NEW else key, "label": shown, "right": right, "dim": bool(dim and dim[0]),
                     "open": home, "at": None if go in (NEW, home) else go,
                     "source": None if key == NEW else p.source(key),          # what quoting this row quotes
                     "inside": key != NEW and key != home and not store.quoted(blocks.get(key))})  # a block inside a pericope
    return rows


# --- the server ----------------------------------------------------------------

def snap_node(blocks: dict, ref: str, seen: frozenset = frozenset()) -> dict:
    """Block `ref` as the expression engine reads it (the snapshot: fw's stored cases, TYPE.md's Case): text,
    a paraphrase, a quote, a picture (a quote of its pericope), an expression (its source), or blocks (a kind's
    description too); one gone, or met again inside itself, as nothing."""
    b = blocks.get(ref)
    if b is None or ref in seen:
        return {"id": ref, "t": "unknown"}
    if store.quoted(b):
        return {"id": ref, "t": "quote", "target": store.quoted(b)[0]}
    if store.paraphrases(b):
        return {"id": ref, "t": "paraphrase", "target": store.paraphrases(b), "text": store.text_of(b) or ""}
    if store.text_of(b) is not None:   # (its links too: a computed text keeps them, TYPE.md's Inline)
        return {"id": ref, "t": "text", "text": store.text_of(b), "links": [{"to": l["to"], "at": list(l["at"])} for l in store.links(b)]}
    if store.image_of(b):
        return {"id": ref, "t": "picture", "target": ref}
    if store.expr_of(b) is not None:
        return {"id": ref, "t": "expr", "source": store.expr_of(b)}
    return {"id": ref, "t": "blocks", "children": [snap_node(blocks, k, seen | {ref}) for k in store.children(b)]}


def snapshot_json(library: dict) -> dict:
    """The store as the page hands it to the expression engine (hazelRun's snapshot): every pericope, its title, its
    kinds (yes answers), its facts (created, updated, how many visits, the pericopes pointing at it: quotes, links,
    paraphrases, oldest first, as the backlinks above its header) and its body as stored. Pure. The page puts the open
    pericope's own, live, over it."""
    blocks = blocks_of(library)
    up = {k: i for i, b in blocks.items() for k in store.children(b)}
    def home(i):
        seen = set()
        while i in up and i not in seen:
            seen.add(i)
            i = up[i]
        return i if i in library else None
    pointing = {}   # target -> [(created, the pericope pointing)]
    for i, b in blocks.items():
        q = store.quoted(b)
        targets = ([q[0]] if q else []) + [link["to"] for link in store.links(b)] + ([store.paraphrases(b)] if store.paraphrases(b) else []) + store.expr_refs(b)
        h = home(i) if targets else None
        for t in targets if h else []:
            pointing.setdefault(t, []).append((b.get("created") or "", h))
    def backs(i):
        out = []
        for _, h in sorted(pointing.get(i, [])):
            if h != i and h not in out:
                out.append(h)
        return out
    return {"pericopes": [{"id": i, "title": e["title"] or "",
                           "kinds": [k for k, yes in store.kinds_of(e["block"]).items() if yes],
                           "created": e["block"].get("created") or "", "updated": e["block"].get("updated") or "",
                           "visits": (e["block"].get("visits") or {}).get("total", 0),
                           "backlinks": backs(i),
                           "body": snap_node(blocks, i)}
                          for i, e in library.items() if e["entry"]]}


def library() -> dict:
    return store.build_library(store.load_data())


def stamp() -> int:
    try:
        return store.DATA_PATH.stat().st_mtime_ns
    except OSError:
        return 0


def refusal(method: str, path: str, host: str | None, origin: str | None, ctype: str | None, port: int) -> str | None:
    """Why a request isn't the page's own (None: it is). Only this machine's page may use the core (the audit of
    2026-11-19): the Host must be 127.0.0.1:<port> or localhost:<port> (a rebound DNS name can't read the store), any
    Origin must be that too (no other site can call the API: a browser always sends one across sites), and what
    changes something (PUT, POST) must say its body is JSON (a plain-text POST, which needs no preflight, is refused;
    a dropped picture's bytes, POST /api/picture, come as image/*). Pure."""
    ours = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if (host or "").strip().lower() not in ours:
        return "not this machine's page (Host)"
    if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in ours}:
        return "not this machine's page (Origin)"
    if method in ("PUT", "POST"):
        kind = (ctype or "").split(";")[0].strip().lower()
        if kind != "application/json" and not (path == "/api/picture" and kind.startswith("image/")):
            return "expected Content-Type: application/json"
    return None


class Handler(BaseHTTPRequestHandler):
    def refused(self, method: str) -> bool:
        """Answered 403 when the request isn't the page's own (refusal)."""
        why = refusal(method, urlparse(self.path).path, self.headers.get("Host"), self.headers.get("Origin"),
                      self.headers.get("Content-Type"), self.server.server_address[1])
        if why:
            self.send(403, {"error": why})
        return bool(why)

    def do_GET(self):
        if self.refused("GET"):
            return
        url = urlparse(self.path)
        ask = parse_qs(url.query)
        path = url.path
        try:
            if path == "/" or path == "/index.html":
                return self.file(WEB / "index.html")
            if path.startswith("/dist/"):
                return self.file(WEB / "dist" / Path(path[len("/dist/"):]).name)
            if path.startswith("/images/"):
                name = path[len("/images/"):]
                return self.file(store.IMAGES_PATH / name) if IMAGE_RE.match(name) else self.send(404, {"error": "no such picture"})
            if path == "/api/stamp":
                return self.send(200, {"stamp": stamp()})
            if path == "/api/keys":   # the user's key bindings (#/keys), over the page's defaults
                return self.send(200, {"keys": read_keys()})
            if path == "/api/version":   # the code this core started with, and the page built now (the page reloads on a change)
                return self.send(200, {"code": CODE, "page": page_stamp(), "store": str(store.DATA_PATH)})
            if path == "/api/home":
                lib = library()
                return self.send(200, {"count": sum(1 for e in lib.values() if e["entry"]), "rows": home_json(lib)})
            if path == "/api/search":
                q = (ask.get("q") or [""])[0]
                meaning = None
                if (ask.get("meaning") or ["0"])[0] == "1" and fw_meaning.URL not in ("", "off") \
                        and len(q.strip()) >= fw_meaning.MIN_CHARS:
                    try:
                        meaning = fw_meaning.fetch(fw_meaning.URL, q)
                    except (OSError, ValueError):
                        meaning = None
                return self.send(200, {"query": q, "rows": search_json(library(), q, meaning), "meaning": meaning is not None})
            ex = re.fullmatch(r"/api/exits/([^/]+)", path)
            if ex and ID_RE.match(ex.group(1)):   # where to go from a pericope (fw_search.exits); meaning=1: the search service asked too
                lib = library()
                if not (lib.get(ex.group(1)) or {}).get("entry"):
                    return self.send(404, {"error": "no such pericope"})
                return self.send(200, {"rows": exits_json(lib, ex.group(1), (ask.get("meaning") or ["0"])[0] == "1")})
            if path == "/api/masking":   # what masking a quote works on (masking_json)
                qid = (ask.get("quote") or [""])[0]
                lib = library()
                if not store.quoted((lib.get(qid) or {}).get("block")):
                    return self.send(404, {"error": "no such quote"})
                return self.send(200, masking_json(lib, qid))
            if path == "/api/clip":   # what fw last clipped (the rich clipboard, shared with the terminal), or {}
                return self.send(200, store.load_clip() or {})
            if path == "/api/blocks":   # ?ids=a,b: blocks as the page edits them, keeping their ids (a cut, pasted: moved)
                lib = library()
                ids = [i for i in (ask.get("ids") or [""])[0].split(",") if i in lib]
                return self.send(200, {"blocks": [node_json(lib, i) for i in ids]})
            if path == "/api/snapshot":   # the store as the expression engine reads it (snapshot_json)
                return self.send(200, snapshot_json(library()))
            if path == "/api/kinds":   # every kind: {id, name}, oldest first (the kinds picker)
                lib = library()
                if (ask.get("members") or ["0"])[0] == "1":   # (the kinds view: each kind's members too)
                    return self.send(200, {"kinds": [{"id": k, "name": lib[k]["title"], "members": members_json(lib, k)}
                                                     for k in store.kind_ids(lib)], "unkinded": unkinded_json(lib)})
                return self.send(200, {"kinds": [{"id": k, "name": lib[k]["title"]} for k in store.kind_ids(lib)]})
            if path == "/api/quote":   # a new quote of `target`, as the page draws it (what it shows, what it holds)
                target = (ask.get("target") or [""])[0]
                lib = library()
                if target not in lib:
                    return self.send(404, {"error": "no such block"})
                # where it's going (`into`: the block it'll be in and what holds it; `depth`: quotes around it there).
                # Never refused (the user, 2026-11-19): the data model allows any quote, however deep what it quotes
                # goes, or if it comes back round to here; the drawing decides what to show (⋯ past the depth, ↻ at a
                # cycle). Its first drawing starts from here, so it stops where it would show itself even before it's saved
                into, depth = (ask.get("into") or [""])[0], int((ask.get("depth") or ["0"])[0] or 0)
                blocks = blocks_of(lib)
                here = tuple(i for i in into.split(",") if i in blocks)
                return self.send(200, quote_json(lib, None, target, None, [], {}, depth + 1, here))
            m = re.fullmatch(r"/api/pericope/([^/]+)", path)
            if m and ID_RE.match(m.group(1)):
                lib = library()
                if m.group(1) not in lib:
                    return self.send(404, {"error": "no such pericope"})
                return self.send(200, pericope_json(lib, m.group(1)))
            return self.send(404, {"error": "not found"})
        except (store.StoreError, OSError, ValueError) as e:
            return self.send(500, {"error": str(e)})

    def do_PUT(self):
        if self.refused("PUT"):
            return
        if urlparse(self.path).path == "/api/keys":   # {keys}: the user's key bindings, kept
            try:
                keys = self.body().get("keys") or {}
                write_keys({k: v for k, v in keys.items() if isinstance(k, str) and isinstance(v, str)})
                return self.send(200, {"keys": read_keys()})
            except (OSError, ValueError) as e:
                return self.send(500, {"error": str(e)})
        lens = re.fullmatch(r"/api/lens/([^/]+)", urlparse(self.path).path)
        if lens and ID_RE.match(lens.group(1)):   # {text, base}: a masked quote's view, written through (store.commit_view)
            try:
                body = self.body()
                hashes, _ = store.commit_view(lens.group(1), body.get("text") or "", None, base=body.get("base"))
                return self.send(200, {"bases": hashes})
            except store.StoreError as e:
                return self.send(409, {"error": str(e)})
            except (OSError, ValueError) as e:
                return self.send(500, {"error": str(e)})
        m = re.fullmatch(r"/api/pericope/([^/]+)", urlparse(self.path).path)
        if not (m and ID_RE.match(m.group(1))):
            return self.send(404, {"error": "not found"})
        try:
            body = self.body()
            fields = [{"key": "title", "value": body.get("title") or "", "editable": True}] if "title" in body else []
            notes, base, _, _ = store.commit(m.group(1), body.get("draft"), fields, final=bool(body.get("final")),
                                             base=body.get("base"))
            blocks = blocks_of(library())
            also = {i: store.content_hash(blocks, i) for i in body.get("also") or [] if i in blocks}
            return self.send(200, {"base": base, "notes": notes, "gone": m.group(1) not in blocks, "bases": also})
        except store.StoreError as e:
            return self.send(409, {"error": str(e)})
        except (OSError, ValueError) as e:
            return self.send(500, {"error": str(e)})

    def do_POST(self):
        if self.refused("POST"):
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/visit":   # {pericope?, block?, flags?, ago?, flush?}: attention from the page (attention)
                body = self.body()
                ago = body.get("ago") or 0
                at = store.clock() - (ago if isinstance(ago, (int, float)) and 0 <= ago <= store.VISIT_GAP else 0)
                flags = "".join(f for f in "cwq" if f in str(body.get("flags") or ""))
                lib = library()
                attention(blocks_of(lib), body.get("pericope") if (lib.get(body.get("pericope")) or {}).get("entry") else None,
                          body.get("block"), flags, at)
                flush_visits(everything=bool(body.get("flush")))
                return self.send(200, {})
            if path == "/api/pericope":   # a new pericope ({title})
                title = (self.body().get("title") or "").strip() or None
                def make(data, blocks):
                    return store.add_block(data, blocks, store.new_id(blocks), [], title=title, entry=True)["id"]
                ref = store.transact(store.editing(make), tidy=False)   # (its base too: home's waiting pericope saves into it at once)
                return self.send(200, {"id": ref, "base": store.content_hash(blocks_of(library()), ref)})
            if path == "/api/popout":   # {block}: a pericope of its own, quoted where it was (store.pop_out)
                ref = self.body().get("block")
                entry, _, _ = store.pop_out(ref)
                return self.send(200, {"id": entry})
            if path == "/api/act":   # the Ctrl+/ menu's actions, each a store function; its undo record comes back
                body = self.body()
                do, q = body.get("do"), body.get("quote")
                if do == "detach":            # Turn into text
                    _, _, record = store.detach(q)
                    return self.send(200, {"record": record})
                if do == "popout":            # Turn into a quote (and open it)
                    entry, _, record = store.pop_out(body.get("block"))
                    return self.send(200, {"id": entry, "record": record})
                if do == "setmask":           # masking done: the mask, anchors into `draft` (moved onto the stored text)
                    _, record = store.set_quote_mask(q, body.get("draft"), body.get("mask"))
                    return self.send(200, {"record": record})
                if do == "showall":           # Remove mask
                    _, record = store.set_quote_mask(q, None, None, inner=True)
                    return self.send(200, {"record": record})
                if do == "show":              # its top line: what it shows of its source
                    _, record = store.set_quote_show(q, list(body.get("show") or []))
                    return self.send(200, {"record": record})
                if do == "lock":              # Lock / Unlock writing through
                    _, record = store.set_quote_lock(q, bool(body.get("on")))
                    return self.send(200, {"record": record})
                if do == "link":              # Link to a pericope: a span of a block of text (to a new one, titled)
                    to, record = store.link_text(body.get("block"), body.get("text") or "", body.get("at"),
                                                 body.get("to"), body.get("title"))
                    return self.send(200, {"to": to, "title": library()[to]["title"], "record": record})
                if do == "unlink":            # Remove link (the text stays)
                    record = store.unlink_text(body.get("block"), body.get("to"), body.get("at"))
                    return self.send(200, {"record": record})
                if do == "kind":              # an answer: block is (true) or isn't (false) a kind, or none (null); a new kind by `name`
                    kid, record = store.set_kind(body.get("block"), body.get("kind"), body.get("answer"), body.get("name") or "")
                    return self.send(200, {"kind": kid, "record": record})
                if do == "newkind":           # a kind called `name`, made (the kinds view's + new kind); one there already: it
                    kid, record = store.new_kind(body.get("name") or "")
                    return self.send(200, {"kind": kid, "record": record})
                if do == "rename":            # a kind's name (its title): refused empty, or another kind's
                    record = store.rename_kind(body.get("kind"), body.get("name") or "")
                    return self.send(200, {"record": record})
                if do == "paraphrase_it":     # Paraphrase it: your words in its place (paraphrase_it)
                    pid, record = store.paraphrase_it(body.get("block"))
                    return self.send(200, {"id": pid, "record": record})
                if do == "paraphrase":        # Paraphrases… (`source`) / Not a paraphrase (no source)
                    record = store.set_paraphrase(body.get("block"), body.get("source"))
                    return self.send(200, {"record": record})
                if do == "delete":            # Delete this pericope (quotes of it elsewhere keep its last text)
                    return self.send(200, {"quotes": store.delete_entry(body.get("pericope"))})
                return self.send(404, {"error": f"no action {do!r}"})
            if path == "/api/clip":   # {ids, cut, text}: blocks clipped (save_clip: a cut one kept while it's held)
                body = self.body()
                blocks = blocks_of(library())
                ids = [i for i in body.get("ids") or [] if i in blocks]
                store.save_clip({"text": body.get("text") or "", "blocks": [clip_unit(blocks, i) for i in ids],
                                 **({"cut": True} if body.get("cut") else {})} if ids else None)
                return self.send(200, {"ok": True})
            if path == "/api/maskop":   # {draft, mask, op, a, b, i}: one key while masking (mask_op), the mask back
                body = self.body()
                return self.send(200, {"mask": mask_op(body["draft"], body["mask"], body["op"], int(body.get("a") or 0),
                                                       int(body.get("b") or 0), int(body.get("i") or 0))})
            if path == "/api/restore":   # {record}: an action taken back (store.restore); its inverse comes back
                return self.send(200, {"record": store.restore(self.body().get("record") or {"blocks": {}})})
            if path == "/api/maskto":   # {quote, block}: the quote masked to just that block (store.mask_quote_to)
                body = self.body()
                store.mask_quote_to(body.get("quote"), body.get("block"))
                lib = library()
                b = blocks_of(lib)
                return self.send(200, node_json(lib, body.get("quote")) if body.get("quote") in b else {})
            if path == "/api/picture":   # a picture pericope: {url} downloaded, or the picture's own bytes (dropped)
                if (self.headers.get("Content-Type") or "").startswith("image/"):
                    n = int(self.headers.get("Content-Length") or 0)
                    name = store.add_image_data(self.rfile.read(n), self.headers.get("X-Name") or "a dropped picture")
                else:
                    url = (self.body().get("url") or "").strip()
                    name = store.add_image_data(store.fetch_image(url), url)
                def make(data, blocks):
                    return store.add_block(data, blocks, store.new_id(blocks), {"image": name}, entry=True)["id"]
                ref = store.transact(store.editing(make), tidy=False)   # (its base too: home's waiting pericope saves into it at once)
                return self.send(200, {"id": ref, "base": store.content_hash(blocks_of(library()), ref)})
            return self.send(404, {"error": "not found"})
        except store.StoreError as e:
            return self.send(409, {"error": str(e)})
        except (OSError, ValueError) as e:
            return self.send(500, {"error": str(e)})

    # --- plumbing
    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        got = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        if not isinstance(got, dict):
            raise ValueError("expected a JSON object")
        return got

    def send(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def file(self, path: Path):
        try:
            data = path.read_bytes()
        except OSError:
            return self.send(404, {"error": "not found"})
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if path.suffix in (".html", ".js", ".css") else "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # (quiet)
        pass

    def handle(self):
        with ACTIVE_LOCK:
            ACTIVE[0] += 1
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):   # (the page went away mid-answer: nothing to tell it)
            pass
        finally:
            with ACTIVE_LOCK:
                ACTIVE[0] -= 1


def serve(port: int = PORT) -> ThreadingHTTPServer:
    """The server on 127.0.0.1:`port` (0: any free one), running in a thread."""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser(description="fw's web editor: a local server over the store")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FW_WEB_PORT", PORT)))
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--code-stamp", action="store_true", help="print which code this is, and stop (fw web compares)")
    a = ap.parse_args()
    if a.code_stamp:
        print(CODE)
        return 0
    try:
        store.cmd_migrate(None)  # (as fw does on every run: the store checked and brought up to date)
    except store.StoreError as e:
        store.die(str(e))
    if os.environ.get("FW_WEB_WATCH", "1") != "0":
        if page_stale():
            build_page()
        threading.Thread(target=keep_current, daemon=True).start()
    threading.Thread(target=keep_flushing, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"fw web: {url}", file=sys.stderr, flush=True)
    if not a.no_open:
        webbrowser.open(url)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
