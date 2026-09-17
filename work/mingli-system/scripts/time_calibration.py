from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def equation_of_time_minutes(value: datetime) -> float:
    """NOAA approximation of apparent-solar versus mean-solar time."""
    day_of_year = value.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (day_of_year - 1 + (value.hour - 12) / 24)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def true_solar_time(local_clock: datetime, longitude: float, timezone_name: str) -> tuple[datetime, float]:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA time zone: {timezone_name}") from exc
    aware = local_clock.replace(tzinfo=zone)
    utc_offset = aware.utcoffset()
    if utc_offset is None:
        raise ValueError(f"UTC offset unavailable for {timezone_name} at {local_clock.isoformat()}")
    offset_hours = utc_offset.total_seconds() / 3600
    correction = equation_of_time_minutes(local_clock) + 4 * longitude - 60 * offset_hours
    return local_clock + timedelta(minutes=correction), correction
