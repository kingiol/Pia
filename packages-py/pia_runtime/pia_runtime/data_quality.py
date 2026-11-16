from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


REQUIRED_MARKET_FIELDS = {
    "snapshot_id",
    "as_of",
    "observed_at",
    "source",
    "quality",
    "breadth",
    "index_trend",
    "volatility",
}

REQUIRED_PORTFOLIO_FIELDS = {
    "snapshot_id",
    "user_id",
    "as_of",
    "source",
    "cash",
    "total_value",
    "drawdown",
    "positions",
}

VALID_QUALITIES = {"verified", "partial", "stale", "unavailable"}
FIELD_COMPLETENESS_TARGET = 0.98
REQUIRED_UNIVERSE_BOARDS = ("main", "chinext", "star", "bse", "etf")
REQUIRED_UNIVERSE_METADATA = (
    "asset_type",
    "board",
    "exchange",
    "listed_at",
    "active",
)


def validate_universe_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate the documented MVP universe categories.

    The market snapshot can have complete aggregate metrics while its
    instrument universe is incomplete. Keep this check separate from generic
    snapshot field completeness so a provider cannot be promoted to verified
    merely because it returned a large number of instruments.
    """

    counts = {board: 0 for board in REQUIRED_UNIVERSE_BOARDS}
    for row in rows:
        board = str(row.get("board") or "").strip().lower()
        asset_type = str(row.get("asset_type") or "").strip().lower()
        category = "etf" if asset_type == "etf" or board == "etf" else board
        if category in counts:
            counts[category] += 1
    missing = [board for board in REQUIRED_UNIVERSE_BOARDS if counts[board] == 0]
    return {
        "required": list(REQUIRED_UNIVERSE_BOARDS),
        "counts": counts,
        "missing": missing,
        "pass": not missing,
    }


def validate_universe_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Report metadata completeness for the eligible universe.

    Suspended or delisted rows remain in the raw normalized universe for
    auditability, but they are excluded from candidate scans. Their missing
    historical listing dates are reported separately and do not downgrade an
    otherwise complete active universe.
    """

    missing_counts = {field: 0 for field in REQUIRED_UNIVERSE_METADATA}
    active_missing_counts = {field: 0 for field in REQUIRED_UNIVERSE_METADATA}
    inactive_missing_counts = {field: 0 for field in REQUIRED_UNIVERSE_METADATA}
    for row in rows:
        is_active = row.get("active") is not False
        for field in REQUIRED_UNIVERSE_METADATA:
            if row.get(field) in (None, ""):
                missing_counts[field] += 1
                target = active_missing_counts if is_active else inactive_missing_counts
                target[field] += 1
    missing = [
        field for field, count in active_missing_counts.items() if count
    ]
    return {
        "required": list(REQUIRED_UNIVERSE_METADATA),
        "missing_counts": missing_counts,
        "active_missing_counts": active_missing_counts,
        "inactive_missing_counts": inactive_missing_counts,
        "missing": missing,
        "pass": not missing,
    }


