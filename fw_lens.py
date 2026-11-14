"""fw_lens — masked quotes as a lens: pure functions over a draft and a mask."""

from __future__ import annotations

import re

from fw_draft import BLOCK_RE, is_atom

# --- masked quotes: a lens ---------------------------------------------------
# A Quote's mask is anchors into its target's draft (block_draft), in pairs
# like brackets: [open, close, open, close, …]. What's inside a pair shows;
# the rest is hidden, one ELLIPSIS per hidden stretch (and a line break after
# it, when the stretch spans one before more shown text: what's shown keeps
# its lines and blocks apart). `view` gets the shown
# text from the target, `put` puts an edited view back, keeping every hidden
# stretch exactly as it was. Anchors follow edits made anywhere else
# (`rebase`), and ranges grow: text typed at an anchor joins what's shown.

ELLIPSIS = ""                 # a hidden stretch, in a view


CLOSE, OPEN = "", ""    # the ends of the one hidden stretch laid open


MARKS = (ELLIPSIS, CLOSE, OPEN)


def pieces(draft: str, mask: list) -> tuple[list, list]:
    """The draft cut at the anchors: hidden pieces H0…Hn around shown ones S1…Sn.
    A block any of whose text shows keeps its marker line (`kept_apart`), so
    hidden text never runs two blocks together."""
    cuts = [0, *kept_apart(draft, mask), len(draft)]
    parts = [draft[a:b] for a, b in zip(cuts, cuts[1:])]
    return parts[0::2], parts[1::2]


def kept_apart(draft: str, mask: list) -> list:
    """`mask` with the marker line of every block it shows any text of shown
    too (the line breaks either side of it with it)."""
    spans, extra, pos, lines = [[a, b] for a, b in zip(mask[0::2], mask[1::2]) if a < b], [], 0, draft.split("\n")
    for n, line in enumerate(lines):
        end = pos + len(line)
        if BLOCK_RE.fullmatch(line):
            text_end = nxt = end + 1  # its text: the lines up to the next marker or quote line
            for later in lines[n + 1:]:
                if BLOCK_RE.fullmatch(later) or is_atom(later):
                    break
                text_end, nxt = nxt + len(later), nxt + len(later) + 1
            if any(a < text_end and b > end + 1 for a, b in spans) and \
                    not any(a <= max(pos - 1, 0) and b >= min(end + 1, len(draft)) for a, b in spans):
                extra.append([max(pos - 1, 0), min(end + 1, len(draft))])
        pos = end + 1
    if not extra:
        return mask
    merged = []
    for a, b in sorted(spans + extra):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [x for span in merged for x in span]


def has_text(piece: str) -> bool:
    """Whether a piece holds anything to read (not only block markers)."""
    return bool(re.sub(r"\{\{block[^}]*\}\}", "", piece).strip("\n"))


def breaks(piece: str) -> bool:
    """Whether a hidden piece spans a line break in its text (block markers aside)."""
    return "\n" in re.sub(r"\{\{block[^}]*\}\}\n?", "", piece)


def mark(hidden: list, k: int, shown: list) -> str:
    """How hidden piece k is drawn in a view: …, with its line break if it has
    one and shown text follows."""
    return ELLIPSIS + ("\n" if k < len(shown) and breaks(hidden[k]) else "")


def past_mark(rest: str, hidden: list, k: int, shown: list) -> str:
    """The view after hidden piece k's …: its line break taken out (text typed
    on the …'s line, after it, joins the shown text that follows)."""
    if mark(hidden, k, shown) == ELLIPSIS:
        return rest
    j = rest.find("\n")
    return rest if j < 0 else rest[:j] + rest[j + 1:]


def snap(draft: str, pos: int, opening: bool) -> int:
    """Keep an anchor in text, out of marker and quote lines: an opening one
    moves to the start of the next text line, a closing one to the end of the
    one before. Except at the very ends: a span can start before a quote the
    draft starts with, and end after one it ends with (or it could never show
    it)."""
    pos = min(max(pos, 0), len(draft))
    start = draft.rfind("\n", 0, pos) + 1
    end = draft.find("\n", pos)
    end = len(draft) if end < 0 else end
    if not (BLOCK_RE.fullmatch(draft[start:end]) or is_atom(draft[start:end])):
        return pos
    if is_atom(draft[start:end]) and (start == 0 if opening else end == len(draft)):
        return 0 if opening else len(draft)
    if opening:
        return snap(draft, end + 1, True) if end < len(draft) else len(draft)
    return snap(draft, start - 1, False) if start > 0 else 0


def normalize(draft: str, mask: list | None) -> list | None:
    """A well-formed mask: anchors in text and in order; ranges with nothing
    to read dropped, and ranges with nothing to read between them merged.
    None when it shows everything; [] when it shows nothing."""
    if mask is None or len(mask) % 2:
        return None
    m = []
    for n, pos in enumerate(mask):
        pos = snap(draft, int(pos), n % 2 == 0)
        m.append(max(pos, m[-1]) if m else pos)
    merged = []
    for a, b in zip(m[0::2], m[1::2]):
        if not has_text(draft[a:b]):
            continue
        if merged and not has_text(draft[merged[-1][1]:a]):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    if len(merged) == 1 and not has_text(draft[:merged[0][0]]) and not has_text(draft[merged[0][1]:]):
        return None
    return [x for pair in merged for x in pair]


