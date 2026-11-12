"""Conservative freshness check for read-only VLAN safety assessments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class FreshnessAssessment:
    blocked: bool
    reasons: tuple[str, ...]
    age_seconds: float | None


def assess_snapshot_freshness(
    observed_at: datetime | None,
    now: datetime,
    *,
    update_succeeded: bool,
    max_age: timedelta = timedelta(minutes=5),
) -> FreshnessAssessment:
    """Reject unknown, unsuccessful, future or stale switch observations."""
    reasons: list[str] = []
    age: float | None = None
    if not update_succeeded:
        reasons.append("coordinator_update_failed")
    if observed_at is None or observed_at.tzinfo is None or now.tzinfo is None:
        reasons.append("snapshot_timestamp_unavailable")
    else:
        age = (now - observed_at).total_seconds()
        if age < 0:
            reasons.append("snapshot_timestamp_in_future")
        elif age > max_age.total_seconds():
            reasons.append("snapshot_too_old")
    if max_age.total_seconds() <= 0:
        reasons.append("invalid_maximum_age")
    return FreshnessAssessment(bool(reasons), tuple(reasons), age)