def validate_temporal_metadata(
    payload: dict[str, Any],
    *,
    expected_as_of: str | None = None,
    latest_allowed_as_of: str | None = None,
    now: datetime | None = None,
    published_field: str | None = None,
    require_observed_at: bool = True,
) -> dict[str, Any]:
    """Validate point-in-time metadata before it can be treated as verified.

    ``as_of`` describes the market/data date, while ``observed_at`` describes
    when the provider response was received. A response observed before its
    declared data date, in the future, or with an invalid expiry is not safe
    to use as verified evidence.
    """

    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    reference_now = reference_now.astimezone(timezone.utc)
    errors: list[dict[str, str]] = []

    as_of_value = payload.get("as_of") or expected_as_of
    as_of_date = _parse_date(as_of_value)
    expected_date = _parse_date(expected_as_of) if expected_as_of else None
    latest_allowed_date = (
        _parse_date(latest_allowed_as_of)
        if latest_allowed_as_of
        else None
    )
    if as_of_date is None:
        errors.append({
            "code": "AS_OF_INVALID",
            "message": "as_of must be an ISO date.",
        })
    elif as_of_date > reference_now.date():
        errors.append({
            "code": "AS_OF_IN_FUTURE",
            "message": "as_of cannot be later than the current date.",
        })
    if expected_date is not None and as_of_date is not None and as_of_date != expected_date:
        errors.append({
            "code": "AS_OF_MISMATCH",
            "message": f"as_of does not match the requested date {expected_date.isoformat()}.",
        })
    if (
        latest_allowed_date is not None
        and as_of_date is not None
        and as_of_date > latest_allowed_date
    ):
        errors.append({
            "code": "AS_OF_AFTER_REQUESTED",
            "message": (
                f"as_of cannot be later than the requested date "
                f"{latest_allowed_date.isoformat()}."
            ),
        })

    observed_at = _parse_datetime(payload.get("observed_at"))
    if observed_at is None and require_observed_at:
        errors.append({
            "code": "OBSERVED_AT_INVALID",
            "message": "observed_at must be an ISO timestamp.",
        })
    elif observed_at is not None:
        if observed_at > reference_now:
            errors.append({
                "code": "OBSERVED_AT_IN_FUTURE",
                "message": "observed_at cannot be later than the current time.",
            })
        if as_of_date is not None and observed_at.date() < as_of_date:
            errors.append({
                "code": "OBSERVED_AT_BEFORE_AS_OF",
                "message": "observed_at cannot precede the declared as_of date.",
            })

    expires_at = payload.get("expires_at")
    if expires_at not in (None, ""):
        expires = _parse_datetime(expires_at)
        if expires is None:
            errors.append({
                "code": "EXPIRES_AT_INVALID",
                "message": "expires_at must be an ISO timestamp.",
            })
        else:
            if observed_at is not None and expires < observed_at:
                errors.append({
                    "code": "EXPIRES_AT_BEFORE_OBSERVED",
                    "message": "expires_at cannot precede observed_at.",
                })
            if expires < reference_now:
                errors.append({
                    "code": "EXPIRED",
                    "message": "evidence has passed its expires_at timestamp.",
                })

    if published_field:
        published_at = _parse_datetime(payload.get(published_field))
        if published_at is None and payload.get(published_field) not in (None, ""):
            errors.append({
                "code": "PUBLISHED_AT_INVALID",
                "message": f"{published_field} must be an ISO date or timestamp.",
            })
        elif published_at is not None:
            if published_at > reference_now:
                errors.append({
                    "code": "PUBLISHED_AT_IN_FUTURE",
                    "message": f"{published_field} cannot be later than the current time.",
                })
            if observed_at is not None and published_at > observed_at:
                errors.append({
                    "code": "PUBLISHED_AT_AFTER_OBSERVED",
                    "message": f"{published_field} cannot be later than observed_at.",
                })
            if (
                latest_allowed_date is not None
                and published_at.date() > latest_allowed_date
            ):
                errors.append({
                    "code": "PUBLISHED_AFTER_REQUESTED",
                    "message": (
                        f"{published_field} cannot be later than the requested "
                        f"date {latest_allowed_date.isoformat()}."
                    ),
                })

    return {
        "valid": not errors,
        "errors": errors,
        "expired": any(error["code"] == "EXPIRED" for error in errors),
    }


def validate_snapshot(snapshot: dict[str, Any], kind: str) -> dict[str, Any]:
    required = REQUIRED_MARKET_FIELDS if kind == "market" else REQUIRED_PORTFOLIO_FIELDS
    missing = sorted(
        field for field in required
        if field not in snapshot or snapshot.get(field) in (None, "")
    )
    completeness = (
        round((len(required) - len(missing)) / len(required), 4)
        if required
        else 1.0
    )
    quality = snapshot.get("quality", "verified")
    if missing:
        quality = "unavailable"
    elif quality not in VALID_QUALITIES:
        quality = "partial"
    temporal = validate_temporal_metadata(
        snapshot,
        require_observed_at=kind == "market" or "observed_at" in snapshot,
    )
    if not temporal["valid"] and quality == "verified":
        quality = "stale" if temporal["expired"] else "unavailable"
    return {
        "quality": quality,
        "missing": missing,
        "field_completeness": completeness,
        "field_completeness_target": FIELD_COMPLETENESS_TARGET,
        "field_completeness_pass": completeness >= FIELD_COMPLETENESS_TARGET,
        "temporal_errors": temporal["errors"],
        "valid": (
            not missing
            and temporal["valid"]
            and quality == "verified"
            and completeness >= FIELD_COMPLETENESS_TARGET
        ),
    }


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10].replace("/", "-"))
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{text[:10]}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
