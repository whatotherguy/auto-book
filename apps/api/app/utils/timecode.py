def ms_to_timecode(ms: int) -> str:
    if ms < 0:
        raise ValueError(f"ms_to_timecode requires a non-negative value, got {ms}")
    total_seconds, millis = divmod(ms, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