def holes(draft: str, mask: list) -> list:
    """The hidden pieces that show, as an ellipsis each, in order."""
    return [k for k, h in enumerate(pieces(draft, mask)[0]) if has_text(h)]


def view(draft: str, mask: list | None, opened: int | None = None) -> str:
    """The lens's get: the shown text, an ELLIPSIS for each hidden stretch;
    the `opened` one laid open instead: CLOSE, its text, OPEN."""
    if mask is None:
        return draft
    hidden, shown = pieces(draft, mask)
    out = []
    for k, h in enumerate(hidden):
        if k == opened:
            out.append((CLOSE if k > 0 else "") + h + (OPEN if k < len(shown) else ""))
        else:
            out.append(mark(hidden, k, shown) if has_text(h) else h)  # only markers: nothing to hide
        if k < len(shown):
            out.append(shown[k])
    return "".join(out)


def put(draft: str, mask: list, text: str, opened: int | None = None) -> tuple[str, list]:
    """The lens's put: an edited view back into the draft. Hidden stretches
    come back exactly as they were (the opened one as it now reads), shown
    text as edited. Returns (new draft, new mask)."""
    hidden, shown = pieces(draft, mask)
    out, new, rest = "", [], text
    for k, h in enumerate(hidden):
        drawn = k == opened or has_text(h)
        if k > 0:  # the shown piece before this hole ends at its mark
            if drawn:
                i = rest.index(CLOSE if k == opened else ELLIPSIS)
                out, rest = out + rest[:i], rest[i + 1:]
                if k != opened:
                    rest = past_mark(rest, hidden, k, shown)
            else:  # only the last hole goes undrawn: the shown text runs to the end
                out, rest = out + rest, ""
            new.append(len(out))
        if k == opened:
            if k < len(shown):
                i = rest.index(OPEN)
                out, rest = out + rest[:i], rest[i + 1:]
            else:
                out, rest = out + rest, ""
        elif drawn:
            if k == 0:  # the view starts with this hole's mark; text typed before it shows, as a block of its own
                i = rest.index(ELLIPSIS)
                if rest[:i]:
                    out = rest[:i] + "\n"
                    new += [0, i]
                rest = past_mark(rest[i + 1:], hidden, k, shown)
            out += h
        if k < len(shown):
            new.append(len(out))
    if rest:  # typed after the last hole's mark: shows, at the end
        sep = "\n" if out and (out.endswith("\n") is False and line_marked(out)) else ""
        new += [len(out) + len(sep), len(out) + len(sep) + len(rest)]
        out += sep + rest
    return out, tighten(out, new)


MARKER_AT = re.compile(r"\n?\{\{block[^}]*\}\}(\n|$)")


def tighten(draft: str, mask: list) -> list:
    """`mask` without the marker lines kept_apart showed: each span from its
    first text to its last (one that was only markers goes)."""
    out = []
    for a0, b0 in zip(mask[0::2], mask[1::2]):
        a, b = a0, b0
        while a < b and (m := MARKER_AT.match(draft, a)) and m.end() <= b:
            a = m.end()
        while a < b and (m := next((m for m in MARKER_AT.finditer(draft, a, b) if m.end() == b), None)):
            b = m.start()
        if a < b or a0 == b0:
            out += [a, b]
    return out


def line_marked(draft: str) -> bool:
    """Whether the draft's last line is a marker or quote line (text can't follow on it)."""
    last = draft[draft.rfind("\n") + 1:]
    return bool(BLOCK_RE.fullmatch(last) or is_atom(last))


# --- editing a mask: an interval set of what's shown ---------------------------
# While a mask is edited, the target's whole text is in the editor with every
# anchor drawn in as a bracket: OPEN where a shown span starts, CLOSE where it
# ends. Each key is a set operation on the spans, so the mask stays well
# formed as you go: a lone bracket's partner is assumed at the edge of the
# stretch it's in (like Hazel's holes). Spans that only touch stay apart
# while editing (drawn ›‹, so a span opened in a gap can still be closed
# within it); `normalize` joins them when the editing is done.

def spans_of(mask: list) -> list:
    return [[a, b] for a, b in zip(mask[0::2], mask[1::2])]


def intersect(a: list | None, b: list | None) -> list | None:
    """What two masks of the same draft both show: a lens seen through
    another, which can only hide more. None shows everything."""
    if a is None or b is None:
        return b if a is None else a
    out = []
    for x0, x1 in spans_of(a):
        for y0, y1 in spans_of(b):
            lo, hi = max(x0, y0), min(x1, y1)
            if lo < hi:
                out += [lo, hi]
    return out


def union(mask: list, a: int, b: int) -> list:
    """Also show a..b (spans that overlap join; ones that only touch stay apart)."""
    merged = []
    for o, c in sorted(spans_of(mask) + [[a, b]]):
        if merged and o < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], c)
        else:
            merged.append([o, c])
    return [x for span in merged for x in span]


