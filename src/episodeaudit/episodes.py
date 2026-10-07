"""Timestamp grouping without an implicit specimen-identity claim."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .manifest import AuditInputError, Manifest, manifest_from_rows, membership_key


def _assumed_timezone(name: str | None) -> tzinfo | None:
    if name is None:
        return None
    if name == "UTC":
        return timezone.utc
    if not isinstance(name, str) or not name:
        raise AuditInputError("naive_timezone must be an explicit IANA time-zone name or UTC.")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise AuditInputError("Time zone is unavailable; use offset-qualified timestamps or install the required time-zone data.") from error


def build_episodes(manifest: Manifest, *, gap_seconds: float = 5.0,
                   naive_timezone: str | None = None, overwrite_groups: bool = False) -> Manifest:
    """Join adjacent captures within collection/acquisition/local-calendar-day.

    Chaining is intentional: a group's first-to-last duration can exceed the
    gap. Each adjacent interval must be <= gap_seconds. No spatial, specimen,
    disease, or camera continuity is inferred. acquisition_id is supplied
    by the user and must be nonempty on every row.
    """
    if isinstance(gap_seconds, bool) or not isinstance(gap_seconds, (int, float)) or not math.isfinite(gap_seconds) or gap_seconds < 0:
        raise AuditInputError("gap_seconds must be a finite nonnegative number.")
    if not isinstance(overwrite_groups, bool):
        raise AuditInputError("overwrite_groups must be boolean; only explicit True permits overwriting existing groups.")
    zone = _assumed_timezone(naive_timezone)
    keys = [membership_key(row) for row in manifest.rows]
    if len(keys) != len(set(keys)):
        raise AuditInputError("Episode construction requires unique collection/sample membership.")
    if not overwrite_groups and any(row.get("group_id") for row in manifest.rows):
        raise AuditInputError("Existing groups would be overwritten; explicitly request overwrite_groups=True.")
    buckets = defaultdict(list)
    for index, row in enumerate(manifest.rows):
        if not row.get("timestamp") or not row.get("acquisition_id"):
            raise AuditInputError("Every row requires timestamp and explicit acquisition_id for episode construction.")
        try:
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except ValueError as error:
            raise AuditInputError(f"Invalid ISO-8601 timestamp for sample {row['sample_id']}.") from error
        # Date-only strings are accepted by datetime.fromisoformat but do not
        # provide a capture time and must not be treated as midnight captures.
        if "T" not in row["timestamp"] and " " not in row["timestamp"]:
            raise AuditInputError("A capture timestamp must contain an explicit time of day.")
        assumed = stamp.tzinfo is None or stamp.utcoffset() is None
        if assumed:
            if zone is None:
                raise AuditInputError("Naive timestamp requires an explicit naive_timezone assumption.")
            stamp = stamp.replace(tzinfo=zone)
        key = (row["collection_id"], row["acquisition_id"], stamp.date().isoformat())
        buckets[key].append((stamp.astimezone(timezone.utc), row["sample_id"], index, assumed))
    assignments = {}
    for key, items in sorted(buckets.items()):
        items.sort(key=lambda item: (item[0], item[1]))
        previous = None
        token = ""
        for stamp, sample_id, index, assumed in items:
            if previous is None or (stamp - previous).total_seconds() > gap_seconds:
                seed = json.dumps([*key, stamp.isoformat(), sample_id], ensure_ascii=False, separators=(",", ":"))
                token = "ep-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
            assignments[index] = (token, "assumed_timezone:" + str(naive_timezone) if assumed else "provided_utc_offset")
            previous = stamp
    output = []
    for index, row in enumerate(manifest.rows):
        clone = dict(row)
        token, basis = assignments[index]
        clone.update(group_id=token, group_kind="episode", group_namespace="",
                     episode_gap_seconds=str(float(gap_seconds)), episode_time_basis=basis)
        output.append(clone)
    return manifest_from_rows(output)
