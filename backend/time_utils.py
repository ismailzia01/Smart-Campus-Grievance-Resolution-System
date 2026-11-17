"""
Time and timezone utility functions for Smart Campus Grievance System.
Ensures consistent conversion from UTC database timestamps to Indian Standard Time (Asia/Kolkata).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST_TIMEZONE = ZoneInfo('Asia/Kolkata')


class ISTStr(str):
    """A string subclass marking that a timestamp string is already in Indian Standard Time (IST).

    Prevents accidental double conversion if passed through conversion filters again.
    """
    _is_ist = True


def to_ist(val, format_str='%Y-%m-%d %H:%M'):
    """Convert a UTC timestamp (string or datetime) to Indian Standard Time (Asia/Kolkata).

    Guarantees:
    - If val is None or empty, returns empty string.
    - If val is already an ISTStr or marked with _is_ist, returns it unchanged (avoids double conversion).
    - If val is a datetime:
        - If naive: treated as UTC per SQLite database convention, then converted to IST.
        - If timezone-aware: converted to IST using astimezone() (avoids double conversion if already in IST).
    - If val is a string:
        - Strips whitespace.
        - If string contains '+05:30' or is already marked, handles conversion without double addition.
        - Handles ISO formats (including trailing 'Z' or explicit offsets).
        - If naive string (e.g. '2026-11-17 07:27:14' or '2026-11-17 07:27'): treated as UTC, then converted to IST.
    - Returns an ISTStr formatted according to format_str (default: '%Y-%m-%d %H:%M').
    """
    if val is None:
        return ''

    if getattr(val, '_is_ist', False):
        return val

    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        ist_dt = val.astimezone(IST_TIMEZONE)
        return ISTStr(ist_dt.strftime(format_str))

    val_str = str(val).strip()
    if not val_str:
        return ''

    # Handle ISO 'Z' suffix (UTC)
    cleaned = val_str.replace('Z', '+00:00')

    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            dt = datetime.strptime(val_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                dt = datetime.strptime(val_str, '%Y-%m-%d %H:%M')
            except ValueError:
                # If unparseable, return string as-is without crashing
                return ISTStr(val_str)

    if dt.tzinfo is None:
        # SQLite naive strings are stored in UTC
        dt = dt.replace(tzinfo=timezone.utc)

    ist_dt = dt.astimezone(IST_TIMEZONE)
    return ISTStr(ist_dt.strftime(format_str))


# Alias for template and API readability
format_ist = to_ist
