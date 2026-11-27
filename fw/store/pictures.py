"""Pictures: Image blocks' files in the images folder beside the store, and their titles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from fw import block as fw_block
from fw import image as fw_image
from fw.store.paths import IMAGES_PATH, TITLES_PATH, StoreError, cached_json

MAX_DOWNLOAD = 50_000_000  # the biggest picture fetch_image takes


def image_file(name: str) -> Path:
    return IMAGES_PATH / name


def add_image(src: str) -> str:
    """Picture file `src` copied into the images folder (add_image_data). Returns its name there."""
    try:
        data = Path(src).expanduser().read_bytes()
    except OSError as e:
        raise StoreError(f"can't read {src}: {e.strerror}")
    return add_image_data(data, src)


def add_image_data(data: bytes, what: str) -> str:
    """Picture `data` into the images folder, named by its hash (kept once). Returns its name; StoreError if no picture."""
    k = fw_image.kind(data[:16])
    if k is None:
        raise StoreError(f"not a png, jpeg, gif or webp: {what}")
    name = f"{hashlib.sha1(data).hexdigest()[:16]}.{k}"
    IMAGES_PATH.mkdir(exist_ok=True)
    if not image_file(name).exists():
        tmp = image_file(name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, image_file(name))
    return name


def fetch_image(url: str) -> bytes:
    """The bytes at web address `url` (fw keeps its own copy, never the link). Raises StoreError."""
    import urllib.error, urllib.request  # (only here: it's slow to load)
    if not url.startswith(("http://", "https://")):
        raise StoreError("that's not a web address (http… or https…)")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) fw/1.0 (free-writing journal)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(MAX_DOWNLOAD + 1)
    except urllib.error.HTTPError as e:
        raise StoreError(f"couldn't download it: {e.code} {e.reason}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise StoreError(f"couldn't download it: {getattr(e, 'reason', e)}")
    if len(data) > MAX_DOWNLOAD:
        raise StoreError("that picture's too big (50 MB at most)")
    return data


def read_titles(path) -> dict:
    try:
        got = json.loads(path.read_text(encoding="utf-8")).get("titles")
    except (OSError, ValueError, AttributeError):
        return {}
    return {k: v for k, v in got.items() if isinstance(v, str) and v.strip()} if isinstance(got, dict) else {}


_titles = [None, {}]


def load_picture_titles() -> dict:
    """picture-titles.json beside the store: {file name: a model's title}; read again only when it changes."""
    return cached_json(TITLES_PATH, _titles, read_titles)


def build_library(data: dict) -> dict:
    """fw_block.build_library, pictures titled by the model's titles."""
    return fw_block.build_library(data, load_picture_titles())
