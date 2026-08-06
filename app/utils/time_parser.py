import re
from datetime import datetime, time, timedelta
from app.config import get_now, TZ


def parse_interval_to_seconds(text: str) -> int:
    """Parses flexible interval strings like '1h 30m 10s', '1ч 30м 10с', '01:30:10', '45m', '300' into integer seconds."""
    text = text.strip().lower()

    if not text:
        raise ValueError("Пустая строка интервала.")

    # Format HH:MM:SS or MM:SS
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 3:
            h, m, s = map(int, parts)
            if m >= 60 or s >= 60 or min(h, m, s) < 0:
                raise ValueError("Minutes and seconds must be between 0 and 59.")
            total = h * 3600 + m * 60 + s
            if total <= 0:
                raise ValueError("The interval must be greater than zero.")
            return total
        elif len(parts) == 2:
            m, s = map(int, parts)
            if s >= 60 or min(m, s) < 0:
                raise ValueError("Seconds must be between 0 and 59.")
            total = m * 60 + s
            if total <= 0:
                raise ValueError("The interval must be greater than zero.")
            return total
        else:
            raise ValueError("Неверный формат времени HH:MM:SS.")

    # Pure number -> seconds
    if text.isdigit():
        return int(text)

    # Human-readable regex for hours, minutes, seconds (English & Russian)
    hours = 0
    minutes = 0
    seconds = 0

    h_match = re.search(r'(\d+)\s*(?:h|ч|час|часа|часов)', text)
    if h_match:
        hours = int(h_match.group(1))

    m_match = re.search(r'(\d+)\s*(?:m|м|мин|минуту|минуты|минут)', text)
    if m_match:
        minutes = int(m_match.group(1))

    s_match = re.search(r'(\d+)\s*(?:s|с|сек|секунду|секунды|секунд)', text)
    if s_match:
        seconds = int(s_match.group(1))

    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError(f"Не удалось распознать интервал из строки '{text}'. Используйте формат: 1ч 30м, 01:30:00 или 300")

    return total


def format_seconds_to_hms(total_seconds: int) -> str:
    """Formats integer seconds into human-readable string like '1 ч. 30 мин. 10 сек.'"""
    total_seconds = int(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} ч.")
    if minutes > 0:
        parts.append(f"{minutes} мин.")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} сек.")

    return " ".join(parts)


def parse_time_hhmm(text: str) -> time:
    """Parses '09:00' or '9:00' into a datetime.time object."""
    text = text.strip()
    return datetime.strptime(text, "%H:%M").time()


def parse_time_range(text: str):
    """Parses '09:00-21:00' or '09:00 21:00' into (time(9,0), time(21,0))."""
    match = re.fullmatch(
        r"\s*(\d{1,2}:\d{2})\s*[-\u2010\u2011\u2012\u2013\u2014\u2212]\s*(\d{1,2}:\d{2})\s*",
        text,
    )
    if not match:
        raise ValueError("Формат времени должен быть ЧЧ:ММ-ЧЧ:ММ, например: 09:00-21:00")
    t1 = parse_time_hhmm(match.group(1))
    t2 = parse_time_hhmm(match.group(2))
    return t1, t2
