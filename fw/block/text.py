"""Words, titles and times: pure functions over strings."""

from __future__ import annotations

import re
from datetime import datetime

TITLE_MAX_CHARS = 60
_SEP_RE = re.compile(r"^-{2,}")
_LEAD_MARKUP_RE = re.compile(r"^[#>\-\*\s]+")
PUNCTUATION = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~" + "–—…“”‘’«»•·")
EXPR_REF = re.compile(r"@([0-9]{8}T[0-9]{6}-[0-9a-f]{4})")
INLINE_CODE = re.compile(r"(?<!\\)\$((?:[^$\n\\]|\\.)*?)\$")   # an inline expression in a text: $source$


def human_date(dt: datetime) -> str:
    """e.g. `August 3rd, 2026`."""
    n = dt.day
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{dt.strftime('%B')} {n}{suffix}, {dt.year}"


def derive_title(content: str) -> str | None:
    """The first real line (no separators or leading markup), clipped to a word boundary; None if there's none."""
    for raw in content.splitlines():
        line = _LEAD_MARKUP_RE.sub("", raw.strip()).strip().strip("\"'“”")
        if not line or _SEP_RE.match(raw.strip()):
            continue
        if len(line) <= TITLE_MAX_CHARS:
            return line.rstrip(".,;:—- ")
        clipped = line[:TITLE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(".,;:—- ")
        return (clipped or line[:TITLE_MAX_CHARS].rstrip()) + "…"
    return None


def is_word(token: str) -> bool:
    """A run without spaces with something besides punctuation in it (the page's `isWord` and Hazel's `is_word` too)."""
    return any(c not in PUNCTUATION for c in token)


def word_count(content: str) -> int:
    """Words in a text as stored; an inline expression counts as one."""
    return sum(1 for w in INLINE_CODE.sub(" \x00 ", content).split() if is_word(w))


def inline_codes(text: str) -> list:
    """The sources of a text's inline expressions (`$…$`; `\\$` a dollar sign), in order."""
    return [m.group(1) for m in INLINE_CODE.finditer(text or "")]


def pretty_time(iso: str | None, clock: bool = True) -> str:
    """"Oct 21, 2026, 3:04 pm" (or just the date)."""
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    date = f"{t:%b} {t.day}, {t.year}"
    return f"{date}, {t.hour % 12 or 12}:{t:%M} {'am' if t.hour < 12 else 'pm'}" if clock else date


def iso_minute(stamp: str | None) -> int | None:
    """An ISO stamp as minutes since the epoch (None if unreadable)."""
    try:
        return int(datetime.fromisoformat(stamp).timestamp() // 60)
    except (TypeError, ValueError):
        return None


def minute_iso(minute: int | None) -> str:
    """Minutes since the epoch as a local ISO date-time ("" for none)."""
    return "" if minute is None else datetime.fromtimestamp(minute * 60).astimezone().isoformat(timespec="seconds")


def ago(minute: int | None, now_min: int) -> str:
    """'just now', '5m ago', '3h ago', '4d ago', '2mo ago', '1y ago'."""
    if minute is None:
        return ""
    d = max(now_min - minute, 0)
    return next((f"{d // size}{unit} ago" for size, unit in ((525600, "y"), (43200, "mo"), (1440, "d"), (60, "h"), (1, "m"))
                 if d >= size), "just now")