def minus(mask: list, a: int, b: int) -> list:
    """Hide a..b."""
    out = []
    for o, c in spans_of(mask):
        if c <= a or o >= b:
            out += [o, c]
            continue
        if o < a:
            out += [o, a]
        if c > b:
            out += [b, c]
    return out


def wrap(mask: list, a: int, b: int) -> list:
    """`[` on a selection: show exactly a..b. Inside a shown span, that span
    narrows to it; in hidden text, it's shown as a span of its own."""
    for o, c in spans_of(mask):
        if o <= a and b <= c:
            return minus(minus(mask, o, a), b, c)
    return union(mask, a, b)


def open_at(mask: list, p: int, length: int) -> list:
    """`[` at p: hidden before p, shown after. In hidden text that shows from
    p to where the hiding ends (the next span, or the end); in shown text it
    hides from the span's start up to p."""
    for o, c in spans_of(mask):
        if o <= p < c:
            return minus(mask, o, p)
    return union(mask, p, min([o for o, _ in spans_of(mask) if o > p], default=length))


def close_at(mask: list, p: int, length: int) -> list:
    """`]` at p: shown before p, hidden after. In shown text that hides from
    p to the span's end; in hidden text it shows from where the hiding began
    (the span before, or the start) up to p."""
    for o, c in spans_of(mask):
        if o < p <= c:
            return minus(mask, p, c)
    return union(mask, max([c for _, c in spans_of(mask) if c < p], default=0), p)


def drop_anchor(mask: list, i: int, length: int) -> list:
    """Take out anchor i: the spans on either side join over the gap it bounded
    (the first opener's span then starts at the start, the last closer's
    runs to the end)."""
    m = list(mask)
    if i % 2 == 0:
        return m[:i - 1] + m[i + 1:] if i > 0 else [0] + m[1:]
    return m[:i] + m[i + 2:] if i + 1 < len(m) else m[:i] + [length]


def tidy_edit(draft: str, mask: list) -> list:
    """A mask kept well formed while it's edited: anchors in text and in
    order, empty spans dropped, overlapping ones joined (touching ones kept)."""
    m = []
    for n, pos in enumerate(mask):
        pos = snap(draft, pos, n % 2 == 0)
        m.append(max(pos, m[-1]) if m else pos)
    out = []
    for o, c in spans_of(m):
        if c <= o:
            continue
        if out and o < out[-1]:
            out[-1] = max(out[-1], c)
        else:
            out += [o, c]
    return out


def edit_mask(draft: str, mask: list | None) -> list:
    """The mask a quote starts editing with: all of it shows when unmasked
    (both brackets drawn), nothing ([]) when it showed nothing."""
    if mask is None:
        return [snap(draft, 0, True), snap(draft, len(draft), False)]
    return tidy_edit(draft, mask)


def view_to_draft(draft: str, mask: list | None, v: int) -> int:
    """Where position v of a quote's view is in its draft (on a …: where it starts)."""
    if mask is None:
        return v
    hidden, shown = pieces(draft, mask)
    vpos = dpos = 0
    for k, h in enumerate(hidden):
        drawn = len(mark(hidden, k, shown)) if has_text(h) else len(h)
        if v < vpos + drawn:
            return snap(draft, dpos, True) if has_text(h) else dpos + v - vpos
        vpos, dpos = vpos + drawn, dpos + len(h)
        if k < len(shown):
            if v <= vpos + len(shown[k]):
                return dpos + v - vpos
            vpos, dpos = vpos + len(shown[k]), dpos + len(shown[k])
    return len(draft)


def draft_to_view(draft: str, mask: list | None, p: int) -> int:
    """Where position p of a draft shows in a quote's view (hidden: at its …)."""
    if mask is None:
        return p
    hidden, shown = pieces(draft, mask)
    vpos = dpos = 0
    for k, h in enumerate(hidden):
        drawn = len(mark(hidden, k, shown)) if has_text(h) else len(h)
        if p < dpos + len(h):
            return vpos if has_text(h) else vpos + p - dpos
        vpos, dpos = vpos + drawn, dpos + len(h)
        if k < len(shown):
            if p <= dpos + len(shown[k]):
                return vpos + p - dpos
            vpos, dpos = vpos + len(shown[k]), dpos + len(shown[k])
    return vpos


def rebase(old: str, new: str, mask: list | None) -> list | None:
    """Anchors moved along with an edit from `old` to `new`, whatever made it:
    the changed stretch is where the two differ, and an anchor in or at it
    moves so its range grows (an opening one to its start, a closing one to
    its end)."""
    if not mask or old == new:
        return mask
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    q = 0
    while q < min(len(old), len(new)) - p and old[-1 - q] == new[-1 - q]:
        q += 1
    end_old, end_new = len(old) - q, len(new) - q
    return [x if x < p else x + len(new) - len(old) if x > end_old else p if n % 2 == 0 else end_new
            for n, x in enumerate(mask)]
