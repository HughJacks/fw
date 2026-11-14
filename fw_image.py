"""fw_image — pictures: what kind a file is and how big, from its first
bytes, and how a terminal is told to draw one.

Pure functions: bytes in, values out (the store reads and copies the files,
the editor writes the escapes). Drawing uses iTerm2's inline images
(OSC 1337 File=…): the terminal decodes and scales the picture itself into
a box of cells, so fw never decodes one. What's sent is a copy no bigger
than the box needs (`thumb_width`; the store makes it), not the original.
"""

from __future__ import annotations

import base64
import struct

CELL_PX = 16       # about how many pixels wide a cell is (Retina)
THUMB_STEP = 400   # copies are made this many pixels wider at a time, so resizing seldom makes another
BIG = 512_000      # a file bigger than this is sent as a copy, however few pixels it has
KINDS = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8": "jpg", b"GIF87a": "gif", b"GIF89a": "gif"}
EXTENSIONS = ("png", "jpg", "jpeg", "gif", "webp")


def kind(head: bytes) -> str | None:
    """The picture format of a file starting with `head`, else None."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return next((k for magic, k in KINDS.items() if head.startswith(magic)), None)


def size(data: bytes) -> tuple[int, int] | None:
    """(width, height) in pixels of a picture's bytes, else None."""
    match kind(data):
        case "png" if len(data) >= 24:
            return struct.unpack(">II", data[16:24])
        case "gif" if len(data) >= 10:
            return struct.unpack("<HH", data[6:10])
        case "jpg":
            return jpeg_size(data)
        case "webp":
            return webp_size(data)
    return None


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Walk a JPEG's segments to its frame header (SOFn)."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def webp_size(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        w, h = struct.unpack("<HH", data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        b = data[21:25]
        return 1 + (((b[1] & 0x3F) << 8) | b[0]), 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
    if chunk == b"VP8X" and len(data) >= 30:
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    return None


def rows_for(px: tuple[int, int] | None, cols: int, most: int) -> tuple[int, int]:
    """How many (columns, rows) of cells a picture of `px` pixels takes,
    `cols` wide at most and `most` rows high at most: its shape kept, a
    cell about twice as tall as it is wide."""
    if not px or not px[0] or not px[1]:
        return cols, min(most, 6)
    w, h = px
    rows = max(1, round(cols * h / w / 2))
    if rows > most:
        return max(1, round(most * 2 * w / h)), most
    return cols, rows


def thumb_width(px: tuple[int, int] | None, nbytes: int, cols: int) -> int | None:
    """How many pixels wide a copy of a picture of `px` pixels (`nbytes`
    big) should be to draw `cols` cells wide, or None to send the original
    (not much wider than that, nor big)."""
    want = -(-cols * CELL_PX // THUMB_STEP) * THUMB_STEP
    if not px or (px[0] <= want * 1.25 and nbytes <= BIG):
        return None
    return min(want, px[0])


def iterm(data: bytes, cols: int, rows: int) -> str:
    """The escape that has iTerm2 draw picture `data` in `cols` × `rows`
    cells from the cursor, its shape kept."""
    return (f"\x1b]1337;File=inline=1;size={len(data)};width={cols};height={rows};preserveAspectRatio=1:"
            + base64.b64encode(data).decode("ascii") + "\x07")


def dropped_path(text: str) -> str | None:
    """A file path as a terminal pastes one dropped on it (spaces and the like
    escaped with \\, or the whole quoted), if `text` is just that, else None."""
    t = text.strip()
    if "\n" in t or not t:
        return None
    if len(t) > 1 and t[0] == t[-1] and t[0] in "'\"":
        t = t[1:-1]
    else:
        out, it = "", iter(t)
        for ch in it:
            out += next(it, "") if ch == "\\" else ch
        t = out
    if t.startswith("file://"):
        from urllib.parse import unquote
        t = unquote(t[7:])
    return t if t.startswith(("/", "~")) and t.lower().rsplit(".", 1)[-1] in EXTENSIONS else None
