"""Duration formatting utility conforming to the '<h> hour(s) <m> min <s> sec' specification."""


def format_duration(seconds: float | int) -> str:
    """Formats a duration in seconds into '<h> hour(s) <m> min <s> sec'.

    Shows only hours, minutes and seconds if not null, except for a null duration: '0 sec'.
    Sub-second non-zero durations (>0 and <1) are rounded to '1 sec'.

    Args:
        seconds: Duration in seconds (can be fractional float or integer).

    Returns:
        Formatted duration string.
    """
    if seconds <= 0:
        return "0 sec"

    total_sec = round(seconds)
    if total_sec == 0:
        # Non-zero duration under 0.5s: ensure minimum 1 sec per agreed specification
        total_sec = 1

    hours = total_sec // 3600
    remainder = total_sec % 3600
    minutes = remainder // 60
    secs = remainder % 60

    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours} hour(s)")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if secs > 0:
        parts.append(f"{secs} sec")

    if not parts:
        return "0 sec"
    return " ".join(parts)
