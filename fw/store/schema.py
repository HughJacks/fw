"""The block schema (schema.json): a small recursive checker, defaults, and what a person edits."""

from __future__ import annotations

import json
import re
from datetime import datetime

from fw.block import masks_out
from fw.store.paths import SCHEMA_PATH

TYPES = {"string": lambda v: isinstance(v, str), "null": lambda v: v is None,
         "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
         "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
         "boolean": lambda v: isinstance(v, bool), "array": lambda v: isinstance(v, list),
         "object": lambda v: isinstance(v, dict)}


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _type_ok(value, spec) -> bool:
    return any(TYPES.get(t, lambda v: False)(value) for t in (spec if isinstance(spec, list) else [spec]))


def _is_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate(value, spec: dict, where: str = "") -> list[str]:
    """What's wrong with `value` by draft-2020-12 `spec` (the parts schema.json uses), recursively."""
    name = f"field `{where}`" if where else "entry"
    at = lambda k: f"{where}.{k}" if where else k
    if "oneOf" in spec and not any(not validate(value, alt, where) for alt in spec["oneOf"]):
        return [f"{name} is none of the shapes it can be"]
    if "type" in spec and not _type_ok(value, spec["type"]):
        return [f"{name} has wrong type (want {spec['type']})"]
    errors = []
    if "const" in spec and value != spec["const"]:
        errors.append(f"{name} must be {spec['const']!r}")
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{name} must be one of {spec['enum']}")
    if isinstance(value, str):
        if spec.get("pattern") and not re.search(spec["pattern"], value):
            errors.append(f"{name} does not match {spec['pattern']}")
        if spec.get("format") == "date-time" and not _is_date(value):
            errors.append(f"{name} is not an ISO-8601 date-time")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < spec.get("minimum", value):
        errors.append(f"{name} is below {spec['minimum']}")
    if isinstance(value, list):
        if not spec.get("minItems", 0) <= len(value) <= spec.get("maxItems", len(value)):
            errors.append(f"{name} has {len(value)} items")
        first = spec.get("prefixItems", [])
        for n, item in enumerate(value):
            sub = first[n] if n < len(first) else spec.get("items")
            if sub is not None:
                errors += validate(item, sub, f"{where}[{n}]")
    if isinstance(value, dict):
        props, extra = spec.get("properties", {}), spec.get("additionalProperties")
        errors += [f"missing required field `{k}`" for k in spec.get("required", []) if k not in value]
        if extra is False:
            errors += [f"unexpected field `{k}`" for k in value if k not in props]
        elif isinstance(extra, dict):
            errors += [e for k in value if k not in props for e in validate(value[k], extra, at(k))]
        errors += [e for key, sub in props.items() if key in value for e in validate(value[key], sub, at(key))]
    return errors


def validate_instance(obj, schema) -> list[str]:
    return validate(obj, schema) if isinstance(obj, dict) else ["entry is not a JSON object"]


def apply_defaults(obj: dict, schema: dict) -> list[str]:
    """Each missing property with a `default` added to `obj`; returns their names."""
    added = [k for k, spec in schema.get("properties", {}).items() if k not in obj and "default" in spec]
    obj.update({k: schema["properties"][k]["default"] for k in added})
    return added


def editable_keys(schema: dict) -> list[str]:
    """The header fields a person edits: all not readOnly, but `content` (the body)."""
    return [k for k, spec in schema.get("properties", {}).items() if not spec.get("readOnly") and k != "content"]


def invalid(data: dict, schema: dict, old: dict | None = None) -> list:
    """What's wrong with the blocks as they'll be written; with `old` (valid, as on disk), only those that differ."""
    was = {b["id"]: b for b in old["blocks"]} if old is not None else {}
    return [f"block {b.get('id') or f'index {i}'}: {e}"
            for i, b in enumerate(masks_out(data["blocks"])) if was.get(b.get("id")) != b for e in validate_instance(b, schema)]
