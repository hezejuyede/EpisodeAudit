"""Strict CSV intake and collection-local membership identifiers."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


class AuditInputError(ValueError):
    """The supplied data cannot support an unambiguous requested operation."""


REQUIRED_COLUMNS = ("sample_id", "collection_id")
OPTIONAL_COLUMNS = ("label", "group_id", "group_kind", "group_namespace", "sha256", "split", "path", "timestamp", "acquisition_id")
GROUP_KINDS = frozenset(("identity", "episode", "other", "unknown"))
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Manifest:
    """Rows in original order. Unknown extra columns are retained as metadata.

    A repeated (collection_id, sample_id) is retained, not silently deduplicated:
    the integrity audit must inspect the complete split membership evidence.
    """

    rows: tuple[dict[str, str], ...]
    columns: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.rows)


def membership_key(row: Mapping[str, str]) -> tuple[str, str]:
    return row["collection_id"], row["sample_id"]


def group_key(row: Mapping[str, str]) -> tuple[str, str, str] | None:
    """An explicit global namespace is optional; the default is collection-local.

    group_kind does NOT form part of identity. Reusing a namespace/ID with
    contradictory kinds is a metadata error, not a way to evade overlap checks.
    """
    if not row.get("group_id"):
        return None
    if row.get("group_namespace"):
        return "explicit", row["group_namespace"], row["group_id"]
    return "collection", row["collection_id"], row["group_id"]


def manifest_from_rows(rows: Iterable[Mapping[str, object]], columns: Iterable[str] | None = None) -> Manifest:
    collected = list(rows)
    if not collected:
        raise AuditInputError("Manifest has no rows; an empty audit cannot pass.")
    if columns is None:
        names = list(dict.fromkeys(key for row in collected for key in row))
    else:
        names = list(columns)
    if len(names) != len(set(names)) or any(not isinstance(n, str) or not n or n != n.strip() for n in names):
        raise AuditInputError("Column names must be unique, nonempty, and have no surrounding whitespace.")
    missing = set(REQUIRED_COLUMNS).difference(names)
    if missing:
        raise AuditInputError("Missing required columns: " + ", ".join(sorted(missing)))
    normalized = []
    for index, original in enumerate(collected, 2):
        if set(original).difference(names):
            raise AuditInputError(f"Row {index} contains fields not represented in the CSV header.")
        row = {}
        for name in names:
            value = original.get(name, "")
            if value is None:
                value = ""
            if not isinstance(value, (str, int, float)):
                raise AuditInputError(f"Row {index}, {name}: value must be a scalar string or number.")
            string = str(value).strip()
            if any(ord(c) < 32 for c in string):
                raise AuditInputError(f"Row {index}, {name}: control characters are not allowed.")
            row[name] = string
        for name in REQUIRED_COLUMNS:
            if not row.get(name):
                raise AuditInputError(f"Row {index}: {name} must be nonempty.")
        digest = row.get("sha256", "").lower()
        if digest and not HASH_PATTERN.fullmatch(digest):
            raise AuditInputError(f"Row {index}: sha256 must contain exactly 64 hexadecimal characters.")
        if "sha256" in row:
            row["sha256"] = digest
        kind = row.get("group_kind", "").lower() or "unknown"
        if kind not in GROUP_KINDS:
            raise AuditInputError(f"Row {index}: group_kind must be identity, episode, other, or unknown.")
        if row.get("group_namespace") and not row.get("group_id"):
            raise AuditInputError(f"Row {index}: group_namespace without group_id is ambiguous.")
        if row.get("group_kind") and not row.get("group_id"):
            raise AuditInputError(f"Row {index}: group_kind without group_id is ambiguous.")
        if row.get("group_id"):
            row["group_kind"] = kind
        normalized.append(row)
    # Ensure generated/normalized columns such as group_kind are written back.
    all_names = tuple(dict.fromkeys(names + [key for row in normalized for key in row]))
    return Manifest(tuple(normalized), all_names)


def load_manifest(path: str | Path) -> Manifest:
    """Read a UTF-8 / UTF-8-BOM comma-separated manifest without type coercion."""
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames is None:
                raise AuditInputError("Manifest has no CSV header.")
            columns = reader.fieldnames
            rows = []
            for line, row in enumerate(reader, 2):
                if None in row or any(v is None for v in row.values()):
                    raise AuditInputError(f"Row {line}: number of fields differs from the header.")
                rows.append(row)
        return manifest_from_rows(rows, columns)
    except (OSError, UnicodeError, csv.Error) as error:
        raise AuditInputError(f"Unable to read CSV manifest: {error}") from error


def write_manifest(manifest: Manifest, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=manifest.columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest.rows)
